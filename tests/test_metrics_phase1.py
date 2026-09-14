import numpy as np
import pandas as pd
import pytest
from portfolio_analysis import metrics as m

def test_initial_loss_counts_as_drawdown():
    assert m.maximum_drawdown(pd.Series([-0.1, 0.05])) == pytest.approx(-0.1)

def test_quantile_integrated_cvar():
    x = pd.Series([-0.1, 0.1])
    assert m.return_quantile(x, 0.25) == pytest.approx(-0.05)
    assert m.historical_cvar(x, 0.75) == pytest.approx(0.075)
    assert m.historical_var(pd.Series([0.01, 0.02])) < 0

def test_effective_daily_sharpe_and_downside():
    x = pd.Series([-0.01, 0.02, 0.03])
    daily = 1.02 ** (1 / 252) - 1
    assert m.sharpe_ratio(x, 0.02) == pytest.approx((x.mean()-daily)/x.std()*np.sqrt(252))
    assert m.downside_volatility(x) == pytest.approx(np.sqrt(252*0.01**2/3))

def test_missing_and_nonfinite_rejected():
    for x in ([0.01, np.nan], [0.01, np.inf], []):
        with pytest.raises(m.MetricError):
            m.maximum_drawdown(pd.Series(x))
    with pytest.raises(m.MetricError, match='A'):
        m.asset_metrics(pd.DataFrame({'A': [0.01]*30+[np.nan]}))

def test_zero_risk_explicit_status():
    result = m.asset_metrics(pd.DataFrame({'A': [0.0]*30}))
    assert np.isnan(result.loc['A','sharpe_ratio'])
    assert result.attrs['metric_status']['A']['sharpe_ratio'] == 'undefined_zero_volatility'

def test_prices_transforms_and_internal_all_empty_rows():
    assert m.simple_returns(pd.Series([100.,110.,99.])).tolist() == pytest.approx([0.1,-0.1])
    prices = pd.DataFrame({'date': pd.date_range('2020-01-01', periods=4), 'symbol':['A']*4, 'close':[100.,np.nan,110.,121.]})
    result = m.daily_returns(prices)
    assert len(result) == 3
    assert result.iloc[:2].isna().all().all()
    assert result.attrs['audit']

@pytest.mark.parametrize('name', ['annualized_return','annualized_volatility','sharpe_ratio','maximum_drawdown','historical_var','historical_cvar','downside_volatility','sortino_ratio','calmar_ratio'])
def test_all_statistics_reject_nonfinite(name):
    with pytest.raises(m.MetricError):
        getattr(m, name)([0.01, float('inf')])

@pytest.mark.parametrize('confidence', [0, 1, -0.1, float('nan')])
def test_invalid_confidence(confidence):
    for function in [m.historical_var, m.historical_cvar]:
        with pytest.raises(m.MetricError):
            function([0.01, 0.02], confidence)

def test_cvar_full_piecewise_tail_and_singleton():
    # At p=.5, quantile=-.02; integral consists of one full trapezoid.
    assert m.historical_cvar([-0.1,-0.02,0.05], 0.5) == pytest.approx(0.06)
    assert m.historical_cvar([0.01]) == pytest.approx(-0.01)

def test_log_and_simple_preserve_alignment_and_reject_gaps():
    prices = pd.Series([100.,110.,99.], index=['a','b','c'])
    result = m.log_returns(prices)
    assert result.index.tolist() == ['b','c']
    assert result.tolist() == pytest.approx(np.log([1.1,0.9]))
    for function in [m.simple_returns, m.log_returns]:
        with pytest.raises(m.MetricError):
            function([100.,np.nan,101.])

def test_internal_missing_rejected_despite_sufficient_count():
    with pytest.raises(m.MetricError, match='missing'):
        m.asset_metrics(pd.DataFrame({'A':[0.01]*15+[np.nan]+[0.01]*15}))

def test_sortino_target_and_calmar_formulas():
    x = np.array([-0.02,0.01,0.04])
    target = 0.03
    daily = (1+target)**(1/252)-1
    risk = np.sqrt(np.mean(np.minimum(x-daily,0)**2)*252)
    assert m.sortino_ratio(x, target) == pytest.approx((x.mean()-daily)*252/risk)
    assert m.calmar_ratio(x) == pytest.approx(m.annualized_return(x)/0.02)
    assert np.isnan(m.sortino_ratio([0.01,0.02]))
    assert np.isnan(m.calmar_ratio([0.01,0.02]))

def test_computed_overflow_is_explicit_error():
    for function in (m.simple_returns, m.log_returns):
        with pytest.raises(m.MetricError, match='finite'):
            function([1e-300, 1e300])
    with pytest.raises(m.MetricError, match='finite'):
        m.annualized_volatility([0., 1e308])

def test_daily_returns_rejects_computed_infinity():
    prices = pd.DataFrame({'date':[1,2], 'symbol':['A','A'], 'close':[1e-300,1e300]})
    with pytest.raises(m.MetricError, match='finite'):
        m.daily_returns(prices)

def test_sharpe_underflowed_zero_variance_is_undefined():
    assert np.isnan(m.sharpe_ratio([1e-200, 2e-200], risk_free_rate=0))

def test_ratio_output_overflow_is_error():
    with pytest.raises(m.MetricError, match='finite'):
        m.calmar_ratio([-1e-310, 0.01])
