"""Price cleaning with mutually exclusive row-removal reasons."""
from dataclasses import dataclass, field
import numpy as np
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
    events: list = field(default_factory=list)
    raw_counts: dict = field(default_factory=dict)
    duplicate_counts: dict = field(default_factory=dict)

def clean_prices(frame: pd.DataFrame) -> tuple[pd.DataFrame, DataQuality]:
    """Return cleaned rows and removal ledger; preserve source/price metadata.

    Input: normalized long prices. Invalid rows are removed with exact row IDs.
    Conflicting same-symbol/date prices are all quarantined, never selected by order.
    Output: sorted frame and counts; an empty frame is allowed for quality-only runs.
    """
    missing = set(_NORMALIZED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError("Price frame is missing required columns: " + ", ".join(sorted(missing)))
    clean = frame.copy().reset_index(drop=True)
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    # Exchange sessions are timezone-naive dates; providers normalize beforehand.
    if getattr(clean["date"].dt, "tz", None) is not None:
        clean["date"] = clean["date"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    clean["date"] = clean["date"].dt.normalize()
    raw_counts = clean.groupby("symbol", dropna=False).size().to_dict()
    dup = clean.duplicated(["symbol","date"])
    duplicate_counts = clean.loc[dup].groupby("symbol",dropna=False).size().to_dict()
    reasons = pd.Series("",index=clean.index,dtype="str")
    missing_close = clean.close.isna()
    clean["close"] = pd.to_numeric(clean.close,errors="coerce")
    invalid = ~missing_close & (~np.isfinite(clean.close) | clean.close.le(0))
    reasons.loc[missing_close] = "missing_close"
    reasons.loc[invalid] = "invalid_price"
    reasons.loc[clean.date.isna()] = "invalid_date"
    bad_symbol = clean.symbol.isna() | clean.symbol.astype(str).str.strip().eq("")
    reasons.loc[bad_symbol] = "invalid_symbol"
    usable = clean.loc[reasons.eq("")]
    conflict = usable.groupby(["symbol","date"]).close.transform("nunique").gt(1)
    reasons.loc[usable.index[conflict]] = "conflicting_duplicate"
    usable = clean.loc[reasons.eq("")]
    reasons.loc[usable.index[usable.duplicated(["symbol","date"])]] = "duplicate"
    events = []
    for i in clean.index[reasons.ne("")]:
        row=clean.loc[i]
        events.append({"stage":"cleaning","row_id":int(i),"ticker":str(row.symbol),
            "date":row.date,"reason":reasons[i],"action":"remove","affected_rows":1})
    output=clean.loc[reasons.eq("")].sort_values(["symbol","date"]).reset_index(drop=True)
    q=DataQuality(len(frame),len(output),int(reasons.eq("duplicate").sum()),
        int(reasons.eq("invalid_price").sum()),int(reasons.eq("missing_close").sum()),
        output.date.min(),output.date.max(),events,raw_counts,duplicate_counts)
    if output.empty:
        # Preserve old public error, attaching the complete ledger for pipeline reporting.
        error=ValueError("No valid prices remain after cleaning")
        error.quality=q
        raise error
    return output,q
