import json
import hashlib
import sqlite3
from contextlib import closing
import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.index_reporting import load_index_rules, run_index_matrix, export_index_package
from test_index_construction import sample

def rules():
    cal,r,u=sample()
    c=load_index_rules()
    c["universe"]=u;c["estimation_window"]=20
    return cal,r,c

def test_four_rules_share_evaluation_dates_and_initial_turnover_separate():
    cal,r,c=rules()
    tables,meta=run_index_matrix(r,cal,c)
    s=tables["summary"]
    assert len(s)==4 and set(s.status)=={"complete"}
    assert s.evaluation_count.nunique()==1
    assert s.first_return_date.nunique()==1
    assert (s.initial_turnover==1).all()
    for row in s.itertuples():
        ledger=tables["rebalances"].query("index_id==@row.index_id")
        assert row.maintenance_turnover==pytest.approx(ledger.loc[~ledger.initial,"turnover"].sum())
        daily=tables["daily"].query("index_id==@row.index_id")
        assert row.cumulative_return==pytest.approx(daily.index_level.iloc[-1]/1000-1)
        assert row.annualized_maintenance_turnover==pytest.approx(row.maintenance_turnover*252/row.evaluation_count)
    assert meta["market_cap_weighted"]["status"]=="skipped"
    assert len(tables["monthly_vs_quarterly"])==2

def test_partial_failures_not_scored_as_success():
    cal,r,c=rules()
    r.loc["2023-04-10","A"]=np.nan
    tables,meta=run_index_matrix(r,cal,c)
    assert set(tables["summary"].status)=={"failed"}
    assert tables["summary"].annualized_return.isna().all()
    assert len(tables["failures"])==4
    assert not tables["daily"].empty
    assert set(tables["daily"].path_status)=={"failed"}

def test_export_keeps_time_of_day_and_does_not_overwrite(tmp_path):
    cal,r,c=rules()
    tables,meta=run_index_matrix(r,cal,c)
    out=tmp_path/"report"
    export_index_package(tables,meta,out)
    csv=pd.read_csv(out/"tables/eligibility.csv")
    assert csv.decision_time.str.contains("14:59").all()
    with closing(sqlite3.connect(out/"analysis.sqlite")) as conn:
        assert conn.execute("select count(*) from summary").fetchone()[0]==4
    for name,h in json.loads((out/"sha256.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==h
    with pytest.raises(ValueError):export_index_package(tables,meta,out)

def test_unknown_rule_config_rejected(tmp_path):
    c=load_index_rules();c["rebalance_frequencies"]=["21","63"]
    p=tmp_path/"rules.json";p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError):load_index_rules(p)

@pytest.mark.parametrize("key,value",[("signal_cutoff","same-day close"),("execution","open t"),
                                     ("inception","arbitrary first row"),("schema_version",999)])
def test_fixed_rule_text_cannot_contradict_implementation(tmp_path,key,value):
    c=load_index_rules();c[key]=value
    p=tmp_path/"rules.json";p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError):load_index_rules(p)

def test_sqlite_timestamp_keeps_just_late_nanosecond(tmp_path):
    cal,r,c=rules()
    tables,meta=run_index_matrix(r,cal,c)
    late=pd.Timestamp("2023-03-31 14:59:00.000000001")
    tables["nanosecond_probe"]=pd.DataFrame({"available_at":[late]})
    out=tmp_path/"exact"
    export_index_package(tables,meta,out)
    with closing(sqlite3.connect(out/"analysis.sqlite")) as con:
        saved=con.execute("select available_at from nanosecond_probe").fetchone()[0]
    assert pd.Timestamp(saved)==late
