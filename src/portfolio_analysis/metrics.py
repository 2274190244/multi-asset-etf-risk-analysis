"""Daily simple-return metrics; annualization uses 252 trading days.

Missing observations are never implicitly removed by a risk statistic. VaR and
CVaR use signed losses, so an entirely positive tail may have negative loss.
"""
import numpy as np
import pandas as pd

_TRADING_DAYS_PER_YEAR = 252
_MINIMUM_OBSERVATIONS = 30
RISK_METRICS = ('annualized_return', 'annualized_volatility', 'sharpe_ratio',
                'maximum_drawdown', 'historical_var', 'historical_cvar',
                'downside_volatility', 'sortino_ratio', 'calmar_ratio')

class MetricError(ValueError):
    """Return inputs cannot support the requested statistic."""

def _values(returns, minimum=1):
    try:
        x = np.asarray(returns, dtype=float)
    except (TypeError, ValueError) as exc:
        raise MetricError('Returns must be numeric') from exc
    if x.ndim != 1 or len(x) < minimum:
        raise MetricError(f'At least {minimum} observations are required')
    if not np.isfinite(x).all():
        raise MetricError('Returns must be finite with no missing observations')
    if (x <= -1).any():
        raise MetricError('Daily returns must be greater than -1.0')
    return x

def _finite_ratio(numerator, denominator):
    if denominator == 0:
        return np.nan
    with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
        result = float(np.divide(numerator, denominator))
    if not np.isfinite(result):
        raise MetricError('Computed ratio exceeds finite numeric range')
    return result

def _daily_rate(annual):
    if not np.isfinite(annual) or annual <= -1:
        raise MetricError('Annual rate must be finite and greater than -1')
    return float(np.expm1(np.log1p(annual) / 252))

def _price_returns(prices, logarithmic=False):
    x = np.asarray(prices, dtype=float)
    if x.ndim not in (1, 2) or len(x) < 2 or not np.isfinite(x).all() or (x <= 0).any():
        raise MetricError('Prices require at least two finite positive observations without gaps')
    with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
        result = np.log(x[1:] / x[:-1]) if logarithmic else x[1:] / x[:-1] - 1
    if not np.isfinite(result).all():
        raise MetricError('Computed returns exceed finite numeric range')
    if isinstance(prices, pd.Series):
        return pd.Series(result, index=prices.index[1:], name=prices.name)
    if isinstance(prices, pd.DataFrame):
        return pd.DataFrame(result, index=prices.index[1:], columns=prices.columns)
    return result

def simple_returns(prices):
    """Adjacent simple price returns, without annualization.

    Parameters
    ----------
    prices : one- or two-dimensional array, Series, or DataFrame
        At least two finite, positive, complete price observations in time order.

    Returns
    -------
    array, Series, or DataFrame
        Decimal returns P[t]/P[t-1]-1; same container and trailing index. The
        undefined first observation is omitted. Invalid/overflowing values raise
        MetricError; gaps are never removed or filled.
    """
    return _price_returns(prices)

def log_returns(prices):
    """Adjacent logarithmic price returns, without annualization.

    Parameters
    ----------
    prices : one- or two-dimensional array, Series, or DataFrame
        At least two finite positive prices in time order, without missing cells.

    Returns
    -------
    array, Series, or DataFrame
        Dimensionless log(P[t]/P[t-1]), retaining the trailing input index.
        These are log returns, not simple returns accepted by risk functions.
        Invalid inputs or nonfinite computed ratios raise MetricError.
    """
    return _price_returns(prices, logarithmic=True)

