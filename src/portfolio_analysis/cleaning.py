"""Price-data cleaning and data-quality reporting."""

from dataclasses import dataclass

import pandas as pd


_NORMALIZED_COLUMNS = ["date", "symbol", "asset_name", "asset_class", "close"]


@dataclass(frozen=True)
class DataQuality:
    input_rows: int
    output_rows: int
    duplicates_removed: int
    invalid_prices_removed: int
    missing_close_removed: int
    start_date: pd.Timestamp
    end_date: pd.Timestamp


def clean_prices(frame: pd.DataFrame) -> tuple[pd.DataFrame, DataQuality]:
    """Remove unusable price rows while keeping the normalized schema stable."""
    missing_columns = set(_NORMALIZED_COLUMNS).difference(frame.columns)
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise ValueError(f"Price frame is missing required columns: {names}")

    clean = frame.loc[:, _NORMALIZED_COLUMNS].copy()
    input_rows = len(clean)

    original_close = clean["close"]
    missing_close = original_close.isna()
    clean["close"] = pd.to_numeric(original_close, errors="coerce")
    invalid_price = (~missing_close) & (
        clean["close"].isna() | clean["close"].le(0)
    )
    clean = clean.loc[~(missing_close | invalid_price)].copy()

    duplicate_rows = clean.duplicated(subset=["date", "symbol"])
    duplicates_removed = int(duplicate_rows.sum())
    clean = clean.loc[~duplicate_rows].sort_values(["symbol", "date"]).reset_index(
        drop=True
    )

    if clean.empty:
        raise ValueError("No valid prices remain after cleaning")

    quality = DataQuality(
        input_rows=input_rows,
        output_rows=len(clean),
        duplicates_removed=duplicates_removed,
        invalid_prices_removed=int(invalid_price.sum()),
        missing_close_removed=int(missing_close.sum()),
        start_date=clean["date"].min(),
        end_date=clean["date"].max(),
    )
    return clean, quality
