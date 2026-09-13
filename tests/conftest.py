import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--require-archives", action="store_true", help="Fail collection if original private/local audit archives are absent")


def pytest_configure(config):
    config.addinivalue_line("markers", "archive: replays original local raw evidence, not the normalized public sample")


def pytest_collection_modifyitems(config, items):
    """Explicitly identify original-archive tests; never treat their absence as passes."""
    module_archives = {
        "test_phase3_workflow.py": ("output_phase1", "docs/audit/phase3"),
        "test_phase4_workflow.py": ("output_phase1",),
        "test_reproduction_phase1.py": ("output_phase1", "output_verified"),
    }
    function_archives = {
        "test_saved_phase1_source_and_aligned_comparison": ("output_phase1",),
        "test_source_rejects_missing_session": ("output_phase1",),
        "test_cli_end_to_end_and_source_unchanged": ("output_phase1",),
        "test_real_matrix_and_serialized_output_consistency": ("output_phase5",),
        "test_original_archives_match_normalized_recalculation": tuple(f"output_phase{p}" for p in (2, 3, 4, 5)),
    }
    independent_dashboard = {"test_portfolio_drawdowns_follow_running_peak", "test_portfolio_cumulative_returns_rebases_at_selected_start"}
    required = {p for paths in [*module_archives.values(), *function_archives.values()] for p in paths}
    missing = sorted(p for p in required if not (ROOT / p).exists())
    if config.getoption("--require-archives") and missing:
        raise pytest.UsageError("Original archives required but unavailable: " + ", ".join(missing))
    for item in items:
        name = item.originalname or item.name
        dependencies = module_archives.get(item.path.name, function_archives.get(name, ()))
        if item.path.name == "test_dashboard_data.py" and name not in independent_dashboard:
            dependencies = ("output_phase1",)
        if dependencies:
            item.add_marker(pytest.mark.archive)
            unavailable = [p for p in dependencies if not (ROOT / p).exists()]
            if unavailable:
                item.add_marker(pytest.mark.skip(reason="Original raw-audit archives not distributed; use normalized-sample integration tests. Missing: " + ", ".join(unavailable)))


@pytest.fixture(scope="session")
def demo_results(tmp_path_factory):
    """Actually recompute the published sample, even when old outputs are present."""
    from portfolio_analysis.research_bundle import build_bundle
    target = tmp_path_factory.mktemp("demo") / "result"
    with patch("socket.socket.connect", side_effect=AssertionError("Offline reproduction attempted network access")):
        build_bundle(target)
    return target


@pytest.fixture
def yahoo_payload():
    fixture_path = Path(__file__).parent / "fixtures" / "yahoo_chart.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def eastmoney_payload():
    fixture_path = Path(__file__).parent / "fixtures" / "eastmoney_kline.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))
