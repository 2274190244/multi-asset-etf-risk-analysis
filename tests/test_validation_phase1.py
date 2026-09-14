import pandas as pd
import pytest
from portfolio_analysis.quality import china_sessions
from portfolio_analysis.pipeline import run_pipeline
from test_pipeline_phase1 import fixture

def test_all_nontrading_request_is_empty():
    assert len(china_sessions("2026-01-03","2026-01-04"))==0

def test_unknown_basis_cannot_produce_performance(tmp_path):
    data=fixture();data["price_basis"]="unverified_magic"
    result=run_pipeline(pd.Timestamp("2025-01-02").date(),pd.Timestamp("2025-06-30").date(),tmp_path/"x",price_data=data)
    assert result.metadata["status"]=="quality_only"

def test_daily_provider_rows_without_metadata_are_rejected(tmp_path):
    data=fixture();data.loc[data.index[0],"source"]=""
    with pytest.raises(ValueError,match="metadata"):
        run_pipeline(pd.Timestamp("2025-01-02").date(),pd.Timestamp("2025-06-30").date(),tmp_path/"x",price_data=data)