def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Pivot closing prices into daily simple returns without filling gaps.

    Parameters
    ----------
    prices : DataFrame
        Long table with date, symbol, close columns. Observed prices must be
        finite and positive; missing prices are retained for explicit auditing.

    Returns
    -------
    DataFrame
        Date-indexed decimal daily returns, one column per symbol. Only the
        first structural undefined row is removed; every later row remains,
        including entirely missing rows. attrs['audit'] records that removal
        and every missing return cell. No annualization is applied.
    """
    missing = {'date', 'symbol', 'close'}.difference(prices.columns)
    if missing:
        raise ValueError(f"Price frame is missing required columns: {', '.join(sorted(missing))}")
    closing = prices.pivot(index='date', columns='symbol', values='close').sort_index()
    observed = closing.to_numpy(dtype=float)
    if np.isinf(observed).any() or (observed <= 0).any():
        raise MetricError('Observed closing prices must be finite and positive')
    with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
        result = closing.pct_change(fill_method=None).iloc[1:].copy()
    if np.isinf(result.to_numpy(dtype=float)).any():
        raise MetricError('Computed daily returns exceed finite numeric range')
    result.attrs['audit'] = [{'action': 'remove_initial_undefined_return', 'rows': min(1, len(closing))},
                             {'action': 'retain_missing_returns', 'count': int(result.isna().sum().sum()),
                              'cells': [{'date': str(date), 'symbol': str(symbol)}
                                        for date, row in result.isna().iterrows()
                                        for symbol, missing in row.items() if missing]}]
    return result

def annualized_return(returns):
    """Geometric annual return under a 252-trading-day convention.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns, each greater than -1.

    Returns
    -------
    float
        Decimal annual return, prod(1+r)**(252/n)-1. Invalid input or output
        overflow raises MetricError; no observations are silently removed.
    """
    x = _values(returns)
    with np.errstate(over='ignore'):
        result = float(np.expm1(np.log1p(x).mean() * 252))
    if not np.isfinite(result):
        raise MetricError('Annualized return exceeds finite numeric range')
    return result

def annualized_volatility(returns):
    """Sample volatility annualized by sqrt(252).

    Parameters
    ----------
    returns : one-dimensional array or Series
        At least two complete finite daily simple returns greater than -1.

    Returns
    -------
    float
        Decimal annual sample standard deviation (ddof=1). Constant returns
        give zero; invalid inputs or nonfinite output raise MetricError.
    """
    with np.errstate(over='ignore', invalid='ignore'):
        result = float(np.std(_values(returns, 2), ddof=1) * np.sqrt(252))
    if not np.isfinite(result):
        raise MetricError('Computed volatility exceeds finite numeric range')
    return result

def sharpe_ratio(returns, risk_free_rate=0.02):
    """Daily excess-return Sharpe ratio annualized by sqrt(252).

    Parameters
    ----------
    returns : one-dimensional array or Series
        At least two complete finite daily simple returns greater than -1.
    risk_free_rate : float, default 0.02
        Effective annual decimal rate, finite and greater than -1. Converted
        to the daily rate (1+rate)**(1/252)-1 before subtraction.

    Returns
    -------
    float
        Mean daily excess / sample daily excess standard deviation * sqrt(252).
        Zero computed excess volatility (including numeric underflow) gives NaN; invalid or nonfinite statistics raise
        MetricError. The numerator is arithmetic, not compounded annual return.
    """
    x = _values(returns, 2)
    excess = x - _daily_rate(risk_free_rate)
    # The numerator and denominator both use daily excess returns.
    with np.errstate(over='ignore', invalid='ignore'):
        sigma = np.std(excess, ddof=1)
        mean_excess = excess.mean()
    if not np.isfinite(sigma) or not np.isfinite(mean_excess):
        raise MetricError('Computed excess statistics exceed finite numeric range')
    if sigma == 0 or np.ptp(excess) == 0:
        return np.nan
    return _finite_ratio(mean_excess * np.sqrt(252), sigma)

def maximum_drawdown(returns):
    """Deepest cumulative wealth drawdown, including initial wealth one.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1, ordered
        chronologically. No annualization or 252-day scaling is applied.

    Returns
    -------
    float
        Nonpositive decimal peak-to-trough decline. Initial losses count;
        an increasing wealth path gives zero. Invalid inputs raise MetricError.
    """
    log_wealth = np.r_[0., np.cumsum(np.log1p(_values(returns)))]
    return float(np.expm1(log_wealth - np.maximum.accumulate(log_wealth)).min())

def return_quantile(returns, probability=0.05):
    """Linearly interpolated empirical daily return quantile.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1.
    probability : float, default 0.05
        Quantile probability in [0, 1]. Sorted values occupy knots i/(n-1).

    Returns
    -------
    float
        Decimal daily return, using linear interpolation between knots; no
        annualization. A singleton gives its sole value. Invalid inputs raise
        MetricError.
    """
    if not np.isfinite(probability) or not 0 <= probability <= 1:
        raise MetricError('Quantile probability must be between 0 and 1')
    return float(np.quantile(_values(returns), probability, method='linear'))

def _tail(confidence):
    if not np.isfinite(confidence) or not 0 < confidence < 1:
        raise MetricError('Confidence must be strictly between 0 and 1')
    return 1-confidence

def historical_var(returns, confidence=0.95):
    """Signed daily historical value at risk using a linear quantile.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1.
    confidence : float, default 0.95
        Finite confidence strictly between zero and one.

    Returns
    -------
    float
        Negative return quantile at 1-confidence, in decimal daily loss units.
        No annualization or zero clamp: positive tail returns give negative VaR.
        Quantiles use linear interpolation; invalid inputs raise MetricError.
    """
    return -return_quantile(returns, _tail(confidence))

def historical_cvar(returns, confidence=0.95):
    """Signed daily expected shortfall of the linear empirical quantile.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1.
    confidence : float, default 0.95
        Finite confidence strictly between zero and one.

    Returns
    -------
    float
        Negative integral of the piecewise-linear empirical return quantile on
        [0, 1-confidence], divided by 1-confidence, in decimal daily loss units.
        Exact trapezoids integrate the SAME quantile used by VaR. This differs
        from averaging observations below a threshold. No annualization or
        zero clamp is applied; invalid inputs raise MetricError.
    """
    alpha = _tail(confidence)
    x = np.sort(_values(returns))
    knots = np.linspace(0, 1, len(x))
    p = np.r_[knots[knots < alpha], alpha]
    q = np.interp(p, knots, x)
    return float(-np.sum(np.diff(p)*(q[:-1]+q[1:])/2)/alpha)

def downside_volatility(returns, target_return=0.0):
    """Annual lower-partial-moment volatility over all observations.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1.
    target_return : float, default 0
        Effective annual decimal target, finite and greater than -1, converted
        to a daily target using (1+target)**(1/252)-1.

    Returns
    -------
    float
        sqrt(252 * mean(min(r-daily_target, 0)**2)), in annual decimal units.
        The denominator includes every observation, including above-target
        days. No downside gives zero; invalid inputs raise MetricError.
    """
    downside = np.minimum(_values(returns)-_daily_rate(target_return), 0)
    with np.errstate(over='ignore', invalid='ignore'):
        result = float(np.sqrt(np.mean(downside**2)*252))
    if not np.isfinite(result):
        raise MetricError('Computed downside volatility exceeds finite numeric range')
    return result

def sortino_ratio(returns, target_return=0.0):
    """Arithmetic excess return divided by annual downside volatility.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite daily simple returns greater than -1.
    target_return : float, default 0
        Effective annual decimal target, converted to an effective daily rate
        using 252 trading days; must be finite and greater than -1.

    Returns
    -------
    float
        252 * mean(r-daily_target) / downside_volatility, dimensionless.
        All observations contribute to the downside moment. Zero downside
        volatility gives NaN; invalid inputs raise MetricError.
    """
    x = _values(returns)
    risk = downside_volatility(x, target_return)
    with np.errstate(over='ignore', invalid='ignore'):
        numerator = (x.mean()-_daily_rate(target_return))*252
    if not np.isfinite(numerator):
        raise MetricError('Computed excess return exceeds finite numeric range')
    return _finite_ratio(numerator, risk)

def calmar_ratio(returns):
    """Geometric annual return divided by absolute maximum drawdown.

    Parameters
    ----------
    returns : one-dimensional array or Series
        Nonempty complete finite chronological daily simple returns above -1.

    Returns
    -------
    float
        Dimensionless ratio using 252-day geometric annualization and initial
        wealth one. Zero drawdown gives NaN; invalid inputs or nonfinite ratios
        raise MetricError.
    """
    risk = abs(maximum_drawdown(returns))
    return _finite_ratio(annualized_return(returns), risk)

def asset_metrics(returns, risk_free_rate=0.02, *, minimum_observations=30):
    """Calculate nine statistics from complete daily simple return columns.

    Parameters
    ----------
    returns : DataFrame
        Chronologically ordered daily simple returns, one column per asset.
        All cells must be finite and greater than -1; no missing cells trimmed.
    risk_free_rate : float, default 0.02
        Effective annual decimal risk-free rate for Sharpe only.
    minimum_observations : int, default 30
        Required observations per asset; must be at least two.

    Returns
    -------
    DataFrame
        Asset rows and RISK_METRICS numeric columns, original five fields first.
        Return/volatility fields use annual decimal units and 252 trading days;
        drawdown, VaR and CVaR use unannualized decimal units; ratios are
        dimensionless. Sortino/downside use a zero target. Undefined zero-risk
        ratios are NaN and explained in attrs['metric_status']; missing policy
        is recorded in attrs['missing_data_policy']. Invalid data raises
        MetricError naming the asset; no observations are silently removed.
    """
    _daily_rate(risk_free_rate)
    if not isinstance(minimum_observations, int) or minimum_observations < 2:
        raise MetricError('minimum_observations must be an integer of at least two')
    metrics, status = {}, {}
    for symbol, series in returns.items():
        try:
            if series.count() < minimum_observations:
                raise MetricError(f'At least {minimum_observations} daily observations are required')
            x = _values(series, minimum_observations)
            metrics[symbol] = {name: (sharpe_ratio(x, risk_free_rate) if name == 'sharpe_ratio'
                                     else globals()[name](x)) for name in RISK_METRICS}
            status[symbol] = {name: ('ok' if np.isfinite(value) else
                              {'sharpe_ratio': 'undefined_zero_volatility',
                               'sortino_ratio': 'undefined_zero_downside_volatility',
                               'calmar_ratio': 'undefined_zero_drawdown'}[name])
                              for name, value in metrics[symbol].items()}
        except MetricError as exc:
            raise MetricError(f'{symbol}: {exc}') from exc
    result = pd.DataFrame.from_dict(metrics, orient='index', columns=RISK_METRICS)
    result.attrs['metric_status'] = status
    result.attrs['missing_data_policy'] = 'strict; no rows removed'
    return result
