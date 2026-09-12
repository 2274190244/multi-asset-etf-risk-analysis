"""Reproducible Phase 2 scenarios and versioned research output packages."""
from pathlib import Path
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import numpy as np
import pandas as pd
from portfolio_analysis.backtest import run_backtest, STRATEGIES, COST_BPS
from portfolio_analysis.metrics import asset_metrics, simple_returns
from portfolio_analysis.quality import china_sessions
from portfolio_analysis.config import ASSETS
from portfolio_analysis.data_source import parse_eastmoney_response


def file_hashes(folder):
    """Return relative POSIX filename -> SHA256 for all files under folder."""
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def load_phase1_source(folder):
    """Validate preserved Phase 1 evidence and return complete common daily returns.

    Parameters
    ----------
    folder : path
        Complete Phase 1 package with prices, source metadata, raw responses.
    Returns
    -------
    (DataFrame, dict)
        Calendar-checked daily returns and original methodology. Raw hashes and
        normalized provider prices must match. No gaps are filled or discarded.
        This replay supports the five configured Chinese ETFs/Eastmoney source.
    """
    folder = Path(folder)
    meta = json.loads((folder/"methodology.json").read_text(encoding="utf-8"))
    if meta["status"] != "complete":
        raise ValueError("Phase 1 source must be complete")
    provenance = pd.read_csv(folder/"powerbi/source_metadata.csv")
    prices = pd.read_csv(folder/"powerbi/prices.csv", parse_dates=["date"])
    if set(prices.symbol) != {a.symbol for a in ASSETS}:
        raise ValueError("Expected the five configured assets")
    if prices.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate price rows")
    if not provenance.price_basis.eq("forward_adjusted").all() or not provenance.source.eq("eastmoney").all():
        raise ValueError("Replay requires the preserved forward-adjusted Eastmoney evidence")
    for asset in ASSETS:
        rows = provenance[provenance.symbol == asset.symbol]
        if len(rows) != 1:
            raise ValueError("Ambiguous source metadata")
        path = folder/"raw"/f"eastmoney_{asset.symbol}.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != rows.iloc[0].raw_sha256:
            raise ValueError(f"Raw hash mismatch: {asset.symbol}")
        parsed = parse_eastmoney_response(json.loads(path.read_text(encoding="utf-8")), asset)
        original = parsed.set_index("date").close.sort_index()
        saved = prices[prices.symbol == asset.symbol].set_index("date").close.sort_index()
        original.index = pd.to_datetime(original.index)
        try:
            pd.testing.assert_series_equal(saved, original, check_names=False,
                                           check_dtype=False, rtol=1e-12, atol=1e-12)
        except AssertionError as error:
            raise ValueError(f"Raw versus saved prices mismatch: {asset.symbol}") from error
    wide = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    first_return = pd.Timestamp(meta["shared_window_start"])
    if first_return not in wide.index or wide.index.get_loc(first_return) == 0:
        raise ValueError("Missing initial wealth price")
    start = wide.index[wide.index.get_loc(first_return)-1]
    end = pd.Timestamp(meta["shared_window_end"])
    window = wide.loc[start:end]
    calendar = pd.DatetimeIndex(china_sessions(start.date(), end.date()))
    if not window.index.equals(calendar.rename("date")):
        raise ValueError("Incomplete or unexpected common China trading dates")
    values = window.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Nonfinite, missing or nonpositive prices; no silent dropping")
    return simple_returns(window), meta


