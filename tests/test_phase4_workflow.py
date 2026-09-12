import json
import runpy
from pathlib import Path
import pandas as pd

def test_real_phase4_reproduction(tmp_path):
    runner=runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/run_phase4.py"))
    target=tmp_path/"phase4"
    assert runner["main"](["--output-dir",str(target)])==0
    summary=pd.read_csv(target/"tables/summary.csv")
    assert len(summary)==4 and set(summary.status)=={"complete"}
    assert summary.evaluation_count.nunique()==1
    assert summary.first_return_date.nunique()==1
    meta=json.loads((target/"methodology.json").read_text(encoding="utf-8"))
    assert meta["source"]["rows_removed"]==0
    assert meta["market_cap_weighted"]["status"]=="skipped"
    ledger=pd.read_csv(target/"tables/rebalances.csv",parse_dates=["execution_date","estimation_end","first_effective_return_date"])
    assert set(ledger.estimation_count)=={252}
    assert (ledger.estimation_end<ledger.execution_date).all()
    assert (ledger.first_effective_return_date>ledger.execution_date).all()
    assert (ledger.loc[ledger.initial,"execution_date"].dt.month%3==0).all()
    assert (target/"input_phase1/raw/eastmoney_510300.SS.json").exists()
    assert meta["availability_evidence"]=="assumed"

def test_source_preserves_asset_gap_for_eligibility(tmp_path):
    import shutil,hashlib
    from portfolio_analysis.index_reporting import load_index_source
    source=tmp_path/"input"
    shutil.copytree("output_phase1",source)
    symbol="510300.SS";date="2024-06-03"
    raw=source/"raw"/("eastmoney_"+symbol+".json")
    data=json.loads(raw.read_text(encoding="utf-8"))
    data["data"]["klines"]=[r for r in data["data"]["klines"] if not r.startswith(date+",")]
    raw.write_text(json.dumps(data),encoding="utf-8")
    digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    prices=pd.read_csv(source/"powerbi/prices.csv")
    prices=prices[~((prices.symbol==symbol)&(prices.date==date))].copy()
    prices.loc[prices.symbol==symbol,"raw_sha256"]=digest
    prices.to_csv(source/"powerbi/prices.csv",index=False)
    provenance=pd.read_csv(source/"powerbi/source_metadata.csv")
    provenance.loc[provenance.symbol==symbol,"raw_sha256"]=digest
    provenance.to_csv(source/"powerbi/source_metadata.csv",index=False)
    returns,meta=load_index_source(source)
    assert pd.isna(returns.loc[date,symbol])
    assert pd.isna(returns.loc["2024-06-04",symbol])
    assert meta["missing_price_cells"]==1
    assert meta["missing_return_cells"]==2
    assert len(returns)==725
