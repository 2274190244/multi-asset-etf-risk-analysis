import json
from pathlib import Path

import pytest


@pytest.fixture
def yahoo_payload():
    fixture_path = Path(__file__).parent / "fixtures" / "yahoo_chart.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def eastmoney_payload():
    fixture_path = Path(__file__).parent / "fixtures" / "eastmoney_kline.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))