def run_scenarios(returns, *, estimation_window=252, frequencies=(21, 63),
                  costs=COST_BPS, risk_free_rate=0.02):
    """Return research tables/metadata for all three strategies on identical dates.

    Parameters
    ----------
    returns : DataFrame
        Validated common-date daily returns.
    estimation_window : int
        Rolling observations, default 252.
    frequencies, costs : tuples
        Unique nonempty subsets of (21,63) and (0,5,10,20).
    risk_free_rate : float
        Annual effective assumed rate for existing metric functions.
    Returns
    -------
    (dict[str, DataFrame], dict)
        Daily returns, holdings, trades, targets, gross/net summary,
        concentration/turnover diagnostics and explicit metric status.
    """
    if (not frequencies or len(set(frequencies)) != len(frequencies)
            or not set(frequencies).issubset({21, 63})
            or not costs or len(set(costs)) != len(costs)
            or not set(costs).issubset(COST_BPS)):
        raise ValueError("Scenario lists must be unique nonempty allowed subsets")
    if not np.isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError("Invalid annual risk-free rate")
    tables = {name: [] for name in ("daily", "weights", "trades", "targets")}
    summary, diagnostics, statuses = [], [], []
    common_index = None
    for strategy in STRATEGIES:
        for frequency in frequencies:
            for cost in costs:
                result = run_backtest(returns, strategy=strategy,
                    estimation_window=estimation_window, rebalance_every=frequency,
                    cost_bps=cost)
                if common_index is None:
                    common_index = result.daily.index
                if not result.daily.index.equals(common_index):
                    raise ValueError("Scenario evaluation dates differ")
                key = {"strategy": strategy, "rebalance_every": frequency, "cost_bps": cost}
                for name in tables:
                    frame = getattr(result, name)
                    if name == "daily":
                        frame = frame.reset_index()
                    tables[name].append(frame.assign(**key))
                daily, trades = result.daily, result.trades
                metric_input = daily[["gross_return", "net_return"]].rename(
                    columns={"gross_return": "gross", "net_return": "net"})
                stats = asset_metrics(metric_input, risk_free_rate, minimum_observations=2)
                for basis in ("gross", "net"):
                    summary.append({**key, "basis": basis,
                        "start": common_index[0], "end": common_index[-1],
                        "observations": len(daily), **stats.loc[basis].to_dict(),
                        "total_return": float(daily[basis+"_nav"].iloc[-1]-1)})
                    for metric, status in stats.attrs["metric_status"][basis].items():
                        statuses.append({**key, "basis": basis, "metric": metric, "status": status})
                regular = trades.loc[~trades.initial]
                diagnostics.append({**key, "executions": len(trades),
                    "subsequent_rebalances": len(regular),
                    "initial_turnover": float(trades.loc[trades.initial, "turnover"].sum()),
                    "subsequent_turnover": float(regular.turnover.sum()),
                    "total_turnover": float(trades.turnover.sum()),
                    "annualized_turnover": float(regular.turnover.sum()*252/len(daily)),
                    "mean_subsequent_turnover": float(regular.turnover.mean()) if len(regular) else 0.,
                    "transaction_cost": float(trades.transaction_cost.sum()),
                    "initial_transaction_cost": float(trades.loc[trades.initial, "transaction_cost"].sum()),
                    "traded_amount": float(trades.traded_amount.sum()),
                    "terminal_wealth_drag": float(daily.gross_nav.iloc[-1]-daily.net_nav.iloc[-1]),
                    "mean_maximum_weight": float(daily.maximum_weight.mean()),
                    "peak_weight": float(daily.maximum_weight.max()),
                    "mean_hhi": float(daily.hhi.mean()), "max_hhi": float(daily.hhi.max()),
                    "max_target_weight": float(trades.target_maximum_weight.max()),
                    "mean_target_hhi": float(trades.target_hhi.mean())})
    completed = {name: pd.concat(frames, ignore_index=True) for name, frames in tables.items()}
    completed.update(summary=pd.DataFrame(summary), diagnostics=pd.DataFrame(diagnostics),
                     metric_status=pd.DataFrame(statuses))
    metadata = {
        "phase": 2, "scenario_count": len(STRATEGIES)*len(frequencies)*len(costs),
        "estimation_window": estimation_window, "frequencies": list(frequencies),
        "cost_bps": list(costs), "annualization_periods": 252,
        "annual_risk_free_rate": risk_free_rate,
        "evaluation_start": str(common_index[0].date()),
        "evaluation_end": str(common_index[-1].date()), "evaluation_count": len(common_index),
        "execution_rule": "close t using 252 (or configured window) returns through t-1; first gain t+1",
        "cost_rule": "per-side actual notional; q=k*sum(abs((1-q)*target-pretrade))",
        "turnover_rule": "half L1 including cash; initial turnover=1",
        "annualized_turnover_rule": "subsequent turnover *252/evaluation_return_count; excludes initial",
        "initial_fee_rule": "allocated to first net return; actual date retained in trade ledger",
        "initial_fee_risk_caveat": "first net observation includes one-off entry fee and first market return",
        "concentration_rule": "daily end-of-day drifted holdings and execution targets separately",
        "terminal_liquidation": False, "daily_rebalancing": False,
        "undefined_ratios": "NaN with metric_status table; never zero-filled",
        "var": "95% signed loss, negative linear return quantile; no clamp",
        "cvar": "negative mean of linear quantile curve over [0,.05]",
        "sharpe": "daily effective risk-free; daily excess mean/sample std * sqrt(252)",
        "sortino_target_annual": 0.,
    }
    return completed, metadata


