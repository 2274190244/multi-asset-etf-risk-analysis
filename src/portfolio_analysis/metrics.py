"""Return and risk metrics for normalized asset price data."""

import numpy as np
import pandas as pd


_TRADING_DAYS_PER_YEAR = 252
_MINIMUM_OBSERVATIONS = 30


class MetricError(ValueError):
    """Raised when return data is insufficient for a risk metric."""


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Convert normalized closing prices into a wide table of daily returns."""
    required_columns = {"date", "symbol", "close"}
    missing_columns = required_columns.difference(prices.columns)
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise ValueError(f"Price frame is missing required columns: {names}")

    closing_prices = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    return closing_prices.pct_change(fill_method=None).dropna(how="all")


def maximum_drawdown(returns: pd.Series) -> float:
    """Return the deepest decline from a running cumulative-wealth peak."""
    wealth = (1.0 + returns.dropna()).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    return float(drawdown.min())


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Return historical value at risk as a positive loss."""
    return float(-returns.dropna().quantile(1.0 - confidence))


def asset_metrics(returns: pd.DataFrame, risk_free_rate: float = 0.02) -> pd.DataFrame:
    """Calculate annualized return, risk, and downside statistics per asset."""
    observation_counts = returns.count()
    insufficient = observation_counts[observation_counts < _MINIMUM_OBSERVATIONS]
    if not insufficient.empty:
        names = ", ".join(map(str, insufficient.index))
        raise MetricError(
            f"At least {_MINIMUM_OBSERVATIONS} daily observations are required for: {names}"
        )

    invalid_assets = returns.columns[returns.le(-1.0).any()]
    if not invalid_assets.empty:
        names = ", ".join(map(str, invalid_assets))
        raise MetricError(
            f"Daily returns must be greater than -1.0 for: {names}"
        )

    metrics = {}
    for symbol, series in returns.items():
        observed = series.dropna()
        annualized_return = (1.0 + observed).prod() ** (
            _TRADING_DAYS_PER_YEAR / len(observed)
        ) - 1.0
        annualized_volatility = observed.std(ddof=1) * np.sqrt(_TRADING_DAYS_PER_YEAR)
        metrics[symbol] = {
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "sharpe_ratio": (annualized_return - risk_free_rate)
            / annualized_volatility,
            "maximum_drawdown": maximum_drawdown(observed),
            "historical_var": historical_var(observed),
        }

    return pd.DataFrame.from_dict(metrics, orient="index").replace(
        [np.inf, -np.inf], np.nan
    )
