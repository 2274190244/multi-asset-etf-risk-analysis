"""Research presentation must preserve archived evidence and comparison boundaries."""
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def normalized_evidence(request, monkeypatch):
    if request.node.name in {"test_missing_package_is_explicit", "test_tampered_result_is_rejected"}:
        monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    else:
        monkeypatch.setenv("ETF_RESEARCH_RESULTS", str(request.getfixturevalue("demo_results")))

def test_missing_package_is_explicit(tmp_path):
    from portfolio_analysis.research_display import read_table,ResearchDataError
    with pytest.raises(ResearchDataError,match="缺少"):
        read_table(tmp_path,3,"summary")

def test_tampered_result_is_rejected(tmp_path):
    import json
    from portfolio_analysis.research_display import read_table,ResearchDataError
    p=tmp_path/"output_phase3";p.mkdir()
    (p/"summary.csv").write_text("status\nok\n")
    (p/"sha256.json").write_text(json.dumps({"summary.csv":"wrong"}))
    with pytest.raises(ResearchDataError,match="校验"):
        read_table(tmp_path,3,"summary")

def test_tracking_mismatch_suppresses_strict_metrics():
    from portfolio_analysis.research_display import tracking_view
    s,d=tracking_view(ROOT,"510300.SS__official")
    assert s.status=="basis_mismatch"
    assert pd.isna(s.annualized_tracking_error)
    assert d.rolling_tracking_error.isna().all()
    assert d.date.min()==pd.Timestamp(s.sample_start)

def test_common_robustness_group_and_skipped_rows():
    from portfolio_analysis.research_display import robustness_view
    s,f=robustness_view(ROOT,"extended_126_252","2025","phase2",10)
    assert set(s.group_id)=={"extended_126_252"}
    assert set(s.period_id)=={"2025"}
    assert s[s.window==504].status.eq("insufficient_history").all()
    assert s[s.status=="ok"].evaluation_count.nunique()==1
    assert set(f.basis)=={"net"}

@pytest.mark.parametrize("page",["研究概览","ETF Tracking Research","Walk-Forward Portfolio Research",
                                "Index Construction Research","Robustness Analysis","数据与方法附录"])
def test_research_pages_render(page):
    app=AppTest.from_file(str(ROOT/"streamlit_app.py")).run(timeout=60)
    app.radio[0].set_value(page).run(timeout=60)
    assert not app.exception
    assert not app.error
    if page not in ["研究概览","数据与方法附录"]:
        headings=[x.value for x in app.subheader]
        assert headings==["Research Question","Methodology","Evidence","Findings","Limitations"]

def test_tracking_unavailable_remains_visible():
    app=AppTest.from_file(str(ROOT/"streamlit_app.py")).run(timeout=60)
    app.radio[0].set_value("ETF Tracking Research").run(timeout=60)
    app.selectbox[0].set_value("511010.SS__official").run(timeout=60)
    assert not app.exception
    assert not app.error
    assert any("unavailable" in w.value for w in app.warning)

def test_readme_and_summary_use_shared_findings():
    from portfolio_analysis.research_display import findings
    for path in [ROOT/"README.md",ROOT/"docs/RESEARCH_SUMMARY.md"]:
        text=path.read_text(encoding="utf-8")
        assert all(line in text for line in findings(ROOT))

def test_robustness_index_extended_subperiod_filters():
    app=AppTest.from_file(str(ROOT/"streamlit_app.py")).run(timeout=60)
    app.radio[0].set_value("Robustness Analysis").run(timeout=60)
    app.selectbox[0].set_value("extended_126_252").run(timeout=60)
    app.selectbox[1].set_value("2025").run(timeout=60)
    app.selectbox[2].set_value("phase4").run(timeout=60)
    assert not app.exception and not app.error
    frame=app.dataframe[0].value
    assert frame[frame.window==504].status.eq("insufficient_history").all()
    assert "gross_annualized_return" in frame
    assert "net_annualized_return" not in frame

def test_portfolio_frequency_cost_changes_evidence():
    app=AppTest.from_file(str(ROOT/"streamlit_app.py")).run(timeout=60)
    app.radio[0].set_value("Walk-Forward Portfolio Research").run(timeout=60)
    app.selectbox[0].set_value(63).run(timeout=60)
    app.selectbox[1].set_value(20).run(timeout=60)
    assert not app.exception and not app.error
    frame=app.dataframe[0].value
    assert frame.cost_bps.eq(20).all() and frame.rebalance_every.eq(63).all()
    assert set(frame.basis)=={"gross","net"}
