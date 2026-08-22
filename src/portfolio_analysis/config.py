from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    name: str
    asset_class: str


ASSETS = (
    AssetConfig("510300.SS", "沪深300ETF", "csi_300"),
    AssetConfig("510500.SS", "中证500ETF", "csi_500"),
    AssetConfig("159915.SZ", "创业板ETF", "chinext"),
    AssetConfig("518880.SS", "黄金ETF", "gold"),
    AssetConfig("511010.SS", "国债ETF", "government_bond"),
)


def default_date_range(today: date) -> tuple[date, date]:
    try:
        start = today.replace(year=today.year - 3)
    except ValueError:
        start = today.replace(year=today.year - 3, day=28)
    return start, today
