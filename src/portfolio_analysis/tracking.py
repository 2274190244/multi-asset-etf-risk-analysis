"""Pairwise daily tracking analytics. No filling or implicit missing-row deletion."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .metrics import simple_returns, annualized_return, annualized_volatility, maximum_drawdown

@dataclass
class Alignment:
    """Selected complete levels/returns, counts, and one row per exclusion reason."""
    prices: pd.DataFrame
    returns: pd.DataFrame
    quality: dict
    events: pd.DataFrame

def _dates(index, label):
    if not isinstance(index, pd.DatetimeIndex) or index.tz is not None:
        raise ValueError(f"{label}: timezone-naive DatetimeIndex required")
    if index.hasnans or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError(f"{label}: dates must be unique, ordered and nonmissing")
    if not index.equals(index.normalize()):
        raise ValueError(f"{label}: dates must be normalized")
    return index

def _levels(series, label):
    if not isinstance(series, pd.Series):
        raise ValueError(f"{label}: Series required")
    _dates(series.index, label)
    x = series.to_numpy(dtype=float)
    if np.isinf(x).any() or (x <= 0).any():
        raise ValueError(f"{label}: observed levels must be finite and positive")

def align_levels(etf, benchmark, etf_calendar, benchmark_calendar):
    """Align positive level Series using explicit session DatetimeIndexes.

    Returns Alignment. NaNs/absent observations break daily-return intervals.
    Select the longest complete consecutive block on the union session calendar
    within the overlapping input date range; earliest block wins ties. Every
    rejected date has a reason in events. No filling or multi-day gap bridging.
    Calendars must cover the overlapping input range; calendar provenance is
    the caller's responsibility. Fewer than three selected levels raises.
    """
    _levels(etf, "etf"); _levels(benchmark, "benchmark")
    ec = _dates(etf_calendar, "etf_calendar")
    bc = _dates(benchmark_calendar, "benchmark_calendar")
    if etf.empty or benchmark.empty or ec.empty or bc.empty:
        raise ValueError("Empty data/calendar")
    start, end = max(etf.index[0],benchmark.index[0]), min(etf.index[-1],benchmark.index[-1])
    expected = ec.union(bc)
    expected = expected[(expected >= start) & (expected <= end)]
    if expected.empty:
        raise ValueError("No overlapping sessions")
    prices = pd.concat([etf.rename("etf"),benchmark.rename("benchmark")],axis=1,sort=True).reindex(expected)
    eligible = prices.notna().all(axis=1) & expected.isin(ec) & expected.isin(bc)
    events = []
    def log(date, reason, asset):
        events.append(dict(date=date,reason=reason,asset=asset,action="exclude"))
    for date in etf.index.union(benchmark.index).difference(expected):
        log(date,"outside_overlap_or_session_calendar","pair")
    for date in expected:
        if date not in ec or date not in bc:
            log(date,"different_trading_calendar","pair")
        for name, cal in [("etf",ec),("benchmark",bc)]:
            if date in cal and pd.isna(prices.loc[date,name]):
                log(date,name+"_missing",name)
    positions = np.flatnonzero(eligible.to_numpy())
    blocks = np.split(positions,np.where(np.diff(positions)!=1)[0]+1)
    block = max(blocks,key=len)
    selected = expected[block]
    for date in expected[eligible].difference(selected):
        log(date,"outside_selected_block","pair")
    if len(selected) < 3:
        raise ValueError("At least three consecutive common levels required; missing data not filled")
    out = prices.loc[selected].copy()
    returns = simple_returns(out)
    quality = dict(overlap_start=str(start.date()),overlap_end=str(end.date()),
        matched_price_count=int(prices.notna().all(axis=1).sum()),
        selected_price_count=len(out),matched_observation_count=len(returns),
        expected_session_count=len(expected),excluded_session_count=len(expected)-len(out),
        initial_undefined_return_count=1,
        sample_start=str(out.index[0].date()),sample_end=str(out.index[-1].date()),
        first_return_date=str(returns.index[0].date()),
        policy="longest_complete_union_calendar_block_earliest_tie")
    return Alignment(out,returns,quality,pd.DataFrame(events,columns=["date","reason","asset","action"]))

def _return_pair(etf,benchmark):
    if not isinstance(etf,pd.Series) or not isinstance(benchmark,pd.Series):
        raise ValueError("Aligned return Series required")
    _dates(etf.index,"etf"); _dates(benchmark.index,"benchmark")
    if not etf.index.equals(benchmark.index):
        raise ValueError("Return dates must match exactly; align levels first")
    x,y=etf.to_numpy(dtype=float),benchmark.to_numpy(dtype=float)
    if len(x)<2 or not np.isfinite(x).all() or not np.isfinite(y).all() or (x<=-1).any() or (y<=-1).any():
        raise ValueError("At least two complete finite simple returns greater than -1 required")
    return x,y

def tracking_statistics(etf,benchmark):
    """Return statistics for already aligned, comparable daily simple Series.

    TD = compounded ETF return minus compounded benchmark return, percentage
    points in decimal units. Annual TD is difference of geometric annual returns.
    TE = sample std(daily ETF minus benchmark) * sqrt(252). IR uses arithmetic
    active mean/std * sqrt(252), no risk-free subtraction. Zero TE gives NaN IR.
    The reporting layer must enforce comparability before publishing TD/TE/IR.
    """
    x,y=_return_pair(etf,benchmark)
    active=x-y
    sigma=0. if np.ptp(active)==0 else float(np.std(active,ddof=1))
    e_total=float(np.expm1(np.log1p(x).sum()))
    b_total=float(np.expm1(np.log1p(y).sum()))
    result=dict(etf_cumulative_return=e_total,benchmark_cumulative_return=b_total,
        tracking_difference=e_total-b_total,
        annualized_tracking_difference=annualized_return(x)-annualized_return(y),
        annualized_tracking_error=sigma*np.sqrt(252),
        information_ratio=float(active.mean()/sigma*np.sqrt(252)) if sigma else np.nan,
        information_ratio_status="ok" if sigma else "undefined_zero_tracking_error",
        etf_annualized_volatility=annualized_volatility(x),
        benchmark_annualized_volatility=annualized_volatility(y),
        etf_maximum_drawdown=maximum_drawdown(x),benchmark_maximum_drawdown=maximum_drawdown(y),
        matched_observation_count=len(x))
    if any(np.isinf(v) for v in result.values() if isinstance(v,(float,np.floating))):
        raise ValueError("Computed tracking statistic exceeds finite numeric range")
    return result

def rolling_tracking(etf,benchmark,window=63):
    """Return full trailing-window TE and Pearson correlation DataFrame.

    Input: identical dated finite daily simple Series and integer window >=2.
    Output: same dates; first window-1 rows NaN, no centered/future windows.
    Constant-window correlation is undefined (NaN).
    """
    _return_pair(etf,benchmark)
    if isinstance(window,bool) or not isinstance(window,int) or window<2:
        raise ValueError("window must be an integer >=2")
    active=etf-benchmark
    return pd.DataFrame({"rolling_tracking_error":active.rolling(window,min_periods=window).std(ddof=1)*np.sqrt(252),
                         "rolling_correlation":etf.rolling(window,min_periods=window).corr(benchmark)})
