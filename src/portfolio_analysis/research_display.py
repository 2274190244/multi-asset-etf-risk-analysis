"""Read-only research presentation adapters. No strategy calculations or downloads."""
import hashlib
import json
from pathlib import Path
import pandas as pd

PAGES=["研究概览","ETF Tracking Research","Walk-Forward Portfolio Research",
       "Index Construction Research","Robustness Analysis","数据与方法附录"]
COMMON_LIMITS="回顾性研究；固定五只ETF存在样本选择/存续偏差。原始数据版本与真实可得时点未完全验证，不等于实盘或前瞻样本外能力。"
CONVENTIONS="年化252日；2%有效年无风险利率按(1.02)^(1/252)-1转为日利率；Sharpe使用同频日超额收益均值/样本标准差再年化。回撤为非正值，VaR保留损失口径符号。"

class ResearchDataError(ValueError):
    """Archived evidence missing or inconsistent."""

def read_table(root,phase,name):
    """Read one archived CSV after checking its SHA256; never fall back."""
    folder=Path(root)/f"output_phase{phase}"
    rel=f"{name}.csv" if phase==3 else f"tables/{name}.csv"
    path=folder/rel
    try:
        manifest=json.loads((folder/"sha256.json").read_text(encoding="utf-8"))
        content=path.read_bytes()
    except (OSError,ValueError) as error:
        raise ResearchDataError(f"缺少或无法读取 Phase {phase} / {name}；请检查归档结果包。") from error
    if manifest.get(rel)!=hashlib.sha256(content).hexdigest():
        raise ResearchDataError(f"结果校验失败：Phase {phase} / {name}")
    try:
        import io
        frame=pd.read_csv(io.BytesIO(content))
        for col in ["date","execution_date"]:
            if col in frame:frame[col]=pd.to_datetime(frame[col],format="mixed")
        return frame
    except (ValueError,pd.errors.ParserError) as error:
        raise ResearchDataError(f"结果格式错误：{path.name}") from error

def tracking_view(root,pair_id):
    """Return a single pair and its dates; suppress strict metrics on mismatch."""
    s=read_table(root,3,"summary")
    rows=s[s.pair_id==pair_id]
    if len(rows)!=1:raise ResearchDataError("Tracking 配对不存在或重复")
    row=rows.iloc[0].copy()
    d=read_table(root,3,"daily");d=d[d.pair_id==pair_id].copy()
    if row.status!="comparable":
        for col in ["tracking_difference","annualized_tracking_difference","annualized_tracking_error","information_ratio"]:
            row[col]=float("nan")
        d["rolling_tracking_error"]=float("nan")
    if len(d)!=row.selected_price_count or d.date.min()!=pd.Timestamp(row.sample_start) or d.date.max()!=pd.Timestamp(row.sample_end):
        raise ResearchDataError("Tracking 图表与表格日期不一致")
    return row,d

def robustness_view(root,group,period,engine,cost):
    """Select one date-comparable archived group, retaining skipped scenarios."""
    s=read_table(root,5,"sensitivity");f=read_table(root,5,"frequency_comparison")
    cost=0 if engine=="phase4" else cost
    mask=lambda x:(x.group_id==group)&(x.period_id==period)&(x.engine==engine)&(x.cost_bps==cost)
    s=s[mask(s)].copy();f=f[mask(f)&(f.basis==("net" if engine=="phase2" else "gross"))].copy()
    valid=s[s.status=="ok"]
    if s.empty:raise ResearchDataError("所选比较组不可得")
    for col in ["first_return_date","end_date","evaluation_count"]:
        if valid[col].nunique()>1:raise ResearchDataError("评价日期不一致")
    return s,f

def findings(root):
    """Generate shared evidence-backed prose for UI, README and Research Summary."""
    s=read_table(root,5,"stability_summary")
    b=s[s.question=="minimum_variance_bond_concentration"].set_index("group_id")
    return [
        f"Minimum Variance 在可用路径中持续高度集中于国债ETF：主比较组最低权重 {b.loc['all_windows','minimum']:.2%}，较长样本组 {b.loc['extended_126_252','minimum']:.2%}；不是跨市场、跨时期保证。",
        "Inverse Volatility 在已分析的同日期样本中持续降低相对 Equal Weight 的波动率，但明显集中于国债ETF，低风险不等于资产充分分散。",
        "更频繁调仓通常增加换手，但月度调仓没有在所有子区间稳定提高收益；须同时查看费用和配对差异，不能写成所有情景均增加换手。",
        "Sharpe、回撤和集中度对估计窗口及样本区间敏感；没有选择最佳参数，重叠子区间不属于独立统计实验。",
        "三只股票ETF可在已披露假设下相对全收益研究参考分析跟踪表现；官方价格基准未被替换，黄金与国债的严格跟踪指标保持 unavailable。"
    ]
