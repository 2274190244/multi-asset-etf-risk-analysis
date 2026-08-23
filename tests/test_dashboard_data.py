import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from portfolio_analysis.dashboard_data import (
    DashboardDataError,
    asset_cumulative_returns,
    correlation_wide,
    load_dashboard_data,
    portfolio_cumulative_returns,
    portfolio_drawdowns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def copy_verified_package(tmp_path):
    shutil.copytree(PROJECT_ROOT / "output_verified", tmp_path / "output_verified")
    return tmp_path


def test_load_dashboard_data_reads_verified_package():
    data = load_dashboard_data(PROJECT_ROOT)

    assert len(data.prices) == 3630
    assert data.prices["symbol"].nunique() == 5
    assert set(data.portfolio_metrics["portfolio"]) == {
        "equal_weight",
        "minimum_volatility",
    }
    assert data.resume_facts["risk_metric_count"] == 5
    assert data.prices["date"].min() == pd.Timestamp("2023-08-14")
    assert data.prices["date"].max() == pd.Timestamp("2026-08-12")


def test_load_dashboard_data_reports_missing_file(tmp_path):
    root = copy_verified_package(tmp_path)
    (root / "output_verified" / "powerbi" / "prices.csv").unlink()

    with pytest.raises(DashboardDataError, match="prices.csv"):
        load_dashboard_data(root)


def test_load_dashboard_data_reports_missing_column(tmp_path):
    root = copy_verified_package(tmp_path)
    path = root / "output_verified" / "powerbi" / "asset_metrics.csv"
    frame = pd.read_csv(path).drop(columns="historical_var")
    frame.to_csv(path, index=False)

    with pytest.raises(DashboardDataError, match="historical_var"):
        load_dashboard_data(root)


def test_load_dashboard_data_rejects_invalid_dates(tmp_path):
    root = copy_verified_package(tmp_path)
    path = root / "output_verified" / "powerbi" / "prices.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "date"] = "not-a-date"
    frame.to_csv(path, index=False)

    with pytest.raises(DashboardDataError, match="prices.csv.*date"):
        load_dashboard_data(root)


def test_load_dashboard_data_rejects_non_finite_metrics(tmp_path):
    root = copy_verified_package(tmp_path)
    path = root / "output_verified" / "powerbi" / "asset_metrics.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "annualized_return"] = np.inf
    frame.to_csv(path, index=False)

    with pytest.raises(DashboardDataError, match="annualized_return"):
        load_dashboard_data(root)


def test_load_dashboard_data_rejects_blank_identifier_text(tmp_path):
    root = copy_verified_package(tmp_path)
    path = root / "output_verified" / "powerbi" / "prices.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "asset_name"] = ""
    frame.to_csv(path, index=False)

    with pytest.raises(DashboardDataError, match="asset_name"):
        load_dashboard_data(root)


def test_load_dashboard_data_rejects_inconsistent_resume_facts(tmp_path):
    root = copy_verified_package(tmp_path)
    path = root / "output_verified" / "resume_facts.json"
    facts = json.loads(path.read_text(encoding="utf-8"))
    facts["price_rows"] = 9999
    path.write_text(json.dumps(facts), encoding="utf-8")

    with pytest.raises(DashboardDataError, match="price_rows.*不一致"):
        load_dashboard_data(root)


def test_asset_cumulative_returns_filters_and_rebases_each_asset():
    data = load_dashboard_data(PROJECT_ROOT)

    result = asset_cumulative_returns(
        data.prices,
        symbols=["510300.SS", "518880.SS"],
        start_date="2024-01-02",
        end_date="2024-03-29",
    )

    assert set(result["symbol"]) == {"510300.SS", "518880.SS"}
    assert result["date"].between("2024-01-02", "2024-03-29").all()
    assert result.groupby("symbol")["cumulative_return"].first().tolist() == pytest.approx(
        [0.0, 0.0]
    )


def test_asset_cumulative_returns_rejects_empty_selection():
    data = load_dashboard_data(PROJECT_ROOT)

    with pytest.raises(DashboardDataError, match="筛选条件"):
        asset_cumulative_returns(data.prices, symbols=[])


def test_portfolio_drawdowns_follow_running_peak():
    timeseries = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "portfolio": ["equal_weight"] * 3,
            "cumulative_return": [0.10, -0.12, -0.076],
        }
    )

    result = portfolio_drawdowns(timeseries)

    assert result["drawdown"].tolist() == pytest.approx([0.0, -0.20, -0.16])
    assert (result["drawdown"] <= 0).all()


def test_portfolio_cumulative_returns_rebases_at_selected_start():
    timeseries = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "portfolio": ["equal_weight"] * 3,
            "daily_return": [0.10, -0.20, 0.05],
        }
    )

    result = portfolio_cumulative_returns(
        timeseries, start_date="2026-01-02", end_date="2026-01-03"
    )

    assert result["cumulative_return"].tolist() == pytest.approx([0.0, 0.05])


def test_portfolio_cumulative_returns_rejects_empty_range():
    data = load_dashboard_data(PROJECT_ROOT)

    with pytest.raises(DashboardDataError, match="没有组合日收益记录"):
        portfolio_cumulative_returns(
            data.portfolio_timeseries,
            start_date="2023-08-14",
            end_date="2023-08-14",
        )


def test_correlation_wide_returns_symmetric_named_matrix():
    data = load_dashboard_data(PROJECT_ROOT)

    result = correlation_wide(data.correlation_matrix, data.asset_names)

    assert result.shape == (5, 5)
    assert result.index.tolist() == result.columns.tolist()
    assert np.allclose(result.to_numpy(), result.to_numpy().T)
    assert np.allclose(np.diag(result), 1.0)
    assert "沪深300ETF" in result.index


def test_correlation_wide_rejects_a_missing_asset():
    data = load_dashboard_data(PROJECT_ROOT)
    incomplete = data.correlation_matrix.loc[
        (data.correlation_matrix["symbol"] != "159915.SZ")
        & (data.correlation_matrix["correlated_symbol"] != "159915.SZ")
    ]

    with pytest.raises(DashboardDataError, match="缺少资产.*创业板ETF"):
        correlation_wide(incomplete, data.asset_names)
