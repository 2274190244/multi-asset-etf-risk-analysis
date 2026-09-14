"""Direct Streamlit deployment must work without a manual build command."""
from concurrent.futures import ThreadPoolExecutor
import errno
from pathlib import Path
import shutil
import time

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_direct_start_builds_and_loads_all_pages(tmp_path, monkeypatch):
    monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    app_root = tmp_path / "app"
    app_root.mkdir()
    shutil.copy2(ROOT / "streamlit_app.py", app_root / "streamlit_app.py")
    for name in ("config", "data/research_demo"):
        shutil.copytree(ROOT / name, app_root / name)
    (app_root / "docs/audit").mkdir(parents=True)
    shutil.copy2(ROOT / "docs/RESEARCH_SUMMARY.md", app_root / "docs/RESEARCH_SUMMARY.md")
    for phase in range(1, 6):
        shutil.copy2(ROOT / f"docs/audit/phase{phase}_report.md", app_root / f"docs/audit/phase{phase}_report.md")
    assert not (app_root / "research_results").exists()
    app = AppTest.from_file(str(app_root / "streamlit_app.py")).run(timeout=120)
    from portfolio_analysis.research_display import PAGES
    for page in PAGES:
        app.radio[0].set_value(page).run(timeout=60)
        assert not app.exception and not app.error, page
        assert not any("研究结果尚未生成" in info.value for info in app.info), page
        if page not in ("研究概览", "数据与方法附录"):
            assert app.dataframe, page
    assert (app_root / "research_results/bundle.json").is_file()


def test_concurrent_start_only_builds_once(tmp_path, monkeypatch, demo_results):
    import portfolio_analysis.deployment as deployment
    monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    calls = []
    def build(destination, inputs):
        calls.append(destination)
        time.sleep(0.03)
        shutil.copytree(demo_results, destination)
    monkeypatch.setattr(deployment, "build_bundle", build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: deployment.ensure_default_results(tmp_path), range(4)))
    assert len(calls) == 1 and sum(results) == 1


def test_custom_missing_directory_is_not_replaced(tmp_path, monkeypatch):
    from portfolio_analysis.deployment import ensure_default_results
    monkeypatch.setenv("ETF_RESEARCH_RESULTS", str(tmp_path / "custom"))
    assert ensure_default_results(tmp_path) is False
    assert not (tmp_path / "research_results").exists()


@pytest.mark.parametrize("folder", ["research_results", "output_phase2"])
def test_existing_results_are_never_overwritten(tmp_path, monkeypatch, folder):
    from portfolio_analysis.deployment import ensure_default_results
    monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    destination = tmp_path / folder
    destination.mkdir()
    sentinel = destination / "sha256.json"
    sentinel.write_text("corrupt")
    assert ensure_default_results(tmp_path) is False
    assert sentinel.read_text() == "corrupt"


def test_failed_start_does_not_publish_and_can_retry(tmp_path, monkeypatch, demo_results):
    import portfolio_analysis.deployment as deployment
    monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    def fail(*args, **kwargs):
        raise ValueError("input hash mismatch")
    monkeypatch.setattr(deployment, "build_bundle", fail)
    with pytest.raises(ValueError, match="input hash"):
        deployment.ensure_default_results(tmp_path)
    assert not (tmp_path / "research_results").exists()
    monkeypatch.setattr(deployment, "build_bundle", lambda destination, inputs: shutil.copytree(demo_results, destination))
    assert deployment.ensure_default_results(tmp_path) is True


@pytest.mark.parametrize("race_error", [FileExistsError("another worker published"),
                                      OSError(errno.ENOTEMPTY, "another worker published")])
def test_other_process_publication_is_checked(tmp_path, monkeypatch, demo_results, race_error):
    import portfolio_analysis.deployment as deployment
    monkeypatch.delenv("ETF_RESEARCH_RESULTS", raising=False)
    def raced(destination, inputs):
        shutil.copytree(demo_results, destination)
        raise race_error
    monkeypatch.setattr(deployment, "build_bundle", raced)
    assert deployment.ensure_default_results(tmp_path) is False
    shutil.rmtree(tmp_path / "research_results")
    def corrupt_race(destination, inputs):
        raced_path = destination / "output_phase3"
        raced_path.mkdir(parents=True)
        (raced_path / "sha256.json").write_text("[]")
        raise FileExistsError("incomplete competing output")
    monkeypatch.setattr(deployment, "build_bundle", corrupt_race)
    with pytest.raises(ValueError):
        deployment.ensure_default_results(tmp_path)
