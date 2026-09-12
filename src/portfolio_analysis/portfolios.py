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

    covariance = returns.cov().to_numpy(dtype=float) * 252.0
    if not np.isfinite(covariance).all():
        raise PortfolioOptimizationError("Return covariance must be finite")

    # Normalize annual covariance to unit maximum variance for stable tolerances.
    scale = max(float(np.diag(covariance).max()), np.finfo(float).tiny)
    objective_covariance = covariance / scale
    initial_weights = equal_weights(returns.columns).to_numpy()
    try:
        result = minimize(
            lambda weights: float(weights @ objective_covariance @ weights),
            initial_weights,
            method="SLSQP",
            jac=lambda weights: 2.0 * objective_covariance @ weights,
            options={"ftol": 1e-12, "maxiter": 1000},
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

    value = float(optimized_weights @ objective_covariance @ optimized_weights)
    baselines = np.r_[float(initial_weights @ objective_covariance @ initial_weights),
                      np.diag(objective_covariance)]
    if value > baselines.min() + 1e-9:
        raise PortfolioOptimizationError("Optimization is worse than a feasible baseline")
    # Frank-Wolfe gap on the simplex: zero iff first-order optimal for convex QP.
    gradient = 2.0 * objective_covariance @ optimized_weights
    gap = float(optimized_weights @ gradient - gradient.min())
    if gap > 1e-6:
        raise PortfolioOptimizationError("Optimization failed first-order optimality check")
    weights = pd.Series(optimized_weights, index=returns.columns, dtype=float)
    weights.attrs["optimization"] = {
        "annualized_variance": float(optimized_weights @ covariance @ optimized_weights),
        "equal_weight_variance": float(initial_weights @ covariance @ initial_weights),
        "single_asset_variances": dict(zip(returns.columns, np.diag(covariance).tolist())),
        "normalized_optimality_gap": gap, "ftol": 1e-12, "maxiter": 1000,
        "iterations": int(getattr(result, "nit", 0)),
        "covariance_scale": scale, "gradient": "analytic",
    }
    return weights


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

    if (aligned_weights < 0).any() or not np.isclose(
        aligned_weights.sum(), 1.0, atol=_WEIGHT_TOLERANCE, rtol=0
    ):
        raise ValueError("Weights must be non-negative and sum to one")
    _validate_returns(returns)
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

    if (values <= -1.0).any():
        raise PortfolioOptimizationError("Simple returns must be greater than -1")
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


def split_returns(returns: pd.DataFrame, train_fraction: float = 0.7):
    """Split ordered daily returns once by time, without fitting on evaluation.

    Input: finite returns with a unique increasing DatetimeIndex and fraction (0,1).
    Output: disjoint training/evaluation copies, each containing at least 2 rows.
    The first evaluation return starts after the last training close.
    """
    _validate_returns(returns)
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise ValueError("Split requires a DatetimeIndex")
    if returns.index.has_duplicates or not returns.index.is_monotonic_increasing:
        raise ValueError("Split requires unique increasing dates")
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    boundary = int(len(returns) * train_fraction)
    if min(boundary, len(returns) - boundary) < 2:
        raise ValueError("Training and evaluation each require at least two observations")
    return returns.iloc[:boundary].copy(), returns.iloc[boundary:].copy()


def inverse_volatility_weights(returns: pd.DataFrame) -> pd.Series:
    """Return long-only weights inversely proportional to historical volatility.

    Parameters
    ----------
    returns : DataFrame
        At least two complete finite daily simple returns > -1 per asset.

    Returns
    -------
    Series
        Labelled finite nonnegative weights summing to one. Sample standard
        deviation uses ddof=1. Zero/nonfinite risk is rejected, never floored.
    """
    _validate_returns(returns)
    sigma = returns.std(ddof=1)
    if not np.isfinite(sigma.to_numpy()).all() or (sigma <= 0).any():
        raise ValueError("Inverse volatility requires strictly positive finite volatility")
    scaled_inverse = sigma.min()/sigma
    return scaled_inverse/scaled_inverse.sum()
