"""End-to-end archived-input reproduction without network."""
import hashlib
import json
from pathlib import Path
import runpy
import sqlite3
from contextlib import closing
import pandas as pd

def test_real_archived_inputs_and_all_etfs(tmp_path):
    run=runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/run_phase3.py"))
    target=tmp_path/"phase3"
    assert run["main"](["--output-dir",str(target)])==0
    summary=pd.read_csv(target/"summary.csv",dtype={"benchmark_code":str})
    assert len(summary)==8 and summary.ticker.nunique()==5
    refs=summary[summary.comparison_role=="total_return_reference"]
    assert set(refs.status)=={"comparable"}
    assert set(refs.matched_observation_count)=={725}
    assert refs.annualized_tracking_error.notna().all()
    official=summary[summary.comparison_role=="official"]
    assert official.annualized_tracking_error.isna().all()
    assert official.information_ratio.isna().all()
    meta=json.loads((target/"metadata.json").read_text(encoding="utf-8"))
    for source in meta["source_manifest"]:
        assert all(source[k] for k in ("source","price_basis","retrieval_timestamp","requested_start","requested_end","sha256"))
    with closing(sqlite3.connect(target/"tracking.sqlite")) as connection:
        assert connection.execute("select count(*) from summary").fetchone()[0]==8
    for name,digest in json.loads((target/"sha256.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest
