from datetime import date

from portfolio_analysis.config import ASSETS, default_date_range


def test_assets_cover_five_distinct_categories():
    assert len(ASSETS) == 5
    assert {asset.asset_class for asset in ASSETS} == {
        "csi_300", "csi_500", "chinext", "gold", "government_bond"
    }


def test_default_date_range_is_three_years_and_excludes_future_dates():
    start, end = default_date_range(date(2026, 8, 12))
    assert start == date(2023, 8, 12)
    assert end == date(2026, 8, 12)
