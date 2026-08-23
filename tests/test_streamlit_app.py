from datetime import date
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_dashboard_renders_core_recruiter_view():
    app = AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py")).run(timeout=30)

    assert not app.exception
    assert app.title[0].value == "多资产 ETF 收益与风险分析平台"
    assert [tab.label for tab in app.tabs] == [
        "市场表现",
        "风险分析",
        "组合分析",
        "数据质量",
    ]
    assert [metric.label for metric in app.metric[:4]] == [
        "价格记录",
        "ETF 数量",
        "收益与风险指标",
        "投资组合",
    ]
    assert [metric.value for metric in app.metric[:4]] == ["3,630", "5", "5", "2"]
    charts = app.get("plotly_chart")
    assert len(charts) == 8
    assert all(json.loads(chart.proto.spec)["data"] for chart in charts)


def test_streamlit_dashboard_explains_empty_portfolio_date_range():
    app = AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py")).run(timeout=30)

    app.date_input[0].set_value((date(2023, 8, 14), date(2023, 8, 14))).run(
        timeout=30
    )

    assert not app.exception
    assert any("没有组合日收益记录" in message.value for message in app.info)
    assert len(app.get("plotly_chart")) == 6


def test_streamlit_dashboard_accepts_a_partially_selected_date_range():
    app = AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py")).run(timeout=30)

    app.date_input[0].set_value((date(2024, 1, 2),)).run(timeout=30)

    assert not app.exception
    assert len(app.tabs) == 4


def test_streamlit_dashboard_filters_market_charts_to_one_etf():
    app = AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py")).run(timeout=30)

    app.multiselect[0].set_value(["510300.SS"]).run(timeout=30)

    assert not app.exception
    market_spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert [trace["name"] for trace in market_spec["data"]] == ["沪深300ETF"]
    heatmap_spec = json.loads(app.get("plotly_chart")[4].proto.spec)
    assert len(heatmap_spec["data"][0]["x"]) == 5
    assert len(heatmap_spec["data"][0]["y"]) == 5
