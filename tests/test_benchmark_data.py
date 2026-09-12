import json
import pandas as pd
import pytest
from portfolio_analysis.benchmark_data import parse_csi, parse_efunds, parse_eastmoney_nav, merge_levels

def test_csi_identity_and_close():
    p={"code":"200","data":[{"tradeDate":"20240102","indexCode":"H00300","close":123.4}]}
    s=parse_csi(json.dumps(p),"H00300")
    assert s.iloc[0]==123.4
    with pytest.raises(ValueError):parse_csi(json.dumps(p),"000300")

def test_csi_duplicate_rejected():
    row={"tradeDate":"20240102","indexCode":"000300","close":100}
    with pytest.raises(ValueError):parse_csi(json.dumps({"code":"200","data":[row,row]}),"000300")

def test_efunds_cumulative_return_not_cumulative_nav():
    s=parse_efunds('mk_159915_all="0_1_2_3_4;20240102_0.50_1.2_1.6_0;20240103_0.65_1.3_1.7_0;";',"159915")
    assert s.iloc[0]==1.5
    assert s.iloc[1]==1.65

def test_efunds_identity():
    with pytest.raises(ValueError):parse_efunds('mk_000001_all="0_1;20240102_0.5;";',"159915")

def nav_text(events):
    rows=[dict(x=int(pd.Timestamp(d,tz="Asia/Shanghai").timestamp()*1000),y=y,unitMoney=event) for d,y,event in events]
    return 'var fS_code = "510300"; var Data_netWorthTrend = '+json.dumps(rows,ensure_ascii=False)+';'

def test_nav_cash_reinvestment_and_local_date():
    p=nav_text([("2024-01-02",10,""),("2024-01-03",9.5,"分红：每份派现金1元")])
    levels,events=parse_eastmoney_nav(p,"510300")
    assert levels.index[0]==pd.Timestamp("2024-01-02")
    assert levels.iloc[1]/levels.iloc[0]==pytest.approx(1.05)
    assert events.iloc[0].cash_per_share==1

def test_unknown_corporate_action_rejected():
    p=nav_text([("2024-01-02",10,""),("2024-01-03",5,"拆分：1折2")])
    with pytest.raises(ValueError,match="corporate"):parse_eastmoney_nav(p,"510300")

def test_merge_duplicates_audited_and_conflicts_rejected():
    s=pd.Series([1.,2.],pd.to_datetime(["2024-01-02","2024-01-03"]))
    levels,audit=merge_levels([s,s])
    assert len(levels)==2 and audit["identical_duplicates_removed"]==2
    with pytest.raises(ValueError):merge_levels([s,s*2])

def test_sge_close_not_weighted_average():
    from portfolio_analysis.benchmark_data import parse_sge
    html='<table><tr><!-- <td>1</td> --><td>2024-01-02</td><td>Au99.99</td><td>1</td><td>2</td><td>1</td><td>450</td><td>0</td><td>0</td><td>449</td></tr></table>'
    assert parse_sge(html).iloc[0]==450

def test_sge_old_date_checked():
    from portfolio_analysis.benchmark_data import parse_sge
    html='<h1>上海黄金交易所2023年8月14日交易行情</h1><tr><td>Au99.99</td><td>1</td><td>2</td><td>1</td><td>455.95</td></tr>'
    assert parse_sge(html,"2023-08-14").iloc[0]==455.95
    with pytest.raises(ValueError):parse_sge(html,"2023-08-15")

def test_merge_does_not_silently_remove_missing():
    s=pd.Series([1.,float("nan")],pd.to_datetime(["2024-01-02","2024-01-03"]))
    with pytest.raises(ValueError):merge_levels([s])
