from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

import portfolio_analysis.pipeline as pipeline_module
from portfolio_analysis.config import ASSETS
from portfolio_analysis.pipeline import PipelineError, PipelineResult, run_pipeline
from portfolio_analysis.portfolios import PortfolioOptimizationError


EXPECTED_OUTPUTS = {
    "analysis.sqlite",
    "powerbi/prices.csv",
    "powerbi/asset_metrics.csv",
    "powerbi/portfolio_timeseries.csv",
    "powerbi/portfolio_metrics.csv",
    "powerbi/correlation_matrix.csv",
    "powerbi/portfolio_weights.csv",
    "powerbi/data_quality.csv",
    "resume_facts.json",
}


def test_run_pipeline_creates_retrying_session_only_when_session_is_omitted(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    configured_session = _FixtureSession()
    factory_calls = []

    def fake_session_factory():
        factory_calls.append(True)
        return configured_session

    monkeypatch.setattr(
        pipeline_module, "create_market_session", fake_session_factory
    )

    run_pipeline(
        date(2026, 1, 1), date(2026, 2, 14), tmp_path / "output"
    )

    assert factory_calls == [True]
    assert configured_session.eastmoney_symbols == [asset.symbol for asset in ASSETS]


def test_run_pipeline_creates_offline_powerbi_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = _FixtureSession()

    result = run_pipeline(
        date(2026, 1, 1), date(2026, 2, 14), tmp_path / "output", session=session
    )

    output_dir = tmp_path / "output"
    actual = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert EXPECTED_OUTPUTS.issubset(actual)
    facts = json.loads((output_dir / "resume_facts.json").read_text(encoding="utf-8"))
    assert {
        "price_rows",
        "asset_count",
        "risk_metric_count",
        "start_date",
        "end_date",
        "portfolio_count",
    }.issubset(facts)
    assert facts["price_rows"] == 45 * len(ASSETS)
    assert facts["asset_count"] == len(ASSETS)
    assert facts["risk_metric_count"] == 5
    assert facts["portfolio_count"] == 2
    assert not {
        "revenue_growth",
        "profit_growth",
        "business_improvement",
    }.intersection(facts)
    assert result.failures == {}
    assert session.eastmoney_symbols == [asset.symbol for asset in ASSETS]
    assert session.yahoo_symbols == []
    assert set(result.metadata["data_providers"].values()) == {"eastmoney"}


def test_run_pipeline_falls_back_to_yahoo_for_one_eastmoney_failure(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    fallback_symbol = ASSETS[1].symbol
    session = _FixtureSession(eastmoney_failing_symbol=fallback_symbol)

    result = run_pipeline(
        date(2026, 1, 1), date(2026, 2, 14), tmp_path / "output", session=session
    )

    assert result.failures == {}
    assert session.eastmoney_symbols == [asset.symbol for asset in ASSETS]
    assert session.yahoo_symbols == [fallback_symbol]
    assert result.metadata["data_providers"][fallback_symbol] == "yahoo"
    assert {
        provider
        for symbol, provider in result.metadata["data_providers"].items()
        if symbol != fallback_symbol
    } == {"eastmoney"}


def test_run_pipeline_does_not_fallback_after_unexpected_primary_error(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    session = _FixtureSession()

    def raise_programming_error(*args, **kwargs):
        raise TypeError("primary programming error")

    monkeypatch.setattr(
        pipeline_module, "fetch_eastmoney_asset_prices", raise_programming_error
    )

    with pytest.raises(TypeError, match="primary programming error"):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 2, 14),
            tmp_path / "output",
            session=session,
        )

    assert session.yahoo_symbols == []
    assert not (tmp_path / "output").exists()


def test_run_pipeline_records_each_asset_failure_and_skips_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = _FixtureSession(failing_symbol=ASSETS[2].symbol)

    result = run_pipeline(
        date(2026, 1, 1), date(2026, 2, 14), tmp_path / "output", session=session
    )

    assert list(result.failures) == [ASSETS[2].symbol]
    assert "simulated fetch failure" in result.failures[ASSETS[2].symbol]
    assert session.eastmoney_symbols == [asset.symbol for asset in ASSETS]
    assert session.yahoo_symbols == [ASSETS[2].symbol]
    assert not (tmp_path / "output" / "resume_facts.json").exists()


def test_run_pipeline_retains_only_equal_weights_when_optimization_fails(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    def fail_optimization(returns):
        raise PortfolioOptimizationError("solver did not converge")

    monkeypatch.setattr(
        "portfolio_analysis.pipeline.minimum_volatility_weights", fail_optimization
    )

    result = run_pipeline(
        date(2026, 1, 1),
        date(2026, 2, 14),
        tmp_path / "output",
        session=_FixtureSession(),
    )

    weights = pd.read_csv(tmp_path / "output" / "powerbi" / "portfolio_weights.csv")
    facts = json.loads(
        (tmp_path / "output" / "resume_facts.json").read_text(encoding="utf-8")
    )
    assert weights["portfolio"].unique().tolist() == ["equal_weight"]
    assert weights["weight"].sum() == pytest.approx(1.0)
    assert facts["portfolio_count"] == 1
    assert result.metadata["optimization_status"] == "failed"
    assert result.metadata["optimization_error"] == "solver did not converge"


def test_run_pipeline_uses_complete_five_asset_window_for_portfolios(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    run_pipeline(
        date(2026, 1, 1),
        date(2026, 2, 14),
        tmp_path / "output",
        session=_FixtureSession(missing_date=(ASSETS[4].symbol, 20)),
    )

    quality = pd.read_csv(tmp_path / "output" / "powerbi" / "data_quality.csv")
    timeseries = pd.read_csv(
        tmp_path / "output" / "powerbi" / "portfolio_timeseries.csv"
    )
    assert quality.loc[0, "shared_window_rows"] == 42
    assert timeseries.groupby("portfolio").size().eq(42).all()


def test_portfolio_timeseries_contains_20_day_annualized_rolling_volatility(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    run_pipeline(
        date(2026, 1, 1),
        date(2026, 2, 14),
        tmp_path / "output",
        session=_FixtureSession(),
    )

    timeseries = pd.read_csv(
        tmp_path / "output" / "powerbi" / "portfolio_timeseries.csv"
    )
    assert "rolling_volatility_20d" in timeseries.columns
    for _, portfolio in timeseries.groupby("portfolio", sort=False):
        assert portfolio["rolling_volatility_20d"].iloc[:19].isna().all()
        expected = portfolio["daily_return"].iloc[:20].std(ddof=1) * np.sqrt(252)
        assert portfolio["rolling_volatility_20d"].iloc[19] == pytest.approx(
            expected
        )


def test_run_pipeline_rejects_empty_complete_five_asset_return_window(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        PipelineError, match="No complete five-asset return window is available"
    ):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 12, 31),
            tmp_path / "output",
            session=_DisjointFixtureSession(),
        )

    assert not (tmp_path / "output").exists()


def test_resume_risk_metric_count_comes_from_populated_asset_metric_columns(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    original = pipeline_module._asset_metrics_table

    def metrics_with_unpopulated_var(returns):
        table = original(returns)
        table["historical_var"] = np.nan
        return table

    monkeypatch.setattr(
        pipeline_module, "_asset_metrics_table", metrics_with_unpopulated_var
    )

    run_pipeline(
        date(2026, 1, 1),
        date(2026, 2, 14),
        tmp_path / "output",
        session=_FixtureSession(),
    )

    facts = json.loads(
        (tmp_path / "output" / "resume_facts.json").read_text(encoding="utf-8")
    )
    assert facts["risk_metric_count"] == 4


def test_run_pipeline_cleans_staging_when_new_package_build_fails(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output_new"
    original_write_csv = pipeline_module._write_csv
    write_count = 0

    def fail_second_csv(frame, path):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise RuntimeError("simulated staged build failure")
        return original_write_csv(frame, path)

    monkeypatch.setattr(pipeline_module, "_write_csv", fail_second_csv)

    with pytest.raises(RuntimeError, match="simulated staged build failure"):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 2, 14),
            output_dir,
            session=_FixtureSession(),
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".output_new.staging-*"))


def test_run_pipeline_refuses_existing_destination_without_modifying_it(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output_existing"
    output_dir.mkdir()
    (output_dir / "verified.bin").write_bytes(b"previous\x00package")
    nested = output_dir / "powerbi"
    nested.mkdir()
    (nested / "prices.csv").write_bytes(b"old,verified\r\n1,2\r\n")
    before = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }

    with pytest.raises(
        PipelineError, match="Output destination already exists: .*output_existing"
    ):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 2, 14),
            output_dir,
            session=_FixtureSession(),
        )

    after = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not list(tmp_path.glob(".output_existing.staging-*"))


