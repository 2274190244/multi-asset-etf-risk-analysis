"""Five explicit index stages over a fixed, versioned ETF universe.

This is a retrospective adjusted-price research index, not a certified total-
return or executable fund. Observation dates and available-at cutoffs are separate.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .portfolios import equal_weights, inverse_volatility_weights
from .backtest import execute_trade

@dataclass
class IndexResult:
    """Daily levels, daily holdings, rebalance targets, eligibility and conventions."""
    daily: pd.DataFrame
    holdings: pd.DataFrame
    rebalances: pd.DataFrame
    targets: pd.DataFrame
    eligibility: pd.DataFrame
    metadata: dict

class IndexCalculationError(ValueError):
    """A path stopped; diagnostics and partial output are retained, not scored."""
    def __init__(self,message,diagnostics,partial):
        super().__init__(message)
        self.diagnostics=diagnostics
        self.partial=partial

def _dates(index,label):
    if not isinstance(index,pd.DatetimeIndex) or index.tz is not None or index.hasnans:
        raise ValueError(label+": normalized timezone-naive dates required")
    if not index.is_unique or not index.is_monotonic_increasing or not index.equals(index.normalize()):
        raise ValueError(label+": unique increasing normalized dates required")

def rebalance_dates(calendar,start,end,frequency):
    """Return actual last sessions of calendar months/quarters within bounds.

    calendar is an ordered complete exchange session index extending past the
    enclosing month/quarter. A terminal incomplete calendar period is not used
    as a fabricated period end. Only the calendar, never future prices, is read.
    """
    _dates(calendar,"calendar")
    if frequency not in ("monthly","quarterly"):
        raise ValueError("frequency must be monthly or quarterly")
    if pd.Timestamp(start)>pd.Timestamp(end):raise ValueError("Invalid date range")
    periods=calendar.to_period("M" if frequency=="monthly" else "Q")
    ends=pd.Series(calendar,index=periods).groupby(level=0).max()
    dates=[date for period,date in ends.items()
           if calendar[-1]>period.end_time.normalize() and pd.Timestamp(start)<=date<=pd.Timestamp(end)]
    return pd.DatetimeIndex(dates)

def assumed_availability(returns,calendar):
    """Return per-cell assumed timestamps: next exchange session at 09:00 China time.

    This is a labelled assumption, NOT historical publication-time evidence.
    The calendar must contain a following session for each observation.
    """
    _dates(calendar,"calendar");_dates(returns.index,"returns")
    positions=calendar.get_indexer(returns.index)
    if (positions<0).any() or (positions+1>=len(calendar)).any():
        raise ValueError("calendar must include every observation and its following session")
    stamps=calendar[positions+1]+pd.Timedelta(hours=9)
    return pd.DataFrame({s:stamps for s in returns.columns},index=returns.index)

def _validate_universe(universe,columns):
    symbols=[u["symbol"] for u in universe]
    if len(symbols)!=len(set(symbols)) or set(symbols)!=set(columns):
        raise ValueError("Universe must uniquely match return columns")
    for u in universe:
        if pd.isna(pd.Timestamp(u["eligible_from"])):raise ValueError("Unknown universe effective date")

def assess_eligibility(returns,available_at,universe,execution_date,estimation_window=252):
    """Return one auditable eligibility row per universe member at decision time.

    Uses exactly the last window calendar rows strictly before execution_date,
    available no later than 14:59 on that date. Missing/delayed cells invalidate
    that asset's window, not the entire universe. No backward search for enough
    nonmissing observations. Configuration effective dates are not listing dates.
    """
    if isinstance(estimation_window,bool) or not isinstance(estimation_window,int) or estimation_window<2:
        raise ValueError("estimation_window must be integer >=2")
    _validate_universe(universe,returns.columns)
    t=pd.Timestamp(execution_date);decision=t+pd.Timedelta(hours=14,minutes=59)
    history=returns.loc[returns.index<t].iloc[-estimation_window:]
    rows=[]
    for u in universe:
        symbol=u["symbol"];values=history[symbol].to_numpy(dtype=float)
        stamps=available_at.loc[history.index,symbol]
        reasons=[]
        if t<pd.Timestamp(u["eligible_from"]):reasons.append("outside_universe_effective_period")
        if u.get("eligible_until") and t>pd.Timestamp(u["eligible_until"]):reasons.append("outside_universe_effective_period")
        if len(history)<estimation_window:reasons.append("insufficient_history")
        if not np.isfinite(values).all():reasons.append("missing_history")
        if (values<=-1).any():reasons.append("invalid_return")
        late=stamps.isna() | (stamps>decision)
        if late.any():reasons.append("not_available_at_decision")
        rows.append(dict(execution_date=t,decision_time=decision,symbol=symbol,
            eligible=not reasons,reason=";".join(reasons) if reasons else "eligible",
            estimation_start=history.index[0] if len(history) else pd.NaT,
            estimation_end=history.index[-1] if len(history) else pd.NaT,
            history_count=len(history),missing_count=int((~np.isfinite(values)).sum()),
            unavailable_count=int(late.sum()),latest_available_at=stamps.max()))
    return pd.DataFrame(rows)

def index_weights(history,strategy):
    """Return finite long-only budget-one weights from eligible past daily returns.

    Equal weight or inverse sample volatility. No weight cap or volatility floor;
    zero-risk inverse-volatility input raises instead of silently altering rules.
    """
    if strategy=="equal_weight":return equal_weights(history.columns)
    if strategy=="inverse_volatility":return inverse_volatility_weights(history)
    raise ValueError("Unknown index weighting rule")

def concentration(weights):
    """Return maximum_weight and HHI=sum(w**2) for a finite long-only budget."""
    x=np.asarray(weights,dtype=float)
    if x.ndim!=1 or not len(x) or not np.isfinite(x).all() or (x<0).any() or not np.isclose(x.sum(),1,atol=1e-10,rtol=0):
        raise ValueError("Concentration requires finite long-only weights summing to one")
    return dict(maximum_weight=float(x.max()),hhi=float(x@x))

def run_index(returns,calendar,universe,*,strategy="equal_weight",frequency="monthly",
              estimation_window=252,available_at=None,base_level=1000.,inception_date=None):
    """Run the Universe -> Eligibility -> Weighting -> Rebalance -> Calculation stages.

    Input returns: complete session rows, asset-level NaNs retained for eligibility
    and held-position checks. Calendar extends beyond sample's enclosing quarter.
    Metadata distinguishes provided availability from next-session assumption.
    Output includes initial base row (undefined return), then t+1 performance.
    All frequencies default to the first quarter end with a full past window.
    Optional inception_date selects a later actual quarter-end with enough
    prior history, allowing common-date parameter comparisons.
    Subsequent targets use dates <t and available_at<=14:59t, execute close t,
    and first earn t+1. Non-rebalance holdings drift. No transaction costs.
    Missing held returns stop with IndexCalculationError carrying partial output.
    """
    if not isinstance(returns,pd.DataFrame) or returns.empty or not returns.columns.is_unique:
        raise ValueError("Nonempty unique-column return DataFrame required")
    _dates(returns.index,"returns");_dates(calendar,"calendar")
    _validate_universe(universe,returns.columns)
    if isinstance(estimation_window,bool) or not isinstance(estimation_window,int) or estimation_window<2:
        raise ValueError("estimation_window must be integer >=2")
    if strategy not in ("equal_weight","inverse_volatility"):raise ValueError("Unknown weighting rule")
    if not np.isfinite(base_level) or base_level<=0:raise ValueError("Base level must be finite positive")
    expected=calendar[(calendar>=returns.index[0]) & (calendar<=returns.index[-1])]
    if not returns.index.equals(expected):raise ValueError("Missing/unexpected calendar rows; no silent dropping")
    if calendar[-1]<=returns.index[-1].to_period("Q").end_time.normalize():
        raise ValueError("Calendar must extend beyond the sample's enclosing quarter")
    assumed=available_at is None
    available_at=assumed_availability(returns,calendar) if assumed else available_at.copy()
    if not available_at.index.equals(returns.index) or not available_at.columns.equals(returns.columns):
        raise ValueError("Availability must exactly match return dates/assets")
    for symbol in returns:
        if not pd.api.types.is_datetime64_any_dtype(available_at[symbol].dtype) or getattr(available_at[symbol].dt,"tz",None) is not None:
            raise ValueError("Availability must be timezone-naive China-local timestamps")
        observed_close=pd.Series(returns.index+pd.Timedelta(hours=15),index=returns.index)
        if (available_at[symbol]<observed_close).any():
            raise ValueError("A close return cannot be available before its observation close")
    quarters=rebalance_dates(calendar,returns.index[0],returns.index[-1],"quarterly")
    candidates=[d for d in quarters if (returns.index<d).sum()>=estimation_window]
    if inception_date is None:
        if not candidates:raise ValueError("No common quarter-end inception after full estimation window")
        inception=candidates[0]
    else:
        inception=pd.Timestamp(inception_date)
        if pd.isna(inception) or inception.tz is not None or inception!=inception.normalize() or inception not in quarters:
            raise ValueError("inception_date must be an actual input quarter-end")
        if (returns.index<inception).sum()<estimation_window:
            raise ValueError("Insufficient prior history for inception_date")
    evaluation=returns.index[returns.index>=inception]
    if len(evaluation)<3:raise ValueError("Need at least two returns after inception")
    schedule=set(rebalance_dates(calendar,inception,returns.index[-1],frequency))|{inception}
    symbols=list(returns.columns);current=np.zeros(len(symbols));level=float(base_level)
    daily=[];holdings=[];rebalances=[];targets=[];eligibility=[]
    metadata=dict(strategy=strategy,frequency=frequency,estimation_window=estimation_window,
        inception=str(inception.date()),first_return_date=str(evaluation[1].date()),
        end_date=str(evaluation[-1].date()),base_level=base_level,
        observation_rule="dates strictly before execution t; available by t14:59",
        execution_rule="close t; target first earns t+1",
        availability_policy="assumed_next_session_09:00" if assumed else "provided_timestamps_not_independently_certified",
        timezone="Asia/Shanghai local naive",daily_rebalancing=False,cost_bps=0,
        initial_turnover_rule="initial cash-to-index separately reported; excluded from maintenance turnover",
        universe=universe,status="complete",terminal_liquidation=False)
    def result():
        frame=pd.DataFrame(daily)
        if not frame.empty:frame=frame.set_index("date")
        return IndexResult(frame,pd.DataFrame(holdings),pd.DataFrame(rebalances),
                           pd.DataFrame(targets),pd.DataFrame(eligibility),dict(metadata))
    def fail(date,message,affected):
        metadata["status"]="failed"
        raise IndexCalculationError(message,dict(date=str(date.date()),reason=message,affected_assets=list(affected)),result())
    for date in evaluation:
        initial=date==inception
        start=current.copy();values=returns.loc[date].to_numpy(dtype=float)
        held=start>0
        if not initial and ((~np.isfinite(values[held])).any() or (values[held]<=-1).any()):
            bad=[s for j,s in enumerate(symbols) if held[j] and (not np.isfinite(values[j]) or values[j]<=-1)]
            fail(date,"Missing or invalid held-asset return; path stopped",bad)
        gain=0. if initial else float(start[held]@values[held])
        if not np.isfinite(gain) or gain<=-1:fail(date,"Invalid index gain",symbols)
        level*=1+gain
        if not np.isfinite(level) or level<=0:fail(date,"Invalid index level",symbols)
        pre=start.copy()
        if not initial:
            pre[held]=start[held]*(1+values[held])/(1+gain)
            concentration(pre)
        current=pre.copy();turnover=0.
        is_rebalance=date in schedule and date!=evaluation[-1]
        if is_rebalance:
            report=assess_eligibility(returns,available_at,universe,date,estimation_window)
            eligibility.extend(report.to_dict("records"))
            eligible=report.loc[report.eligible,"symbol"].tolist()
            if not eligible:fail(date,"No eligible constituents",symbols)
            history=returns.loc[returns.index<date,eligible].iloc[-estimation_window:]
            try:
                selected=index_weights(history,strategy)
                target=selected.reindex(symbols,fill_value=0.).to_numpy(dtype=float)
                concentration(target)
            except ValueError as error:fail(date,str(error),eligible)
            invalid=[s for j,s in enumerate(symbols) if target[j]>0 and (not np.isfinite(values[j]) or values[j]<=-1)]
            if invalid:fail(date,"Missing execution-date return/valuation for target asset",invalid)
            turnover=execute_trade(pre,target,0)["turnover"]
            current=target
            next_date=evaluation[evaluation.get_loc(date)+1]
            rebalances.append(dict(execution_date=date,decision_time=date+pd.Timedelta(hours=14,minutes=59),
                estimation_start=history.index[0],estimation_end=history.index[-1],
                estimation_count=len(history),first_effective_return_date=next_date,
                initial=initial,turnover=turnover,constituent_count=len(eligible),
                target_maximum_weight=float(target.max()),target_hhi=float(target@target)))
            for j,symbol in enumerate(symbols):
                targets.append(dict(execution_date=date,symbol=symbol,eligible=symbol in eligible,
                    pretrade_weight=pre[j],target_weight=target[j]))
        stats=concentration(current)
        daily.append(dict(date=date,index_level=level,index_return=np.nan if initial else gain,
            is_initial=initial,is_rebalance=is_rebalance,turnover=turnover,
            maintenance_turnover=0. if initial else turnover,**stats))
        for j,symbol in enumerate(symbols):
            holdings.append(dict(date=date,symbol=symbol,start_weight=start[j],
                pretrade_weight=pre[j],end_weight=current[j]))
    return result()
