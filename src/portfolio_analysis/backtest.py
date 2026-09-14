"""Close-executed rolling portfolios with explicit self-financing transactions.

Prices/returns must already pass common-calendar validation. No observations are
filled or dropped. Targets at close t use only returns strictly before t.
"""
from dataclasses import dataclass
import json
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from portfolio_analysis.portfolios import (
    equal_weights, minimum_volatility_weights, inverse_volatility_weights,
    _validate_returns,
)

STRATEGIES = ("equal_weight", "minimum_variance", "inverse_volatility")
COST_BPS = (0, 5, 10, 20)


@dataclass
class BacktestResult:
    """Daily performance, daily holdings, execution ledger, targets and conventions."""
    daily: pd.DataFrame
    weights: pd.DataFrame
    trades: pd.DataFrame
    targets: pd.DataFrame
    metadata: dict


def _weights(values, *, cash_allowed=False):
    """Validate finite long-only risky fractions; return a defensive numeric copy."""
    w = np.asarray(values, dtype=float).copy()
    if w.ndim != 1 or not len(w) or not np.isfinite(w).all() or (w < 0).any():
        raise ValueError("Weights must be a nonempty finite nonnegative vector")
    if cash_allowed and np.all(w == 0):
        return w
    if not np.isclose(w.sum(), 1., atol=1e-6, rtol=0):
        raise ValueError("Risky weights must sum to one (or all zero at initial cash)")
    return w / w.sum()


def execute_trade(pretrade, target, cost_bps):
    """Execute a fully invested target with fees paid from portfolio wealth.

    Parameters
    ----------
    pretrade, target : one-dimensional arrays
        Risky fractions of pretrade wealth and desired post-fee wealth.
        Pretrade can be all zero for initial cash, otherwise must sum to one.
    cost_bps : {0, 5, 10, 20}
        Fee per actual bought OR sold notional, in basis points.

    Returns
    -------
    dict
        Cost, buy and sell fractions of PRETRADE wealth; nominal half-L1
        turnover including cash; actual total traded fraction. Solves
        q = k * sum(abs((1-q)*target-pretrade)), so post-fee targets are funded.
    """
    pre = _weights(pretrade, cash_allowed=True)
    target = _weights(target)
    if pre.shape != target.shape:
        raise ValueError("Pretrade and target dimensions must match")
    if isinstance(cost_bps, bool) or cost_bps not in COST_BPS:
        raise ValueError("cost_bps must be one of 0, 5, 10, 20")
    k = float(cost_bps) / 10000
    q = 0. if k == 0 else brentq(
        lambda q: q-k*np.abs((1-q)*target-pre).sum(), 0., 1.,
        xtol=1e-15, rtol=1e-14)
    delta = (1-q)*target-pre
    buy = float(np.maximum(delta, 0).sum())
    sell = float(np.maximum(-delta, 0).sum())
    if not np.isclose(q, k*(buy+sell), atol=1e-13, rtol=1e-10):
        raise ValueError("Self-financing fee equation failed")
    return {
        "cost_fraction": float(q), "buy_fraction": buy, "sell_fraction": sell,
        "traded_fraction": buy+sell,
        "turnover": float((np.abs(target-pre).sum()+abs(1-pre.sum()))/2),
    }