def test_run_pipeline_publishes_new_destination_with_one_directory_rename(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output_new"
    original_rename = os.rename
    publish_renames = []

    def record_rename(source, destination):
        source_path = Path(source)
        if (
            source_path.name.startswith(".output_new.staging-")
            and Path(destination) == output_dir
        ):
            publish_renames.append((source_path, Path(destination)))
        return original_rename(source, destination)

    monkeypatch.setattr(os, "rename", record_rename)

    run_pipeline(
        date(2026, 1, 1),
        date(2026, 2, 14),
        output_dir,
        session=_FixtureSession(),
    )

    actual = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert len(publish_renames) == 1
    assert EXPECTED_OUTPUTS.issubset(actual)
    assert not list(tmp_path.glob(".output_new.staging-*"))


def test_run_pipeline_cleans_staging_when_new_destination_rename_fails(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output_failed"
    original_rename = os.rename

    def fail_staging_publish(source, destination):
        source_path = Path(source)
        if (
            source_path.name.startswith(".output_failed.staging-")
            and Path(destination) == output_dir
        ):
            raise PermissionError("simulated publish failure")
        return original_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_staging_publish)

    with pytest.raises(PipelineError, match="Could not publish output package"):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 2, 14),
            output_dir,
            session=_FixtureSession(),
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".output_failed.staging-*"))


