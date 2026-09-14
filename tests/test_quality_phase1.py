import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.cleaning import clean_prices

def prices(values=(100,101,102)):
    return pd.DataFrame({"date":pd.to_datetime(["2026-01-05","2026-01-06","2026-01-07"]),
        "symbol":"A","asset_name":"A","asset_class":"bond","close":values})

def test_infinite_price_is_removed_and_audited():
    clean,q=clean_prices(prices((100,np.inf,102)))
    assert len(clean)==2
    assert q.invalid_prices_removed==1
    assert hasattr(q,"events")

def test_conflicting_duplicate_is_not_arbitrarily_selected():
    raw=prices(); extra=raw.iloc[[0]].copy(); extra["close"]=999
    clean,q=clean_prices(pd.concat([raw,extra]))
    assert not clean.date.eq(pd.Timestamp("2026-01-05")).any()
    assert hasattr(q,"events")

def test_missing_calendar_categories_and_contiguous_selection():
    from portfolio_analysis.quality import assess_quality
    dates=pd.bdate_range("2026-01-05",periods=8)
    raw=pd.DataFrame([{"date":d,"symbol":s,"asset_name":s,"asset_class":"x","close":100+i}
        for s in ["A","B"] for i,d in enumerate(dates) if not(s=="B" and i==2)])
    clean,q=clean_prices(raw)
    report,events,window=assess_quality(clean,q,dates[0],dates[-1],
        sessions_by_symbol={"A":dates,"B":dates},status_by_key={("B",dates[2]):"suspension"})
    assert report.set_index("ticker").loc["B","missing_count"]==1
    assert "suspension" in set(events.reason)
    assert window.index.tolist()==dates[3:].tolist()
    assert "outside_selected_contiguous_window" in set(events.reason)

def test_all_assets_missing_session_detected():
    from portfolio_analysis.quality import assess_quality
    dates=pd.bdate_range("2026-01-05",periods=4)
    raw=prices(); raw["date"]=dates[[0,2,3]]
    clean,q=clean_prices(raw)
    report,events,window=assess_quality(clean,q,dates[0],dates[-1],sessions_by_symbol={"A":dates})
    assert report.iloc[0].missing_count==1
    assert "source_missing_unverified" in set(events.reason)

def test_china_calendar_excludes_spring_festival():
    from portfolio_analysis.quality import china_sessions
    dates=china_sessions("2026-02-13","2026-02-24")
    assert dates.tolist()==list(pd.to_datetime(["2026-02-13","2026-02-24"]))

def test_different_calendars_do_not_bridge_intervals():
    from portfolio_analysis.quality import assess_quality
    dates=pd.bdate_range("2026-01-05",periods=8)
    rows=[dict(date=d,symbol=s,asset_name=s,asset_class="x",close=100+i)
          for s in ["A","B"] for i,d in enumerate(dates) if not(s=="B" and i==2)]
    raw=pd.DataFrame(rows); clean,q=clean_prices(raw)
    report,events,window=assess_quality(clean,q,dates[0],dates[-1],
        sessions_by_symbol={"A":dates,"B":dates.delete(2)})
    assert window.index.tolist()==dates[3:].tolist()
    assert "different_asset_calendar" in set(events.reason)