def run_backtest(returns, *, strategy="equal_weight", estimation_window=252,
                 rebalance_every=21, cost_bps=0, inception_date=None):
    """Run one rolling strategy; retain all common evaluation dates.

    Parameters
    ----------
    returns : DataFrame
        Complete finite daily simple returns > -1, unique increasing DatetimeIndex.
        The caller must validate the trading calendar before supplying data.
    strategy : str
        equal_weight, minimum_variance, or inverse_volatility.
    estimation_window : int, default 252
        Number of returns strictly preceding each execution date.
    rebalance_every : {21, 63}
        Trading-day intervals from first execution, not calendar month/quarter.
    cost_bps : {0, 5, 10, 20}
        Per-side proportional cost on actual traded notional.

    inception_date : date-like, optional
        Common execution anchor; must be a return-index session with at least
        estimation_window earlier rows and two following returns. Default
        preserves execution at index[window]. Cadence is anchored here.

    Returns
    -------
    BacktestResult
        Default execution is index[window]; an explicit inception overrides it.
        The first return is always the following session.
        Initial fee is included in first net return and separately identified;
        no synthetic warm-up return or terminal liquidation is inserted.
        Failures raise with strategy/date, never silently change strategy.
    """
    _validate_returns(returns)
    if not isinstance(returns.index, pd.DatetimeIndex) or returns.index.hasnans:
        raise ValueError("Returns require nonmissing DatetimeIndex")
    if not returns.index.is_unique or not returns.index.is_monotonic_increasing:
        raise ValueError("Returns require unique increasing dates")
    if isinstance(estimation_window, bool) or not isinstance(estimation_window, int) or estimation_window < 2:
        raise ValueError("estimation_window must be an integer >= 2")
    if len(returns) < estimation_window+3:
        raise ValueError("Need a full estimation window, execution day and at least two returns")
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    if isinstance(rebalance_every, bool) or rebalance_every not in (21, 63):
        raise ValueError("rebalance_every must be 21 or 63 trading days")
    if isinstance(cost_bps, bool) or cost_bps not in COST_BPS:
        raise ValueError("cost_bps must be one of 0, 5, 10, 20")
    choose = {
        "equal_weight": lambda history: equal_weights(history.columns),
        "minimum_variance": minimum_volatility_weights,
        "inverse_volatility": inverse_volatility_weights,
    }[strategy]
    dates, columns = returns.index, returns.columns
    execution_pos = estimation_window
    if inception_date is not None:
        inception = pd.Timestamp(inception_date)
        if pd.isna(inception) or inception.tz is not None or inception != inception.normalize() or inception not in dates:
            raise ValueError("inception_date must be a normalized input session")
        execution_pos = dates.get_loc(inception)
        if execution_pos < estimation_window:
            raise ValueError("Insufficient prior history for inception_date")
        if len(dates)-execution_pos < 3:
            raise ValueError("Need two returns after inception_date")
    values = returns.to_numpy(dtype=float)
    current = np.zeros(len(columns))
    gross_nav = net_nav = previous_report_nav = 1.
    initial_cost = initial_turnover = initial_traded = 0.
    daily, holdings, trades, targets = [], [], [], []
    for i in range(execution_pos, len(returns)):
        date = dates[i]
        initial = i == execution_pos
        start = current.copy()
        gain = 0. if initial else float(start @ values[i])
        if not np.isfinite(gain) or gain <= -1:
            raise ValueError(f"Invalid portfolio return at {date}")
        gross_nav *= 1+gain
        net_nav *= 1+gain
        if not np.isfinite([gross_nav, net_nav]).all() or min(gross_nav, net_nav) <= 0:
            raise ValueError(f"Invalid accumulated wealth at {date}")
        pre = start if initial else _weights(start*(1+values[i])/(1+gain))
        current = pre.copy()
        rebalance = i < len(returns)-1 and (i-execution_pos) % rebalance_every == 0
        fee = turnover = traded_amount = 0.
        if rebalance:
            history = returns.iloc[i-estimation_window:i].copy()
            try:
                target_series = choose(history)
                target = _weights(target_series.reindex(columns).to_numpy())
                execution = execute_trade(pre, target, cost_bps)
            except Exception as error:
                raise ValueError(f"{strategy} execution {date.date()} failed: {error}") from error
            pre_nav = net_nav
            fee = pre_nav*execution["cost_fraction"]
            turnover = execution["turnover"]
            traded_amount = pre_nav*execution["traded_fraction"]
            net_nav = pre_nav*(1-execution["cost_fraction"])
            current = target
            trades.append({
                "execution_date": date, "estimation_start": history.index[0],
                "estimation_end": history.index[-1], "estimation_count": len(history),
                "first_effective_return_date": dates[i+1], "initial": initial,
                "turnover": turnover, "pretrade_net_nav": pre_nav,
                "posttrade_net_nav": net_nav, "transaction_cost": fee,
                "buy_amount": pre_nav*execution["buy_fraction"],
                "sell_amount": pre_nav*execution["sell_fraction"],
                "traded_amount": traded_amount, "cost_fraction": execution["cost_fraction"],
                "target_maximum_weight": float(target.max()),
                "target_hhi": float(target @ target),
                "optimization": json.dumps(target_series.attrs.get("optimization", {}), sort_keys=True),
            })
            for j, symbol in enumerate(columns):
                targets.append({"execution_date": date, "symbol": symbol,
                    "pretrade_weight": pre[j], "target_weight": target[j],
                    "trade_amount": pre_nav*((1-execution["cost_fraction"])*target[j]-pre[j])})
        if initial:
            initial_cost, initial_turnover, initial_traded = fee, turnover, traded_amount
            continue
        first = i == execution_pos+1
        net_return = gain if cost_bps == 0 else net_nav/previous_report_nav-1
        previous_report_nav = net_nav
        daily.append({
            "date": date, "gross_return": gain, "net_return": net_return,
            "gross_nav": gross_nav, "net_nav": net_nav, "is_rebalance": rebalance,
            "turnover": turnover+(initial_turnover if first else 0.),
            "transaction_cost": fee+(initial_cost if first else 0.),
            "initial_transaction_cost": initial_cost if first else 0.,
            "execution_transaction_cost": fee,
            "traded_amount": traded_amount+(initial_traded if first else 0.),
            "maximum_weight": float(current.max()), "hhi": float(current @ current),
        })
        for j, symbol in enumerate(columns):
            holdings.append({"date": date, "symbol": symbol,
                "start_weight": start[j], "pretrade_weight": pre[j], "end_weight": current[j]})
    metadata = {
        "strategy": strategy, "estimation_window": estimation_window,
        "rebalance_every": rebalance_every, "cost_bps": cost_bps,
        "evaluation_start": str(dates[execution_pos+1].date()),
        "evaluation_end": str(dates[-1].date()), "evaluation_count": len(daily),
        "execution_rule": "close t; estimate through t-1; target first earns t+1",
        "initial_fee_rule": "actual execution ledger date; allocated to first net return",
        "terminal_liquidation": False, "daily_rebalancing": False,
        "weight_roundoff": "validated sum tolerance 1e-6 then normalized for exact budget",
    }
    return BacktestResult(pd.DataFrame(daily).set_index("date"), pd.DataFrame(holdings),
                          pd.DataFrame(trades), pd.DataFrame(targets), metadata)