def test_run_pipeline_preserves_destination_created_during_publish_race(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output_race"
    competing_bytes = b"competing\x00package"
    original_rename = os.rename

    def create_competing_destination(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            source_path.name.startswith(".output_race.staging-")
            and destination_path == output_dir
        ):
            destination_path.mkdir()
            (destination_path / "winner.bin").write_bytes(competing_bytes)
            raise FileExistsError("simulated destination race")
        return original_rename(source, destination)

    monkeypatch.setattr(pipeline_module.os, "rename", create_competing_destination)

    with pytest.raises(
        PipelineError, match="Output destination already exists: .*output_race"
    ):
        run_pipeline(
            date(2026, 1, 1),
            date(2026, 2, 14),
            output_dir,
            session=_FixtureSession(),
        )

    assert (output_dir / "winner.bin").read_bytes() == competing_bytes
    assert {path.name for path in output_dir.iterdir()} == {"winner.bin"}
    assert not list(tmp_path.glob(".output_race.staging-*"))


class _FixtureResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FixtureSession:
    def __init__(
        self, failing_symbol=None, eastmoney_failing_symbol=None, missing_date=None
    ):
        self.eastmoney_symbols = []
        self.yahoo_symbols = []
        self.failing_symbol = failing_symbol
        self.eastmoney_failing_symbol = eastmoney_failing_symbol
        self.missing_date = missing_date

    def get(self, url, *, params, timeout, headers=None):
        if "eastmoney.com" in url:
            assert headers["Referer"] == "https://quote.eastmoney.com/"
            assert "Mozilla/5.0" in headers["User-Agent"]
            symbol = next(
                asset.symbol
                for asset in ASSETS
                if params["secid"].endswith(asset.symbol.split(".", 1)[0])
            )
            self.eastmoney_symbols.append(symbol)
            if symbol == self.failing_symbol:
                raise requests.ConnectionError("simulated fetch failure")
            if symbol == self.eastmoney_failing_symbol:
                return _FixtureResponse({"rc": 1, "data": None})
            return _FixtureResponse(self._eastmoney_payload(symbol))

        symbol = url.rsplit("/", 1)[-1]
        self.yahoo_symbols.append(symbol)
        if symbol == self.failing_symbol:
            raise requests.ConnectionError("simulated fetch failure")
        return _FixtureResponse(self._yahoo_payload(symbol))

    def _prices(self, symbol):
        symbol_offset = next(
            index for index, asset in enumerate(ASSETS) if asset.symbol == symbol
        )
        return [
            100.0 + symbol_offset * 10.0 + offset * (0.15 + symbol_offset * 0.01)
            + (offset % 4) * 0.05
            for offset in range(45)
        ]

    def _eastmoney_payload(self, symbol):
        first_day = datetime(2026, 1, 1)
        klines = []
        for offset, close in enumerate(self._prices(symbol)):
            if self.missing_date == (symbol, offset):
                continue
            observed = (first_day + timedelta(days=offset)).date().isoformat()
            klines.append(f"{observed},{close},{close},{close},{close},1000")
        return {"rc": 0, "data": {"klines": klines}}

    def _yahoo_payload(self, symbol):
        first_day = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [
            int((first_day + timedelta(days=offset)).timestamp())
            for offset in range(45)
        ]
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {"adjclose": [{"adjclose": self._prices(symbol)}]},
                    }
                ],
                "error": None,
            }
        }


class _DisjointFixtureSession(_FixtureSession):
    def _eastmoney_payload(self, symbol):
        symbol_offset = next(
            index for index, asset in enumerate(ASSETS) if asset.symbol == symbol
        )
        first_day = datetime(2026, 1, 1) + timedelta(days=symbol_offset * 60)
        klines = []
        for offset, close in enumerate(self._prices(symbol)):
            observed = (first_day + timedelta(days=offset)).date().isoformat()
            klines.append(f"{observed},{close},{close},{close},{close},1000")
        return {"rc": 0, "data": {"klines": klines}}
