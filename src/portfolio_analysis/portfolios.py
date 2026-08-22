"""Portfolio construction helpers for wide daily return data."""

import numpy as np
import pandas as pd
from scipy.optimize import minimize


_WEIGHT_TOLERANCE = 1e-6


class PortfolioOptimizationError(ValueError):
    """Raised when minimum-volatility portfolio construction cannot complete."""


def equal_weights(columns) -> pd.Series:
    """Return an equally weighted, fully invested portfolio for ``columns``."""
    index = pd.Index(columns)
    if index.empty:
        raise ValueError("At least one portfolio column is required")
    if index.has_duplicates:
        raise ValueError("Portfolio columns must be unique")

    return pd.Series(1.0 / len(index), index=index, dtype=float)


def minimum_volatility_weights(returns: pd.DataFrame) -> pd.Series:
    """Optimize long-only weights that minimize daily portfolio variance."""
    _validate_returns(returns)

    covariance = returns.cov().to_numpy(dtype=float)
    if not np.isfinite(covariance).all():
        raise PortfolioOptimizationError("Return covariance must be finite")

    initial_weights = equal_weights(returns.columns).to_numpy()
    try:
        result = minimize(
            lambda weights: float(weights @ covariance @ weights),
            initial_weights,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * len(initial_weights),
            constraints={"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0},
        )
    except Exception as error:
        raise PortfolioOptimizationError(
            f"Minimum-volatility optimization raised an exception: {error}"
        ) from error

    success, message = _optimization_status(result)
    if not success:
        raise PortfolioOptimizationError(f"Minimum-volatility optimization failed: {message}")

    optimized_weights = _optimization_weights(result)
    if (
        optimized_weights.shape != initial_weights.shape
        or not np.isfinite(optimized_weights).all()
        or (optimized_weights < 0.0).any()
        or (optimized_weights > 1.0).any()
        or not np.isclose(
            optimized_weights.sum(), 1.0, atol=_WEIGHT_TOLERANCE, rtol=0.0
        )
    ):
        raise PortfolioOptimizationError("Minimum-volatility optimization returned invalid weights")

    return pd.Series(optimized_weights, index=returns.columns, dtype=float)


def portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Calculate daily portfolio returns using weights aligned by asset symbol."""
    if not isinstance(returns, pd.DataFrame):
        raise ValueError("Returns must be a pandas DataFrame")
    if not isinstance(weights, pd.Series):
        raise ValueError("Weights must be a pandas Series")
    if returns.columns.has_duplicates or weights.index.has_duplicates:
        raise ValueError("Return columns and weights must be unique")
    if set(returns.columns) != set(weights.index):
        raise ValueError("Weight symbols must match return columns")

    aligned_weights = weights.reindex(returns.columns).astype(float)
    if not np.isfinite(aligned_weights.to_numpy()).all():
        raise ValueError("Weights must be finite")

    return returns @ aligned_weights


def _validate_returns(returns: pd.DataFrame) -> None:
    """Validate enough finite wide daily return observations for covariance estimation."""
    if not isinstance(returns, pd.DataFrame):
        raise PortfolioOptimizationError("Returns must be a pandas DataFrame")
    if returns.empty or returns.shape[1] == 0:
        raise PortfolioOptimizationError("Returns must contain at least one asset")
    if returns.columns.has_duplicates:
        raise PortfolioOptimizationError("Return columns must be unique")
    if len(returns) < 2:
        raise PortfolioOptimizationError("At least two complete daily observations are required")

    try:
        values = returns.to_numpy(dtype=float)
    except (TypeError, ValueError) as error:
        raise PortfolioOptimizationError("Returns must be finite numeric values") from error

    if not np.isfinite(values).all():
        raise PortfolioOptimizationError("Returns must contain only finite values")


def _optimization_status(result) -> tuple[bool, str]:
    """Return validated success metadata from a SciPy optimization result."""
    try:
        success = result.success
        message = result.message
    except Exception as error:
        raise PortfolioOptimizationError(
            "Minimum-volatility optimization returned a malformed result: "
            "missing success or message"
        ) from error

    if not isinstance(success, (bool, np.bool_)) or not isinstance(message, str):
        raise PortfolioOptimizationError(
            "Minimum-volatility optimization returned a malformed result: "
            "invalid success or message"
        )

    return bool(success), message


def _optimization_weights(result) -> np.ndarray:
    """Return validated numeric weights from a successful optimizer result."""
    try:
        return np.asarray(result.x, dtype=float)
    except Exception as error:
        raise PortfolioOptimizationError(
            "Minimum-volatility optimization returned a malformed result: invalid x"
        ) from error
