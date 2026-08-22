"""End-to-end portfolio analysis orchestration and output packaging."""

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
import pandas as pd

from portfolio_analysis.cleaning import DataQuality, clean_prices
from portfolio_analysis.config import ASSETS
from portfolio_analysis.data_source import (
    MarketDataError,
    create_market_session,
    fetch_asset_prices,
    fetch_eastmoney_asset_prices,
)
from portfolio_analysis.metrics import asset_metrics, daily_returns
from portfolio_analysis.portfolios import (
    PortfolioOptimizationError,
    equal_weights,
    minimum_volatility_weights,
    portfolio_returns,
)
from portfolio_analysis.storage import write_analysis_database


RISK_METRICS = (
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "maximum_drawdown",
    "historical_var",
)


class PipelineError(RuntimeError):
    """Raised when the complete analysis package cannot be built."""


@dataclass(frozen=True)
class PipelineResult:
    """Summary and diagnostics for one pipeline attempt."""

    output_dir: Path
    failures: dict[str, str]
    metadata: dict[str, Any]


def run_pipeline(
    start: date,
    end: date,
    output_dir: str | Path,
    session: Any = None,
) -> PipelineResult:
    """Fetch all configured assets and build the SQLite and Power BI package."""
    output_path = Path(output_dir)
    market_session = session if session is not None else create_market_session()

    frames = []
    failures = {}
    data_providers = {}
    for asset in ASSETS:
        try:
            frame = fetch_eastmoney_asset_prices(asset, start, end, market_session)
            provider = "eastmoney"
        except MarketDataError as eastmoney_error:
            try:
                frame = fetch_asset_prices(asset, start, end, market_session)
                provider = "yahoo"
            except MarketDataError as yahoo_error:
                failures[asset.symbol] = (
                    f"Eastmoney {type(eastmoney_error).__name__}: {eastmoney_error}; "
                    f"Yahoo {type(yahoo_error).__name__}: {yahoo_error}"
                )
                continue
        frames.append(frame)
        data_providers[asset.symbol] = provider

    if failures:
        return PipelineResult(
            output_dir=output_path,
            failures=failures,
            metadata={
                "status": "asset_fetch_failed",
                "assets_fetched": len(frames),
                "assets_required": len(ASSETS),
                "data_providers": data_providers,
            },
        )

    prices, quality = clean_prices(pd.concat(frames, ignore_index=True))
    returns = daily_returns(prices)
    metrics = _asset_metrics_table(returns)

    shared_returns = returns.dropna(axis=0, how="any")
    if shared_returns.empty:
        raise PipelineError("No complete five-asset return window is available")
    portfolio_weights = {"equal_weight": equal_weights(shared_returns.columns)}
    optimization_error = None
    try:
        portfolio_weights["minimum_volatility"] = minimum_volatility_weights(
            shared_returns
        )
    except PortfolioOptimizationError as error:
        optimization_error = str(error)

    portfolio_timeseries, portfolio_metric_table = _portfolio_tables(
        shared_returns, portfolio_weights
    )
    weights_table = _weights_table(portfolio_weights)
    correlation_table = _correlation_table(shared_returns)
    quality_table = _quality_table(quality, shared_returns)

    facts = {
        "price_rows": int(len(prices)),
        "asset_count": int(prices["symbol"].nunique()),
        "risk_metric_count": int(
            sum(
                name in metrics.columns and metrics[name].notna().all()
                for name in RISK_METRICS
            )
        ),
        "start_date": quality.start_date.date().isoformat(),
        "end_date": quality.end_date.date().isoformat(),
        "portfolio_count": len(portfolio_weights),
    }

    staging_path = _create_staging_directory(output_path)
    try:
        _build_output_package(
            staging_path,
            prices=prices,
            asset_metric_table=metrics,
            portfolio_timeseries=portfolio_timeseries,
            portfolio_metric_table=portfolio_metric_table,
            correlation_table=correlation_table,
            weights_table=weights_table,
            quality_table=quality_table,
            facts=facts,
        )
        _publish_output_package(staging_path, output_path)
    except Exception:
        if staging_path.exists():
            shutil.rmtree(staging_path)
        raise

    metadata = {
        "status": "complete",
        "optimization_status": "failed" if optimization_error else "succeeded",
        "optimization_error": optimization_error,
        "shared_window_rows": int(len(shared_returns)),
        "shared_window_start": shared_returns.index.min().date().isoformat(),
        "shared_window_end": shared_returns.index.max().date().isoformat(),
        "data_providers": data_providers,
        **facts,
    }
    return PipelineResult(output_path, failures, metadata)


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-", dir=destination.parent
        )
    )