def compare_phase1(folder, phase2_daily, risk_free_rate=0.02):
    """Compare native and common dates without restarting Phase 2 holdings.

    Input: preserved Phase 1 folder and complete Phase 2 daily output table.
    Output: metric rows with explicit phase, basis, dates, and comparison label.
    Phase 1 gross has implicit daily target restoration and no cost accounting.
    """
    old = pd.read_csv(Path(folder)/"powerbi/portfolio_timeseries.csv", parse_dates=["date"])
    old_names = {"minimum_volatility": "minimum_variance", "equal_weight": "equal_weight"}
    left = max(old.date.min(), phase2_daily.date.min())
    right = min(old.date.max(), phase2_daily.date.max())
    records = []
    for mode in ("native", "common_dates"):
        for name, group in old.groupby("portfolio"):
            series = group.set_index("date").daily_return.sort_index()
            if mode == "common_dates":
                series = series.loc[left:right]
            stats = asset_metrics(series.to_frame("gross"), risk_free_rate, minimum_observations=2)
            records.append({"comparison": mode, "phase": "phase1",
                "strategy": old_names.get(name, name), "rebalance_every": 1, "cost_bps": 0,
                "basis": "gross", "start": series.index[0], "end": series.index[-1],
                "observations": len(series), **stats.loc["gross"].to_dict()})
        for key, group in phase2_daily.groupby(["strategy", "rebalance_every", "cost_bps"]):
            selected = group.set_index("date").sort_index()
            if mode == "common_dates":
                selected = selected.loc[left:right]
                if not selected.index.equals(pd.DatetimeIndex(sorted(old.loc[
                        old.date.between(left, right), "date"].unique()))):
                    raise ValueError("Phase comparison dates differ")
            x = selected[["gross_return", "net_return"]].rename(
                columns={"gross_return": "gross", "net_return": "net"})
            stats = asset_metrics(x, risk_free_rate, minimum_observations=2)
            for basis in ("gross", "net"):
                records.append({"comparison": mode, "phase": "phase2",
                    "strategy": key[0], "rebalance_every": key[1], "cost_bps": key[2],
                    "basis": basis, "start": selected.index[0], "end": selected.index[-1],
                    "observations": len(selected), **stats.loc[basis].to_dict()})
    return pd.DataFrame(records)


def export_package(tables, metadata, destination, *, source_folder=None):
    """Atomically write new CSV/SQLite package, refusing any existing destination.

    Parameters: named DataFrames, JSON-safe metadata, destination path, optional
    preserved Phase 1 folder copied as replay evidence.
    Returns: destination Path. Failure cleans only this call's temporary stage.
    """
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Output destination exists; choose a new version")
    if any(not name.replace("_", "").isalnum() for name in tables):
        raise ValueError("Invalid output table name")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".phase2-", dir=destination.parent))
    try:
        (stage/"tables").mkdir()
        with closing(sqlite3.connect(stage/"analysis.sqlite")) as con:
            for name, table in tables.items():
                serialized = table.copy()
                for col in serialized.select_dtypes(include=["datetime", "datetimetz"]):
                    serialized[col] = serialized[col].dt.strftime("%Y-%m-%d")
                serialized.to_csv(stage/"tables"/f"{name}.csv", index=False)
                serialized.to_sql(name, con, index=False, if_exists="fail")
        if source_folder is not None:
            shutil.copytree(source_folder, stage/"input_phase1")
        (stage/"methodology.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        (stage/"sha256.json").write_text(json.dumps(file_hashes(stage), indent=2), encoding="utf-8")
        if destination.exists():
            raise ValueError("Output destination exists")
        os.rename(stage, destination)
    except Exception:
        shutil.rmtree(stage)
        raise
    return destination
