import runpy
import shutil
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def test_rebuild_uses_preserved_raw_not_mutable_live_cache(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "output_verified", tmp_path / "output_verified")
    shutil.copytree(ROOT / "output_phase1", tmp_path / "output_phase1")
    shutil.copytree(ROOT / "data/raw", tmp_path / "data/raw")
    (tmp_path / "data/raw/eastmoney_510300.SS.json").write_text("invalid live cache")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["rebuild_phase1.py", "--output-dir", "reproduced"])
    runpy.run_path(str(ROOT / "scripts/rebuild_phase1.py"), run_name="__main__")
    expected = pd.read_csv(ROOT / "output_phase1/before_vs_after.csv")
    actual = pd.read_csv(tmp_path / "reproduced/before_vs_after.csv")
    pd.testing.assert_frame_equal(actual, expected, rtol=1e-10, atol=1e-12)