def _build_output_package(
    staging_path: Path,
    *,
    prices: pd.DataFrame,
    asset_metric_table: pd.DataFrame,
    portfolio_timeseries: pd.DataFrame,
    portfolio_metric_table: pd.DataFrame,
    correlation_table: pd.DataFrame,
    weights_table: pd.DataFrame,
    quality_table: pd.DataFrame,
    facts: dict[str, Any],
) -> None:
    powerbi_path = staging_path / "powerbi"
    powerbi_path.mkdir()
    _write_csv(prices, powerbi_path / "prices.csv")
    _write_csv(asset_metric_table, powerbi_path / "asset_metrics.csv")
    _write_csv(portfolio_timeseries, powerbi_path / "portfolio_timeseries.csv")
    _write_csv(portfolio_metric_table, powerbi_path / "portfolio_metrics.csv")
    _write_csv(correlation_table, powerbi_path / "correlation_matrix.csv")
    _write_csv(weights_table, powerbi_path / "portfolio_weights.csv")
    _write_csv(quality_table, powerbi_path / "data_quality.csv")

    write_analysis_database(
        staging_path / "analysis.sqlite",
        {
            "prices": prices,
            "asset_metrics": asset_metric_table,
            "portfolio_metrics": portfolio_metric_table,
            "portfolio_weights": weights_table,
        },
    )
    (staging_path / "resume_facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _publish_output_package(staging_path: Path, destination: Path) -> None:
    if destination.exists():
        raise PipelineError(
            f"Output destination already exists: {destination}. "
            "Choose a new versioned output directory."
        )
    try:
        os.rename(staging_path, destination)
    except OSError as error:
        if destination.exists():
            message = (
                f"Output destination already exists: {destination}. "
                "Choose a new versioned output directory."
            )
        else:
            message = f"Could not publish output package to {destination}."
        raise PipelineError(message) from error


def _asset_metrics_table(returns: pd.DataFrame) -> pd.DataFrame:
    table = asset_metrics(returns).rename_axis("symbol").reset_index()
    asset_lookup = pd.DataFrame(
        {
            "symbol": [asset.symbol for asset in ASSETS],
            "asset_name": [asset.name for asset in ASSETS],
            "asset_class": [asset.asset_class for asset in ASSETS],
        }
    )
    return asset_lookup.merge(table, on="symbol", how="inner")


def _portfolio_tables(
    returns: pd.DataFrame, weights_by_portfolio: dict[str, pd.Series]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    series_frames = []
    metric_series = {}
    for name, weights in weights_by_portfolio.items():
        daily = portfolio_returns(returns, weights).rename(name)
        metric_series[name] = daily
        frame = daily.rename("daily_return").reset_index()
        frame.columns = ["date", "daily_return"]
        frame.insert(1, "portfolio", name)
        frame["cumulative_return"] = (1.0 + frame["daily_return"]).cumprod() - 1.0
        frame["rolling_volatility_20d"] = (
            frame["daily_return"].rolling(window=20, min_periods=20).std(ddof=1)
            * np.sqrt(252)
        )
        series_frames.append(frame)

    metric_table = (
        asset_metrics(pd.DataFrame(metric_series))
        .rename_axis("portfolio")
        .reset_index()
    )
    return pd.concat(series_frames, ignore_index=True), metric_table


def _weights_table(weights_by_portfolio: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.concat(
        [
            weights.rename("weight").rename_axis("symbol").reset_index().assign(
                portfolio=name
            )
            for name, weights in weights_by_portfolio.items()
        ],
        ignore_index=True,
    ).loc[:, ["portfolio", "symbol", "weight"]]


def _correlation_table(returns: pd.DataFrame) -> pd.DataFrame:
    return (
        returns.corr()
        .rename_axis("symbol")
        .reset_index()
        .melt(id_vars="symbol", var_name="correlated_symbol", value_name="correlation")
    )


def _quality_table(quality: DataQuality, shared_returns: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "input_rows": quality.input_rows,
                "output_rows": quality.output_rows,
                "duplicates_removed": quality.duplicates_removed,
                "invalid_prices_removed": quality.invalid_prices_removed,
                "missing_close_removed": quality.missing_close_removed,
                "start_date": quality.start_date.date().isoformat(),
                "end_date": quality.end_date.date().isoformat(),
                "shared_window_rows": len(shared_returns),
                "shared_window_start": shared_returns.index.min().date().isoformat(),
                "shared_window_end": shared_returns.index.max().date().isoformat(),
            }
        ]
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    serializable = frame.copy()
    for column in serializable.select_dtypes(include=["datetime", "datetimetz"]):
        serializable[column] = serializable[column].dt.strftime("%Y-%m-%d")
    serializable.to_csv(path, index=False, encoding="utf-8")
