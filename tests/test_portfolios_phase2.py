import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.portfolios import inverse_volatility_weights

def test_inverse_volatility_known_ratio():
    x=np.array([-.02,.02,-.01,.01])
    w=inverse_volatility_weights(pd.DataFrame({"a":x,"b":2*x}))
    np.testing.assert_allclose(w,[2/3,1/3],atol=1e-12)
    assert w.sum()==pytest.approx(1)

@pytest.mark.parametrize("bad",[0.,np.nan,np.inf])
def test_inverse_volatility_rejects_invalid_or_zero_risk(bad):
    with pytest.raises(ValueError):
        inverse_volatility_weights(pd.DataFrame({"a":[.01,-.01,.02],"b":[bad,bad,bad]}))
