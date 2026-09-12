from datetime import date
from portfolio_analysis.config import ASSETS
from portfolio_analysis.data_source import fetch_eastmoney_asset_prices,parse_chart_response

def test_source_metadata_persisted(tmp_path,monkeypatch,eastmoney_payload):
    monkeypatch.chdir(tmp_path)
    class Response:
        def raise_for_status(self): pass
        def json(self): return eastmoney_payload
    class Session:
        def get(self,*args,**kwargs): return Response()
    frame=fetch_eastmoney_asset_prices(ASSETS[0],date(2026,1,2),date(2026,1,5),Session())
    assert {"source","price_basis","retrieval_timestamp","requested_start","requested_end"}<=set(frame.columns)
    assert frame.price_basis.eq("forward_adjusted").all()
    assert list((tmp_path/"data/raw/snapshots").glob("*.json"))

def test_unadjusted_fallback_is_explicit(yahoo_payload):
    del yahoo_payload["chart"]["result"][0]["indicators"]["adjclose"]
    frame=parse_chart_response(yahoo_payload,ASSETS[0])
    assert frame.price_basis.eq("unadjusted_close").all()

def test_bad_volume_is_a_market_data_error(eastmoney_payload):
    import pytest
    from portfolio_analysis.data_source import parse_eastmoney_response,MarketDataError
    eastmoney_payload["data"]["klines"][0]="2026-01-02,4,4,4,4,-"
    with pytest.raises(MarketDataError):
        parse_eastmoney_response(eastmoney_payload,ASSETS[0])
