import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.tracking import align_levels, tracking_statistics, rolling_tracking

def pair(n=7):
    d = pd.bdate_range("2024-01-02", periods=n)
    return d, pd.Series(np.arange(n)+100., index=d), pd.Series(np.arange(n)+200., index=d)

def test_gap_does_not_bridge_return_intervals():
    d,e,b = pair()
    a = align_levels(e,b.drop(d[2]),d,d)
    assert a.prices.index.equals(d[3:])
    assert a.returns.index.equals(d[4:])
    assert a.quality["matched_price_count"] == 6
    assert a.quality["matched_observation_count"] == 3
    assert "benchmark_missing" in set(a.events.reason)

def test_different_calendars_are_logged():
    d,e,b = pair()
    a = align_levels(e,b.drop(d[2]),d,d.delete(2))
    assert a.prices.index.equals(d[3:])
    assert "different_trading_calendar" in set(a.events.reason)

def test_missing_both_and_earliest_tie():
    d,e,b = pair()
    e.loc[d[3]] = np.nan
    b.loc[d[3]] = np.nan
    a = align_levels(e,b,d,d)
    assert a.prices.index.equals(d[:3])
    assert "outside_selected_block" in set(a.events.reason)

@pytest.mark.parametrize("kind",["duplicate","unsorted","infinite","negative","intraday"])
def test_invalid_levels_rejected(kind):
    d,e,b = pair()
    if kind == "duplicate": e.index = d[:6].append(d[5:6])
    if kind == "unsorted": e = e.iloc[::-1]
    if kind == "infinite": e.iloc[2] = np.inf
    if kind == "negative": e.iloc[2] = -1
    if kind == "intraday": e.index = d + pd.Timedelta(hours=1)
    with pytest.raises(ValueError): align_levels(e,b,d,d)

def test_tracking_formulas():
    d = pd.bdate_range("2024-01-02", periods=4)
    e,b = pd.Series([.02,-.01,.03,.01],d),pd.Series([.01,-.02,.01,0],d)
    s = tracking_statistics(e,b)
    x=e-b
    assert s["tracking_difference"] == pytest.approx((1+e).prod()-(1+b).prod())
    assert s["annualized_tracking_difference"] == pytest.approx((1+e).prod()**63-(1+b).prod()**63)
    assert s["annualized_tracking_error"] == pytest.approx(x.std(ddof=1)*np.sqrt(252))
    assert s["information_ratio"] == pytest.approx(x.mean()/x.std(ddof=1)*np.sqrt(252))
    assert s["matched_observation_count"] == 4

def test_zero_tracking_error():
    d,e,b=pair()
    e = e.pct_change(fill_method=None).iloc[1:]
    s = tracking_statistics(e,e)
    assert s["annualized_tracking_error"] == 0
    assert np.isnan(s["information_ratio"])
    assert s["information_ratio_status"] == "undefined_zero_tracking_error"

def test_misaligned_returns_rejected():
    d,e,b=pair()
    with pytest.raises(ValueError): tracking_statistics(e.iloc[1:]/1000,b.iloc[:-1]/1000)

def test_rolling_trailing_only():
    d = pd.bdate_range("2024-01-02",periods=6)
    e,b=pd.Series([.01,.03,-.01,.02,.05,-.02],d),pd.Series([0,.01,.01,.01,.02,0],d)
    r=rolling_tracking(e,b,window=3)
    assert r.rolling_tracking_error.iloc[:2].isna().all()
    assert r.rolling_tracking_error.iloc[2] == pytest.approx((e-b).iloc[:3].std()*np.sqrt(252))
    assert r.rolling_correlation.iloc[2] == pytest.approx(e.iloc[:3].corr(b.iloc[:3]))
    changed=e.copy();changed.iloc[4:]=.5
    pd.testing.assert_frame_equal(r.iloc[:4],rolling_tracking(changed,b,window=3).iloc[:4])

@pytest.mark.parametrize("window",[0,1,2.5,True])
def test_bad_window(window):
    d,e,b=pair()
    with pytest.raises(ValueError): rolling_tracking(e/1000,b/1000,window=window)
