from datetime import date
import json

import pandas as pd
import pytest
import requests

from portfolio_analysis.config import ASSETS
from portfolio_analysis.data_source import (
    MarketDataError,
    create_market_session,
    eastmoney_secid,
    fetch_asset_prices,
    fetch_eastmoney_asset_prices,
    parse_eastmoney_response,
    parse_chart_response,
)


def test_create_market_session_configures_bounded_get_retries():
    session = create_market_session()

    for scheme in ("http://", "https://"):
        retries = session.get_adapter(scheme).max_retries
        assert retries.total == 3
        assert retries.connect == 3
        assert retries.read == 3
        assert retries.status == 3
        assert retries.backoff_factor == 0.5
        assert retries.allowed_methods == frozenset({"GET"})
        assert retries.status_forcelist == {429, 500, 502, 503, 504}
        assert retries.respect_retry_after_header is True


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("510300.SS", "1.510300"), ("159915.SZ", "0.159915")],
)
def test_eastmoney_secid_maps_supported_chinese_exchange_suffixes(symbol, expected):
    assert eastmoney_secid(symbol) == expected


@pytest.mark.parametrize("symbol", ["SPY", "SPY.US", "12345.SS", "ABCDEF.SZ"])
def test_eastmoney_secid_rejects_unsupported_symbols(symbol):
    with pytest.raises(MarketDataError, match=f"Unsupported Eastmoney symbol: {symbol}"):
        eastmoney_secid(symbol)


def test_parse_eastmoney_response_returns_normalized_columns(eastmoney_payload):
    frame = parse_eastmoney_response(eastmoney_payload, ASSETS[0])

    assert list(frame.columns) == [
        "date",
        "symbol",
        "asset_name",
        "asset_class",
        "close",
    ]
    assert frame["date"].tolist() == [
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-05"),
    ]
    assert frame["symbol"].eq("510300.SS").all()
    assert frame["close"].tolist() == [4.12, 4.08]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"rc": 1, "data": {"klines": ["2026-01-02,4,4,4,4,1"]}}, "rc=1"),
        ({"rc": 0, "data": None}, "No Eastmoney market data"),
        ({"rc": 0, "data": {}}, "No Eastmoney market data"),
        ({"rc": 0, "data": {"klines": []}}, "No Eastmoney market data"),
        ({"rc": 0, "data": {"klines": ["malformed"]}}, "Malformed Eastmoney kline"),
        (
            {"rc": 0, "data": {"klines": ["2026-01-02,4,not-a-price,4,4,1"]}},
            "Non-numeric Eastmoney close",
        ),
    ],
)
def test_parse_eastmoney_response_rejects_invalid_payloads(payload, message):
    with pytest.raises(MarketDataError, match=message):
        parse_eastmoney_response(payload, ASSETS[0])


def test_fetch_eastmoney_asset_prices_uses_daily_adjusted_inclusive_request_and_cache(
    tmp_path, monkeypatch, eastmoney_payload
):
    session = _EastmoneySession(eastmoney_payload)
    monkeypatch.chdir(tmp_path)

    frame = fetch_eastmoney_asset_prices(
        ASSETS[0], date(2026, 1, 2), date(2026, 1, 5), session
    )

    assert frame["close"].tolist() == [4.12, 4.08]
    assert session.url == "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    assert session.headers["Referer"] == "https://quote.eastmoney.com/"
    assert "Mozilla/5.0" in session.headers["User-Agent"]
    assert session.params == {
        "secid": "1.510300",
        "klt": 101,
        "fqt": 1,
        "beg": "20260102",
        "end": "20260105",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56",
    }
    cached_payload = json.loads(
        (tmp_path / "data" / "raw" / "eastmoney_510300.SS.json").read_text(
            encoding="utf-8"
        )
    )
    assert cached_payload == eastmoney_payload


def test_fetch_eastmoney_asset_prices_wraps_http_errors_without_caching(
    tmp_path, monkeypatch, eastmoney_payload
):
    session = _EastmoneySession(
        eastmoney_payload, http_error=requests.HTTPError("503 unavailable")
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        MarketDataError, match="Eastmoney request failed for 510300.SS: 503 unavailable"
    ):
        fetch_eastmoney_asset_prices(
            ASSETS[0], date(2026, 1, 2), date(2026, 1, 5), session
        )

    assert not (tmp_path / "data" / "raw" / "eastmoney_510300.SS.json").exists()


