"""Eastmoney and Yahoo market-data retrieval and normalization."""

from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from portfolio_analysis.config import AssetConfig


_EASTMONEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


class MarketDataError(RuntimeError):
    """Raised when a market-data response cannot produce price records."""


def create_market_session() -> requests.Session:
    """Create a requests session with bounded GET retries for market providers."""
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def eastmoney_secid(symbol: str) -> str:
    """Convert a supported Chinese ETF symbol to Eastmoney's market identifier."""
    match = re.fullmatch(r"(\d{6})\.(SS|SZ)", symbol)
    if match is None:
        raise MarketDataError(f"Unsupported Eastmoney symbol: {symbol}")
    code, exchange = match.groups()
    market = "1" if exchange == "SS" else "0"
    return f"{market}.{code}"


def parse_eastmoney_response(payload: dict, asset: AssetConfig) -> pd.DataFrame:
    """Normalize Eastmoney f51/f53 daily klines for one configured asset."""
    if not isinstance(payload, dict) or payload.get("rc") != 0:
        rc = payload.get("rc") if isinstance(payload, dict) else None
        raise MarketDataError(f"Eastmoney returned rc={rc} for {asset.symbol}")

    data = payload.get("data")
    klines = data.get("klines") if isinstance(data, dict) else None
    if not isinstance(klines, list) or not klines:
        raise MarketDataError(f"No Eastmoney market data for {asset.symbol}")

    records = []
    for row in klines:
        fields = row.split(",") if isinstance(row, str) else []
        if len(fields) != 6:
            raise MarketDataError(f"Malformed Eastmoney kline for {asset.symbol}")

        observed_date = pd.to_datetime(fields[0], format="%Y-%m-%d", errors="coerce")
        if pd.isna(observed_date):
            raise MarketDataError(f"Malformed Eastmoney kline for {asset.symbol}")
        try:
            close = float(fields[2])
        except (TypeError, ValueError) as error:
            raise MarketDataError(
                f"Non-numeric Eastmoney close for {asset.symbol}"
            ) from error
        if not math.isfinite(close):
            raise MarketDataError(f"Non-numeric Eastmoney close for {asset.symbol}")

        records.append(
            {
                "date": observed_date,
                "symbol": asset.symbol,
                "asset_name": asset.name,
                "asset_class": asset.asset_class,
                "close": close,
            }
        )

    return pd.DataFrame.from_records(
        records,
        columns=["date", "symbol", "asset_name", "asset_class", "close"],
    )


def fetch_eastmoney_asset_prices(
    asset: AssetConfig,
    start: date,
    end: date,
    session: Any,
) -> pd.DataFrame:
    """Fetch adjusted daily Eastmoney prices and cache a valid raw response."""
    try:
        response = session.get(
            "http://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": eastmoney_secid(asset.symbol),
                "klt": 101,
                "fqt": 1,
                "beg": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56",
            },
            headers=_EASTMONEY_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise MarketDataError(
            f"Eastmoney request failed for {asset.symbol}: {error}"
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise MarketDataError(
            f"Invalid Eastmoney JSON for {asset.symbol}: {error}"
        ) from error

    frame = parse_eastmoney_response(payload, asset)
    raw_path = Path("data") / "raw" / f"eastmoney_{asset.symbol}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return frame


def parse_chart_response(payload: dict, asset: AssetConfig) -> pd.DataFrame:
    """Normalize a Yahoo chart response for one configured asset."""
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        raise MarketDataError(f"No market data returned for {asset.symbol}")

    result = chart.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise MarketDataError(f"No market data returned for {asset.symbol}")

    block = result[0]
    timestamps = block.get("timestamp")
    indicators = block.get("indicators")
    if not isinstance(timestamps, list) or not isinstance(indicators, dict):
        raise MarketDataError(f"Incomplete market data for {asset.symbol}")

    quote_blocks = indicators.get("adjclose") or indicators.get("quote")
    if not isinstance(quote_blocks, list) or not quote_blocks:
        raise MarketDataError(f"Incomplete market data for {asset.symbol}")

    quote_block = quote_blocks[0]
    if not isinstance(quote_block, dict):
        raise MarketDataError(f"Incomplete market data for {asset.symbol}")

    prices = quote_block.get("adjclose") or quote_block.get("close")

    if (
        not timestamps
        or not isinstance(prices, list)
        or not prices
        or len(timestamps) != len(prices)
        or not any(price is not None for price in prices)
    ):
        raise MarketDataError(f"Incomplete market data for {asset.symbol}")

    return pd.DataFrame(
        {
            "date": pd.to_datetime(timestamps, unit="s", utc=True)
            .tz_convert(None)
            .normalize(),
            "symbol": asset.symbol,
            "asset_name": asset.name,
            "asset_class": asset.asset_class,
            "close": prices,
        }
    )


def fetch_asset_prices(
    asset: AssetConfig,
    start: date,
    end: date,
    session: Any,
) -> pd.DataFrame:
    """Fetch one asset's daily Yahoo prices and cache the raw response."""
    try:
        response = session.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{asset.symbol}",
            params={
                "period1": _to_unix_timestamp(start),
                "period2": _to_unix_timestamp(end + timedelta(days=1)),
                "interval": "1d",
                "events": "history",
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise MarketDataError(
            f"Yahoo request failed for {asset.symbol}: {error}"
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise MarketDataError(
            f"Invalid Yahoo JSON for {asset.symbol}: {error}"
        ) from error

    frame = parse_chart_response(payload, asset)

    raw_path = Path("data") / "raw" / f"{asset.symbol}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return frame


def _to_unix_timestamp(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())
