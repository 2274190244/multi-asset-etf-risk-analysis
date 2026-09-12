import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.tracking_reporting import analyze_pair, export_tracking

def inputs():
    d=pd.bdate_range("2024-01-02",periods=5)
    e=pd.Series([100,102,101,104,105],d)
    b=pd.Series([100,101,100,102,103],d)
    em=dict(data_status="available",value_type="nav_total_return",return_basis_verified=True,
            currency="CNY",valuation_time="equity_close",evidence=["nav"])
    bm=dict(data_status="available",benchmark_type="equity_total_return",definition_status="confirmed",
            currency="CNY",valuation_time="equity_close",evidence=["method"])
    return d,e,b,em,bm

def test_report_gate_masks_all_tracking_fields():
    d,e,b,em,bm=inputs();bm["benchmark_type"]="equity_price"
    r=analyze_pair("test",e,b,em,bm,d,d,window=3)
    assert r["summary"]["status"]=="basis_mismatch"
    assert np.isnan(r["summary"]["annualized_tracking_error"])
    assert np.isnan(r["summary"]["tracking_difference"])
    assert r["daily"].rolling_tracking_error.isna().all()
    assert np.isfinite(r["summary"]["cumulative_return_difference"])
    assert r["summary"]["matched_observation_count"]==4

def test_unavailable_no_fake_results():
    d,e,b,em,bm=inputs();bm["data_status"]="unavailable"
    r=analyze_pair("test",e,None,em,bm,d,d)
    assert r["summary"]["status"]=="unavailable"
    assert r["summary"]["matched_observation_count"]==0
    assert r["daily"].empty

def test_export_preserves_existing_output(tmp_path):
    d,e,b,em,bm=inputs()
    r=analyze_pair("test",e,b,em,bm,d,d,window=3)
    target=tmp_path/"results"
    export_tracking([r],target,{"source":"test"})
    assert (target/"summary.csv").exists()
    assert (target/"metadata.json").exists()
    with pytest.raises(FileExistsError):export_tracking([r],target,{})
