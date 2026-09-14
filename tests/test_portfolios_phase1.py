import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace
from portfolio_analysis import portfolios as p

def diagonal_returns():
    # Exactly diagonal sample covariance, variances 1:4.
    return pd.DataFrame({"A":[.01,-.01,0,0],"B":[0,0,.02,-.02]})

def test_known_diagonal_covariance_solution():
    w=p.minimum_volatility_weights(diagonal_returns())
    assert w.to_numpy()==pytest.approx([.8,.2],abs=1e-6)

def test_false_success_is_rejected(monkeypatch):
    monkeypatch.setattr(p,"minimize",lambda *a,**k:SimpleNamespace(success=True,message="ok",x=np.array([.5,.5])))
    with pytest.raises(p.PortfolioOptimizationError,match="optimal|baseline"):
        p.minimum_volatility_weights(diagonal_returns())

@pytest.mark.parametrize("weights",[[.6,.6],[-.1,1.1],[float("inf"),0]])
def test_invalid_portfolio_weights(weights):
    with pytest.raises(ValueError):
        p.portfolio_returns(diagonal_returns(),pd.Series(weights,index=["A","B"]))

def test_temporal_split_does_not_leak_evaluation():
    dates=pd.bdate_range("2024-01-01",periods=100)
    r=pd.DataFrame(np.random.default_rng(2).normal(0,.01,(100,2)),index=dates,columns=["A","B"])
    assert hasattr(p,"split_returns")
    train,evaluation=p.split_returns(r,train_fraction=.7)
    w=p.minimum_volatility_weights(train)
    changed=r.copy(); changed.iloc[70:]*=10
    other,_=p.split_returns(changed,train_fraction=.7)
    assert p.minimum_volatility_weights(other).to_numpy()==pytest.approx(w.to_numpy())
    assert train.index.max()<evaluation.index.min()


def test_portfolio_rejects_total_loss_outside_price_domain():
    with pytest.raises(p.PortfolioOptimizationError):
        p.portfolio_returns(pd.DataFrame({"A":[-1.,.1]}),pd.Series({"A":1.}))
