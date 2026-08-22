from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from portfolio_analysis.portfolios import (
    PortfolioOptimizationError,
    equal_weights,
    minimum_volatility_weights,
    portfolio_returns,
)


def test_equal_weights_sum_to_one():
    weights = equal_weights(["A", "B", "C", "D", "E"])

    assert weights.sum() == pytest.approx(1.0)
    assert (weights >= 0).all()
    assert weights.index.tolist() == ["A", "B", "C", "D", "E"]


def test_minimum_volatility_weights_respect_constraints():
    rng = np.random.default_rng(7)
    returns = pd.DataFrame(rng.normal(0.0003, 0.01, size=(200, 5)), columns=list("ABCDE"))

    weights = minimum_volatility_weights(returns)

    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert ((weights >= 0.0) & (weights <= 1.0)).all()
    assert weights.index.tolist() == list("ABCDE")


def test_portfolio_returns_aligns_weights_by_symbol_and_preserves_dates():
    dates = pd.to_datetime(["2026-01-02", "2026-01-03"])
    returns = pd.DataFrame({"A": [0.01, -0.02], "B": [0.03, 0.01]}, index=dates)
    weights = pd.Series({"B": 0.75, "A": 0.25})

    result = portfolio_returns(returns, weights)

    assert result.index.equals(dates)
    assert result.tolist() == pytest.approx([0.025, 0.0025])


def test_portfolio_returns_rejects_misaligned_weight_symbols():
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, 0.04]})
    weights = pd.Series({"A": 0.5, "C": 0.5})

    with pytest.raises(ValueError, match="match return columns"):
        portfolio_returns(returns, weights)


def test_minimum_volatility_weights_rejects_insufficient_complete_observations():
    returns = pd.DataFrame({"A": [0.01], "B": [0.02]})

    with pytest.raises(PortfolioOptimizationError, match="two complete daily observations"):
        minimum_volatility_weights(returns)


def test_minimum_volatility_weights_rejects_non_finite_returns():
    returns = pd.DataFrame({"A": [0.01, np.inf], "B": [0.02, 0.03]})

    with pytest.raises(PortfolioOptimizationError, match="finite"):
        minimum_volatility_weights(returns)


def test_minimum_volatility_weights_rejects_nan_returns():
    returns = pd.DataFrame({"A": [0.01, np.nan], "B": [0.02, 0.03]})

    with pytest.raises(PortfolioOptimizationError, match="finite"):
        minimum_volatility_weights(returns)


def test_minimum_volatility_weights_handles_degenerate_covariance():
    returns = pd.DataFrame({"A": [0.001] * 4, "B": [0.001] * 4})

    try:
        weights = minimum_volatility_weights(returns)
    except PortfolioOptimizationError:
        return

    assert np.isfinite(weights.to_numpy()).all()
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert ((weights >= 0.0) & (weights <= 1.0)).all()


def test_minimum_volatility_weights_raises_when_optimizer_fails(monkeypatch):
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.03]})

    monkeypatch.setattr(
        "portfolio_analysis.portfolios.minimize",
        lambda *args, **kwargs: SimpleNamespace(success=False, message="iteration limit"),
    )

    with pytest.raises(PortfolioOptimizationError, match="iteration limit"):
        minimum_volatility_weights(returns)


def test_minimum_volatility_weights_wraps_scipy_exceptions(monkeypatch):
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.03]})

    def raise_solver_error(*args, **kwargs):
        raise RuntimeError("numerical breakdown")

    monkeypatch.setattr("portfolio_analysis.portfolios.minimize", raise_solver_error)

    with pytest.raises(PortfolioOptimizationError, match="numerical breakdown"):
        minimum_volatility_weights(returns)


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(success=True, message="ok"),
        SimpleNamespace(message="ok", x=np.array([0.5, 0.5])),
        SimpleNamespace(success="yes", message="ok", x=np.array([0.5, 0.5])),
        SimpleNamespace(success=True, message=None, x=np.array([0.5, 0.5])),
        SimpleNamespace(success=True, message="ok", x="not weights"),
    ],
)
def test_minimum_volatility_weights_wraps_malformed_optimizer_results(monkeypatch, result):
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.03]})

    monkeypatch.setattr(
        "portfolio_analysis.portfolios.minimize", lambda *args, **kwargs: result
    )

    with pytest.raises(PortfolioOptimizationError, match="malformed result"):
        minimum_volatility_weights(returns)


@pytest.mark.parametrize(
    "optimized_weights",
    [
        np.array([np.nan, 1.0]),
        np.array([0.75, 0.75]),
        np.array([0.5, 0.500005]),
        np.array([-0.01, 1.01]),
    ],
)
def test_minimum_volatility_weights_rejects_invalid_optimizer_weights(
    monkeypatch, optimized_weights
):
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.03]})

    monkeypatch.setattr(
        "portfolio_analysis.portfolios.minimize",
        lambda *args, **kwargs: SimpleNamespace(
            success=True, message="ok", x=optimized_weights
        ),
    )

    with pytest.raises(PortfolioOptimizationError, match="invalid weights"):
        minimum_volatility_weights(returns)
