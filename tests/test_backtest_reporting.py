import json
import sqlite3
import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.backtest_reporting import run_scenarios, export_package, load_phase1_source, compare_phase1

def sample():
    return pd.DataFrame(np.random.default_rng(8).normal(.0002,.01,(330,3)),
        index=pd.bdate_range("2020-01-01",periods=330),columns=["a","b","c"])

def test_all_scenarios_common_dates_and_metrics():
    tables,meta=run_scenarios(sample())
    assert len(tables["summary"])==48
    assert meta["scenario_count"]==24
    grouped=tables["daily"].groupby(["strategy","rebalance_every","cost_bps"])
    dates=[tuple(x.date) for _,x in grouped]
    assert len(set(dates))==1
    summary=tables["summary"]
    for _,g in summary.groupby(["strategy","rebalance_every"]):
        net=g[g.basis=="net"].sort_values("cost_bps")
        assert (net.total_return.diff().iloc[1:]<=1e-12).all()
    required={"annualized_return","annualized_volatility","sharpe_ratio","sortino_ratio",
              "maximum_drawdown","calmar_ratio","historical_var","historical_cvar"}
    assert required.issubset(summary)
    assert {"mean_hhi","max_hhi","mean_maximum_weight","peak_weight","initial_turnover",
            "subsequent_turnover","transaction_cost","annualized_turnover"}.issubset(tables["diagnostics"])
    assert len(tables["metric_status"])==48*9

def test_export_roundtrip_and_no_overwrite(tmp_path):
    tables,meta=run_scenarios(sample(),frequencies=(21,),costs=(0,))
    out=tmp_path/"package"
    export_package(tables,meta,out)
    with sqlite3.connect(out/"analysis.sqlite") as con:
        for name,frame in tables.items():
            saved=pd.read_sql_query('SELECT * FROM '+name,con)
            assert len(saved)==len(frame)
    assert json.loads((out/"methodology.json").read_text(encoding="utf-8"))["scenario_count"]==3
    with pytest.raises(ValueError,match="exists"):
        export_package(tables,meta,out)

def test_saved_phase1_source_and_aligned_comparison():
    root=__import__("pathlib").Path(__file__).resolve().parents[1]
    r,meta=load_phase1_source(root/"output_phase1")
    assert len(r)==725 and r.shape[1]==5
    tables,_=run_scenarios(r,frequencies=(21,),costs=(0,))
    comparison=compare_phase1(root/"output_phase1",tables["daily"])
    aligned=comparison[comparison.comparison=="common_dates"]
    assert aligned.start.nunique()==1 and aligned.end.nunique()==1
    assert set(aligned.observations)=={218}
    assert len(comparison[comparison.phase=="phase1"])==4
    assert (comparison[(comparison.phase=="phase2")&(comparison.comparison=="native")].observations==472).all()

def test_source_rejects_missing_session(tmp_path):
    import shutil
    root=__import__("pathlib").Path(__file__).resolve().parents[1]
    source=tmp_path/"source"
    shutil.copytree(root/"output_phase1",source)
    p=source/"powerbi/prices.csv"
    prices=pd.read_csv(p)
    prices=prices[prices.date!="2024-01-02"]
    prices.to_csv(p,index=False)
    with pytest.raises(ValueError):
        load_phase1_source(source)

def test_cli_end_to_end_and_source_unchanged(tmp_path,monkeypatch):
    import runpy
    from pathlib import Path
    from portfolio_analysis.backtest_reporting import file_hashes
    root=Path(__file__).resolve().parents[1]
    source=root/"output_phase1"
    before=file_hashes(source)
    main=runpy.run_path(str(root/"scripts/run_phase2.py"))["main"]
    monkeypatch.chdir(tmp_path)
    assert main(["--source",str(source),"--output-dir",str(tmp_path/"result")])==0
    meta=json.loads((tmp_path/"result/methodology.json").read_text(encoding="utf-8"))
    assert meta["scenario_count"]==24 and meta["evaluation_count"]==472
    assert file_hashes(source)==before
    copied=file_hashes(tmp_path/"result/input_phase1")
    assert copied==before
