import pandas as pd
import pytest

from portfolio_analysis.cleaning import clean_prices


def test_clean_prices_drops_duplicate_and_invalid_prices():
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-02", "2026-01-03"]),
            "symbol": ["A", "A", "A"],
            "asset_name": ["Example", "Example", "Example"],
            "asset_class": ["equity", "equity", "equity"],
            "close": [10.0, 10.0, 0.0],
        }
    )

    clean, quality = clean_prices(raw)

    assert len(clean) == 1
    assert quality.duplicates_removed == 1
    assert quality.invalid_prices_removed == 1


def test_clean_prices_coerces_prices_sorts_rows_and_reports_date_range():
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-03", "2026-01-02", "2026-01-04", "2026-01-05"]),
            "symbol": ["B", "A", "A", "A"],
            "asset_name": ["B fund", "A fund", "A fund", "A fund"],
            "asset_class": ["bond", "equity", "equity", "equity"],
            "close": ["12.5", None, "not-a-price", "10.0"],
        }
    )

    clean, quality = clean_prices(raw)

    assert clean[["symbol", "date", "close"]].to_dict("records") == [
        {"symbol": "A", "date": pd.Timestamp("2026-01-05"), "close": 10.0},
        {"symbol": "B", "date": pd.Timestamp("2026-01-03"), "close": 12.5},
    ]
    assert quality.input_rows == 4
    assert quality.output_rows == 2
    assert quality.missing_close_removed == 1
    assert quality.invalid_prices_removed == 1
    assert quality.start_date == pd.Timestamp("2026-01-03")
    assert quality.end_date == pd.Timestamp("2026-01-05")


def test_clean_prices_rejects_frames_without_valid_prices():
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02"]),
            "symbol": ["A"],
            "asset_name": ["Example"],
            "asset_class": ["equity"],
            "close": [None],
        }
    )

    with pytest.raises(ValueError, match="No valid prices remain after cleaning"):
        clean_prices(raw)
