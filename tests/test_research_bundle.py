"""Portable inputs and presentation must work without private local archives."""
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_checked_normalized_inputs_have_required_provenance():
    from portfolio_analysis.research_bundle import load_inputs
    prices, levels, meta = load_inputs(ROOT / "data/research_demo")
    assert prices.shape == (726, 5)
    assert len(meta["pairs"]) == 8
    assert len(levels.series_id.unique()) == 13
    assert meta["raw_evidence_included"] is False
    assert meta["market_source"]["retrieval_timestamp"] == "unknown_legacy_snapshot"


def test_input_corruption_is_not_silently_accepted(tmp_path):
    from portfolio_analysis.research_bundle import load_inputs
    shutil.copytree(ROOT / "data/research_demo", tmp_path / "inputs")
    with (tmp_path / "inputs/market_prices.csv").open("a") as handle:
        handle.write("corrupt")
    with pytest.raises(ValueError, match="hash"):
        load_inputs(tmp_path / "inputs")


def test_all_pages_guide_when_result_directory_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ETF_RESEARCH_RESULTS", str(tmp_path / "not_generated"))
    from portfolio_analysis.research_display import PAGES
    app = AppTest.from_file(str(ROOT / "streamlit_app.py")).run(timeout=60)
    for page in PAGES:
        app.radio[0].set_value(page).run(timeout=60)
        assert not app.exception and not app.error
        if page != "数据与方法附录":
            assert any("研究结果尚未生成" in message.value for message in app.info)
            assert any("build_research_demo.py" in block.value for block in app.code)


def test_manifest_missing_is_different_from_corruption(tmp_path, monkeypatch):
    from portfolio_analysis.research_display import read_table, ResearchResultsMissing, ResearchDataError
    monkeypatch.setenv("ETF_RESEARCH_RESULTS", str(tmp_path))
    with pytest.raises(ResearchResultsMissing):
        read_table(ROOT, 3, "summary")
    p = tmp_path / "output_phase3"
    p.mkdir()
    (p / "sha256.json").write_text("not json")
    with pytest.raises(ResearchDataError, match="损坏"):
        read_table(ROOT, 3, "summary")
    (p / "sha256.json").write_text("[]")
    with pytest.raises(ResearchDataError, match="损坏"):
        read_table(ROOT, 3, "summary")


def test_generated_bundle_contains_all_predeclared_cases(demo_results):
    from portfolio_analysis.research_bundle import build_bundle
    meta = json.loads((demo_results / "bundle.json").read_text(encoding="utf-8"))
    assert meta["phase5_successful_scenarios"] == 140
    assert meta["phase5_skipped_scenarios"] == 28
    assert len(list(demo_results.rglob("*.csv"))) == 13
    assert not list(demo_results.rglob("*.sqlite"))
    tracking = pd.read_csv(demo_results / "output_phase3/summary.csv")
    assert len(tracking) == 8 and tracking.status.eq("comparable").sum() == 3
    assert tracking.loc[tracking.status != "comparable", "annualized_tracking_error"].isna().all()
    sensitivity = pd.read_csv(demo_results / "output_phase5/tables/sensitivity.csv")
    assert len(sensitivity) == 672 and sensitivity.status.eq("ok").sum() == 560
    assert sensitivity[sensitivity.status == "ok"].groupby(["group_id", "period_id"]).evaluation_count.nunique().eq(1).all()
    with pytest.raises(FileExistsError):
        build_bundle(demo_results)


def test_original_archives_match_normalized_recalculation(demo_results):
    from portfolio_analysis.research_bundle import REQUIRED_TABLES
    for phase, names in REQUIRED_TABLES.items():
        for name in names:
            rel = f"output_phase{phase}/" + ("" if phase == 3 else "tables/") + name + ".csv"
            a, b = [pd.read_csv(p, dtype={"benchmark_code": str}, float_precision="round_trip")
                    for p in [ROOT / rel, demo_results / rel]]
            for col in a:
                if "date" in col or col in {"start", "end", "inception", "estimation_start", "estimation_end", "information_cutoff", "latest_available_at"}:
                    if a[col].notna().any():
                        try:
                            a[col] = pd.to_datetime(a[col], format="mixed")
                            b[col] = pd.to_datetime(b[col], format="mixed")
                        except (ValueError, TypeError):
                            pass
            pd.testing.assert_frame_equal(a, b[a.columns], check_dtype=False, rtol=1e-8, atol=1e-10)
