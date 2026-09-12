import pytest
from portfolio_analysis.benchmark_config import load_benchmark_config, assess_comparability

def metadata():
    return (dict(data_status="available",value_type="nav_total_return",currency="CNY",
                 valuation_time="equity_close",return_basis_verified=True,evidence=["official-nav","distributions"]),
            dict(data_status="available",benchmark_type="equity_total_return",currency="CNY",
                 valuation_time="equity_close",definition_status="confirmed",evidence=["official-methodology"]))

def test_comparable():
    e,b=metadata()
    assert assess_comparability(e,b)["status"] == "comparable"

@pytest.mark.parametrize("basis",["equity_price","bond_clean_price","bond_full_price"])
def test_mismatch(basis):
    e,b=metadata();b["benchmark_type"]=basis
    assert assess_comparability(e,b)["status"] == "basis_mismatch"

def test_market_price_not_nav():
    e,b=metadata();e["value_type"]="forward_adjusted_market_price"
    assert assess_comparability(e,b)["status"] == "basis_mismatch"

def test_unavailable():
    e,b=metadata();b["data_status"]="unavailable"
    assert assess_comparability(e,b)["status"] == "unavailable"

@pytest.mark.parametrize("field,value",[("return_basis_verified",False),("evidence",[]),("currency","USD"),("valuation_time","unknown")])
def test_no_silent_assumptions(field,value):
    e,b=metadata();e[field]=value
    assert assess_comparability(e,b)["status"] != "comparable"

def test_official_mappings():
    c=load_benchmark_config()
    assert len(c["etfs"])==5
    b=next(x for x in c["etfs"] if x["ticker"]=="511010.SS")["official_benchmark"]
    assert b["code"]=="000140"
    assert b["benchmark_type"]=="bond_clean_price"
    assert b["evidence"]

def test_gold_requires_known_matching_contract():
    e,b=metadata()
    b["benchmark_type"]="gold_spot_close"
    assert assess_comparability(e,b)["status"]=="basis_mismatch"