def test_fetch_eastmoney_asset_prices_propagates_unexpected_request_errors(
    tmp_path, monkeypatch, eastmoney_payload
):
    session = _EastmoneySession(
        eastmoney_payload, request_error=_ProgrammingError("client bug")
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(_ProgrammingError, match="client bug"):
        fetch_eastmoney_asset_prices(
            ASSETS[0], date(2026, 1, 2), date(2026, 1, 5), session
        )


def test_parse_chart_response_returns_normalized_columns(yahoo_payload):
    frame = parse_chart_response(yahoo_payload, ASSETS[0])

    assert list(frame.columns) == [
        "date",
        "symbol",
        "asset_name",
        "asset_class",
        "close",
    ]
    assert frame["symbol"].eq("510300.SS").all()
    assert frame["close"].tolist() == [4.01, 4.08]
    assert frame["date"].dt.tz is None


def test_parse_chart_response_rejects_missing_adjusted_close_values(yahoo_payload):
    yahoo_payload["chart"]["result"][0]["indicators"] = {"adjclose": [{}]}

    with pytest.raises(MarketDataError, match="Incomplete market data for 510300.SS"):
        parse_chart_response(yahoo_payload, ASSETS[0])


@pytest.mark.parametrize(
    "payload",
    [
        {"chart": []},
        {"chart": {"result": [None]}},
        {"chart": {"result": [{"timestamp": [1], "indicators": []}]}},
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1],
                        "indicators": {"adjclose": [None]},
                    }
                ]
            }
        },
    ],
)
def test_parse_chart_response_rejects_malformed_nested_payloads(payload):
    with pytest.raises(MarketDataError) as error:
        parse_chart_response(payload, ASSETS[0])

    assert "510300.SS" in str(error.value)


def test_fetch_asset_prices_persists_raw_response_and_returns_normalized_frame(
    tmp_path, monkeypatch, yahoo_payload
):
    session = _Session(yahoo_payload)
    monkeypatch.chdir(tmp_path)

    frame = fetch_asset_prices(
        ASSETS[0], date(2026, 1, 2), date(2026, 1, 3), session
    )

    assert frame["close"].tolist() == [4.01, 4.08]
    assert session.url == "https://query1.finance.yahoo.com/v8/finance/chart/510300.SS"
    assert session.params == {
        "period1": 1767312000,
        "period2": 1767484800,
        "interval": "1d",
        "events": "history",
    }
    cached_payload = json.loads((tmp_path / "data" / "raw" / "510300.SS.json").read_text())
    assert cached_payload == yahoo_payload


def test_fetch_asset_prices_uses_day_after_end_for_exclusive_period2(
    tmp_path, monkeypatch, yahoo_payload
):
    session = _Session(yahoo_payload)
    monkeypatch.chdir(tmp_path)

    fetch_asset_prices(ASSETS[0], date(2026, 1, 2), date(2026, 1, 3), session)

    assert session.params["period2"] == 1767484800


def test_fetch_asset_prices_wraps_http_errors_as_market_data_errors(
    tmp_path, monkeypatch, yahoo_payload
):
    session = _Session(yahoo_payload, http_error=requests.HTTPError("429 limited"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        MarketDataError, match="Yahoo request failed for 510300.SS: 429 limited"
    ):
        fetch_asset_prices(
            ASSETS[0], date(2026, 1, 2), date(2026, 1, 3), session
        )


def test_fetch_asset_prices_wraps_json_errors_as_market_data_errors(
    tmp_path, monkeypatch, yahoo_payload
):
    session = _Session(yahoo_payload, json_error=ValueError("invalid JSON"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        MarketDataError, match="Invalid Yahoo JSON for 510300.SS: invalid JSON"
    ):
        fetch_asset_prices(
            ASSETS[0], date(2026, 1, 2), date(2026, 1, 3), session
        )


def test_fetch_asset_prices_propagates_raw_cache_write_errors(
    tmp_path, monkeypatch, yahoo_payload
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "portfolio_analysis.data_source.Path.write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("disk denied")),
    )

    with pytest.raises(PermissionError, match="disk denied"):
        fetch_asset_prices(
            ASSETS[0], date(2026, 1, 2), date(2026, 1, 3), _Session(yahoo_payload)
        )


class _Response:
    def __init__(self, payload, http_error=None, json_error=None):
        self._payload = payload
        self._http_error = http_error
        self._json_error = json_error

    def raise_for_status(self):
        if self._http_error is not None:
            raise self._http_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _Session:
    def __init__(self, payload, http_error=None, json_error=None):
        self._payload = payload
        self._http_error = http_error
        self._json_error = json_error
        self.url = None
        self.params = None

    def get(self, url, *, params, timeout):
        self.url = url
        self.params = params
        assert timeout == 30
        return _Response(self._payload, self._http_error, self._json_error)


class _EastmoneyResponse(_Response):
    def __init__(self, payload, http_error=None):
        super().__init__(payload, http_error=http_error)


class _EastmoneySession:
    def __init__(self, payload, http_error=None, request_error=None):
        self._payload = payload
        self._http_error = http_error
        self._request_error = request_error
        self.url = None
        self.params = None
        self.headers = None

    def get(self, url, *, params, headers, timeout):
        if self._request_error is not None:
            raise self._request_error
        self.url = url
        self.params = params
        self.headers = headers
        assert timeout == 30
        return _EastmoneyResponse(self._payload, self._http_error)


class _ProgrammingError(Exception):
    pass
