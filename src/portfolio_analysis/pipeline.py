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
from portfolio_analysis.metrics import asset_metrics, daily_returns, RISK_METRICS
from portfolio_analysis.quality import assess_quality
from portfolio_analysis.portfolios import split_returns
from portfolio_analysis.portfolios import (
    PortfolioOptimizationError,
    equal_weights,
    minimum_volatility_weights,
    portfolio_returns,
)
from portfolio_analysis.storage import write_analysis_database




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
    *, price_data: pd.DataFrame | None = None,
    train_fraction: float = 0.7,
    risk_free_rate: float = 0.02,
    sessions_by_symbol=None,
    status_by_key=None,
) -> PipelineResult:
    """Fetch all configured assets and build the SQLite and Power BI package."""
    output_path = Path(output_dir)
    market_session = session if session is not None else create_market_session()

    if start > end:
        raise PipelineError("Requested start must not exceed end")
    if output_path.exists():
        raise PipelineError(f"Output destination already exists: {output_path}. Choose a new versioned output directory.")
    frames = []
    failures = {}
    data_providers = {}
    for asset in (ASSETS if price_data is None else []):
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

    raw_prices = pd.concat(frames, ignore_index=True) if price_data is None else price_data.copy()
    if set(raw_prices.symbol) != {a.symbol for a in ASSETS}:
        raise PipelineError("All five configured assets are required")
    provenance_columns = ["symbol", "source", "price_basis", "retrieval_timestamp",
                          "requested_start", "requested_end"]
    if not set(provenance_columns).issubset(raw_prices):
        raise PipelineError("Prices require persisted source and request metadata")
    for field in provenance_columns:
        if raw_prices[field].isna().any() or raw_prices[field].astype(str).str.strip().eq("").any():
            raise ValueError(f"Invalid source metadata field: {field}")
    if not np.isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError("risk_free_rate must be finite and greater than -1")
    if not np.isfinite(train_fraction) or not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    provenance = raw_prices.loc[:, provenance_columns + [
        c for c in ["raw_sha256", "snapshot_path", "replay_timestamp"] if c in raw_prices
    ]].drop_duplicates()
    metadata = {
        "status": "complete", "train_fraction": train_fraction,
        "annualization_periods": 252, "annual_risk_free_rate": risk_free_rate,
        "daily_risk_free_rate": float(np.expm1(np.log1p(risk_free_rate)/252)),
        "risk_free_convention": "fixed assumed annual effective rate",
        "sharpe_convention": "daily excess mean/sample std times sqrt(252)",
        "var_convention": "-linear return quantile(1-confidence), signed loss, no clamp",
        "confidence": 0.95, "interpolation": "linear",
        "cvar_convention": "negative integral of linear return quantile over [0,0.05] divided by 0.05",
        "downside_target_annual": 0.0,
        "rebalancing": "constant weights restored each day; gross of costs",
        "sample_policy": "longest complete contiguous common-session price block; earliest tie",
        "evaluation_design": "single chronological split; no rolling backtest",
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "data_providers": dict(zip(provenance.symbol, provenance.source)),
    }
    try:
        prices, quality = clean_prices(raw_prices)
    except ValueError as error:
        if not hasattr(error, "quality"):
            raise
        quality = error.quality
        prices = raw_prices.iloc[:0].copy()
    quality_report, events, window_prices = assess_quality(
        prices, quality, start, end, sessions_by_symbol=sessions_by_symbol,
        status_by_key=status_by_key)
    metadata["quality_events"] = len(events)
    metadata["calendar"] = quality_report.calendar.iloc[0]
    compatible = provenance.price_basis.isin(["forward_adjusted", "adjusted_close"]).all()
    consistent = provenance.groupby("symbol").price_basis.nunique().le(1).all()
    metadata["source_status"] = "adjusted_provider_prices_not_verified_total_return" if compatible and consistent else "mixed_or_unadjusted"
    extras = {"asset_data_quality": quality_report, "data_quality_events": events,
              "source_metadata": provenance}
    if len(window_prices) < 31 or metadata["source_status"] == "mixed_or_unadjusted":
        metadata.update(status="quality_only",
            reason="Insufficient contiguous history or incompatible price basis; no fabricated performance")
        stage = _create_staging_directory(output_path)
        try:
            (stage / "powerbi").mkdir()
            _write_evidence(stage, extras, metadata)
            _publish_output_package(stage, output_path)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return PipelineResult(output_path, {}, metadata)
    shared_returns = window_prices.pct_change(fill_method=None).iloc[1:].copy()
    if shared_returns.isna().any().any():
        raise PipelineError("Internal error: selected window is not complete")
    shared_returns.index.name = "date"
    training, evaluation = split_returns(shared_returns, train_fraction)
    metrics = _asset_metrics_table(shared_returns, risk_free_rate)
    portfolio_weights = {"equal_weight": equal_weights(shared_returns.columns)}
    optimization_error = None
    try:
        portfolio_weights["minimum_volatility"] = minimum_volatility_weights(training)
        metadata["optimization"] = portfolio_weights["minimum_volatility"].attrs["optimization"]
    except PortfolioOptimizationError as error:
        optimization_error = str(error)
    portfolio_timeseries, portfolio_metric_table = _portfolio_tables(
        evaluation, portfolio_weights, risk_free_rate)
    weights_table = _weights_table(portfolio_weights)
    correlation_table = _correlation_table(shared_returns)
    quality_table = _quality_table(quality, shared_returns)
    facts = {
        "price_rows": int(len(prices)), "asset_count": int(prices.symbol.nunique()),
        "risk_metric_count": sum(name in metrics for name in RISK_METRICS),
        "start_date": quality.start_date.date().isoformat(),
        "end_date": quality.end_date.date().isoformat(),
        "portfolio_count": len(portfolio_weights),
    }
    metadata.update({
        "optimization_status": "failed" if optimization_error else "succeeded",
        "optimization_error": optimization_error,
        "shared_window_rows": len(shared_returns),
        "shared_window_start": shared_returns.index.min().date().isoformat(),
        "shared_window_end": shared_returns.index.max().date().isoformat(),
        "training_start": training.index.min().date().isoformat(),
        "training_end": training.index.max().date().isoformat(),
        "evaluation_start": evaluation.index.min().date().isoformat(),
        "evaluation_end": evaluation.index.max().date().isoformat(),
        "training_rows": len(training), "evaluation_rows": len(evaluation),
        "evaluation_wealth_origin": training.index.max().date().isoformat(),
        "asset_metric_status": metrics.attrs.get("metric_status", {}),
        "portfolio_metric_status": portfolio_metric_table.attrs.get("metric_status", {}),
        "tail_sample_warning": len(evaluation) * 0.05 < 10,
        **facts,
    })
    staging_path = _create_staging_directory(output_path)
    try:
        _build_output_package(
            staging_path, prices=prices, asset_metric_table=metrics,
            portfolio_timeseries=portfolio_timeseries,
            portfolio_metric_table=portfolio_metric_table,
            correlation_table=correlation_table, weights_table=weights_table,
            quality_table=quality_table, facts=facts, extras=extras, metadata=metadata)
        _publish_output_package(staging_path, output_path)
    except Exception:
        if staging_path.exists(): shutil.rmtree(staging_path)
        raise
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
    extras=None, metadata=None,
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

    extras = extras or {}
    _write_evidence(staging_path, extras, metadata or {})
    write_analysis_database(
        staging_path / "analysis.sqlite",
        {
            "prices": prices,
            "asset_metrics": asset_metric_table,
            "portfolio_metrics": portfolio_metric_table,
            "portfolio_weights": weights_table,
            **extras,
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


def _asset_metrics_table(returns: pd.DataFrame, risk_free_rate=0.02) -> pd.DataFrame:
    table = asset_metrics(returns, risk_free_rate).rename_axis("symbol").reset_index()
    asset_lookup = pd.DataFrame(
        {
            "symbol": [asset.symbol for asset in ASSETS],
            "asset_name": [asset.name for asset in ASSETS],
            "asset_class": [asset.asset_class for asset in ASSETS],
        }
    )
    result = asset_lookup.merge(table, on="symbol", how="inner")
    result.attrs = table.attrs.copy()
    return result


def _portfolio_tables(
    returns: pd.DataFrame, weights_by_portfolio: dict[str, pd.Series], risk_free_rate=0.02
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
        asset_metrics(pd.DataFrame(metric_series), risk_free_rate, minimum_observations=2)
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


def _write_evidence(staging_path, extras, metadata):
    """Persist diagnostic tables, methodology and raw evidence for every run status."""
    for name, table in extras.items():
        _write_csv(table, staging_path / "powerbi" / f"{name}.csv")
    (staging_path / "methodology.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if "source_metadata" in extras and "snapshot_path" in extras["source_metadata"]:
        raw_folder = staging_path / "raw"
        raw_folder.mkdir()
        for raw_name in extras["source_metadata"]["snapshot_path"].unique():
            if pd.notna(raw_name):
                source = Path(raw_name)
                if not source.is_file():
                    raise PipelineError(f"Missing raw snapshot: {source}")
                shutil.copyfile(source, raw_folder / source.name)
