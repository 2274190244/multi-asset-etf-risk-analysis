import numpy as np
import pandas as pd
import pytest

from portfolio_analysis.metrics import (
    MetricError,
    asset_metrics,
    daily_returns,
    historical_var,
    maximum_drawdown,
)


def test_daily_returns_converts_normalized_prices_to_wide_returns():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-01-03", "2026-01-02", "2026-01-01", "2026-01-01", "2026-01-02"]
            ),
            "symbol": ["A", "A", "A", "B", "B"],
            "asset_name": ["Asset A", "Asset A", "Asset A", "Asset B", "Asset B"],
            "asset_class": ["equity", "equity", "equity", "bond", "bond"],
            "close": [121.0, 110.0, 100.0, 50.0, 55.0],
        }
    )

    returns = daily_returns(prices)

    assert returns.index.tolist() == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]
    assert returns.columns.tolist() == ["A", "B"]
    assert returns.loc[pd.Timestamp("2026-01-02"), "A"] == pytest.approx(0.10)
    assert returns.loc[pd.Timestamp("2026-01-03"), "A"] == pytest.approx(0.10)
    assert returns.loc[pd.Timestamp("2026-01-02"), "B"] == pytest.approx(0.10)


def test_daily_returns_leaves_price_gaps_unfilled():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-01-01", "2026-01-03", "2026-01-01", "2026-01-02", "2026-01-03"]
            ),
            "symbol": ["A", "A", "B", "B", "B"],
            "asset_name": ["Asset A", "Asset A", "Asset B", "Asset B", "Asset B"],
            "asset_class": ["equity", "equity", "bond", "bond", "bond"],
            "close": [100.0, 121.0, 50.0, 55.0, 60.0],
        }
    )

    returns = daily_returns(prices)

    assert returns["A"].isna().all()
    assert returns["B"].tolist() == pytest.approx([0.10, 60.0 / 55.0 - 1.0])


def test_maximum_drawdown_uses_running_peak():
    returns = pd.Series([0.10, -0.20, 0.05])

    assert maximum_drawdown(returns) == pytest.approx(-0.20)


def test_historical_var_is_reported_as_positive_loss():
    returns = pd.Series([-0.04, -0.02, 0.00, 0.01, 0.02])

    assert historical_var(returns, confidence=0.80) == pytest.approx(0.024)


def test_asset_metrics_rejects_fewer_than_30_daily_observations():
    returns = pd.DataFrame({"A": np.repeat(0.001, 29)})

    with pytest.raises(MetricError, match="30 daily observations"):
        asset_metrics(returns)


def test_asset_metrics_rejects_a_sparse_asset_when_another_has_enough_history():
    returns = pd.DataFrame(
        {
            "full": np.repeat(0.001, 30),
            "sparse": np.append(np.repeat(0.001, 29), np.nan),
        }
    )

    with pytest.raises(MetricError, match="sparse"):
        asset_metrics(returns)


@pytest.mark.parametrize("invalid_return", [-1.0, -1.01])
def test_asset_metrics_rejects_returns_that_would_invalidate_geometric_annualization(
    invalid_return,
):
    returns = pd.DataFrame({"A": np.append(np.repeat(0.001, 29), invalid_return)})

    with pytest.raises(MetricError, match="A"):
        asset_metrics(returns)


def test_asset_metrics_uses_geometric_return_sample_volatility_and_sharpe_formula():
    values = np.tile([-0.01, 0.0, 0.015, 0.005], 10)
    returns = pd.DataFrame({"A": values})

    metrics = asset_metrics(returns)

    assert metrics.loc["A", "annualized_return"] == pytest.approx(0.857119336809513)
    assert metrics.loc["A", "annualized_volatility"] == pytest.approx(0.144913767461894)
    assert metrics.loc["A", "sharpe_ratio"] == pytest.approx(5.776672233917574)


def test_asset_metrics_contains_only_finite_values():
    values = np.tile([-0.01, 0.0, 0.015, 0.005], 10)
    returns = pd.DataFrame({"A": values, "B": values * 0.5})

    metrics = asset_metrics(returns)

    assert metrics.index.tolist() == ["A", "B"]
    assert list(metrics.columns) == [
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "maximum_drawdown",
        "historical_var",
    ]
    assert np.isfinite(metrics.to_numpy()).all()
