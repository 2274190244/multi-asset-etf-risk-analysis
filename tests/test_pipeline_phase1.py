import pandas as pd
import numpy as np
from portfolio_analysis.config import ASSETS
from portfolio_analysis.pipeline import run_pipeline
from portfolio_analysis.quality import china_sessions

def fixture():
    dates=china_sessions("2025-01-02","2025-06-30")
    rng=np.random.default_rng(5)
    frames=[]
    for a in ASSETS:
        frames.append(pd.DataFrame({"date":dates,"symbol":a.symbol,"asset_name":a.name,"asset_class":a.asset_class,
            "close":100*np.cumprod(1+rng.normal(.0001,.005,len(dates))),
            "source":"fixture","price_basis":"adjusted_close","retrieval_timestamp":"2026-01-01T00:00:00+00:00",
            "requested_start":"2025-01-02","requested_end":"2025-06-30"}))
    return pd.concat(frames,ignore_index=True)

def test_pipeline_evaluation_and_metadata(tmp_path):
    raw=fixture()
    result=run_pipeline(pd.Timestamp("2025-01-02").date(),pd.Timestamp("2025-06-30").date(),tmp_path/"out",price_data=raw)
    assert result.metadata["training_end"]<result.metadata["evaluation_start"]
    assert (tmp_path/"out/methodology.json").exists()
    assert (tmp_path/"out/powerbi/asset_data_quality.csv").exists()
    assert (tmp_path/"out/powerbi/data_quality_events.csv").exists()
    assert (tmp_path/"out/powerbi/source_metadata.csv").exists()
    times=pd.read_csv(tmp_path/"out/powerbi/portfolio_timeseries.csv")
    assert times.date.min()==result.metadata["evaluation_start"]

def test_quality_report_survives_insufficient_contiguous_sample(tmp_path):
    raw=fixture()
    # Every other session missing for one ETF: no usable long common path.
    bad=raw.symbol.eq(ASSETS[0].symbol)&raw.date.isin(raw.date.unique()[::2])
    result=run_pipeline(pd.Timestamp("2025-01-02").date(),pd.Timestamp("2025-06-30").date(),tmp_path/"out",price_data=raw.loc[~bad])
    assert result.metadata["status"]=="quality_only"
    assert (tmp_path/"out/powerbi/asset_data_quality.csv").exists()
    assert not (tmp_path/"out/powerbi/portfolio_metrics.csv").exists()

def test_weekend_request_boundary():
    assert len(china_sessions("2023-08-12","2023-08-15"))==2
