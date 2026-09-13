"""Research presentation of archived Phase 1–5 evidence."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
import pandas as pd
import plotly.express as px
import streamlit as st
from portfolio_analysis.research_display import (
    PAGES,COMMON_LIMITS,CONVENTIONS,ResearchDataError,ResearchResultsMissing,result_root,read_table,tracking_view,robustness_view,findings)
from portfolio_analysis.deployment import default_results_missing, ensure_default_results

st.set_page_config(page_title="ETF与多资产研究",layout="wide")
st.title("ETF与多资产研究")
st.caption("Tracking · Walk-Forward · Index Construction · Robustness | 已归档研究证据")
page=st.sidebar.radio("研究导航",PAGES)
st.sidebar.caption("首次启动离线准备固定样本，此后筛选已保存结果。252日为既定默认值，不代表最佳参数。")
if default_results_missing(ROOT):
    try:
        with st.spinner("首次启动：正在从固定历史输入生成研究结果，请稍候。"):
            ensure_default_results(ROOT)
    except Exception as error:
        st.error(f"自动准备研究结果失败：{error}。请检查输入完整性、依赖版本及结果目录写权限后重试。")
        st.stop()
if (result_root(ROOT)/"bundle.json").exists():
    st.caption("固定样本重算结果 · 来源标注的标准化输入 · 未包含完整原始采集审计包")

def table(frame):
    formats={c:("{:.2%}" if any(t in c for t in ["return","volatility","drawdown","tracking_error","tracking_difference","weight","turnover","historical_var","historical_cvar"]) and not any(t in c for t in ["date","count","status"]) else "{:.4f}") for c in frame.select_dtypes("number").columns}
    for c in formats:
        if any(t in c for t in ["count","observations","window","cost_bps","rebalance_every"]):formats[c]="{:.0f}"
    st.dataframe(frame.style.format(formats,na_rep="unavailable"),hide_index=True,use_container_width=True)
    st.caption("比例显示为%；Sharpe / IR / HHI为无量纲。下载CSV保留原始小数；缺失值表示不可得，不是0。")

def chart(d,x,y,color=None,percent=False):
    fig=px.line(d,x=x,y=y,color=color)
    if percent:fig.update_yaxes(tickformat=".1%")
    st.plotly_chart(fig,use_container_width=True)

def evidence_download(d,name):
    st.download_button("下载当前证据表",d.to_csv(index=False).encode("utf-8-sig"),file_name=name,mime="text/csv")

def start(question,method):
    st.subheader("Research Question");st.write(question)
    st.subheader("Methodology");st.write(method)
    st.subheader("Evidence")

def finish(text,limits):
    st.subheader("Findings");st.write(text)
    st.subheader("Limitations");st.write(limits);st.caption(COMMON_LIMITS)

try:
    if page=="研究概览":
        st.write("研究编制规则、资产风险与数据口径如何影响可解释的ETF研究结论。")
        for text in findings(ROOT):st.markdown("- "+text)
        st.info("结论是当前可用样本的描述，不代表统计显著优势或实盘盈利能力。")
        st.markdown("从侧栏进入四条研究主线；每页均提供问题、方法、证据、发现及限制。")
        st.caption("Phase 1：方法与数据审计基础；Phase 2–5：研究证据；Phase 6：展示整理。")
    elif page=="ETF Tracking Research":
        s=read_table(ROOT,3,"summary")
        pair=st.selectbox("ETF / 比较对象",s.pair_id.tolist(),index=s.index[s.status=="comparable"][0])
        row,d=tracking_view(ROOT,pair)
        start("ETF与基准的收益是否可比？收益偏离是否稳定？",
              "先按共同交易日对齐，不未来填充。官方价格基准与全收益研究参考分别列示；TD为累计收益差，TE为日差额样本标准差×√252，IR为日差额均值/标准差×√252；滚动窗口63日。")
        st.caption(f"{row.sample_start} → {row.sample_end}；首笔收益 {row.first_return_date}；匹配收益 {row.matched_observation_count}；ETF口径 {row.etf_value_type}；基准 {row.benchmark_code} / {row.benchmark_type}；角色 {row.comparison_role}")
        if row.status!="comparable":st.warning("unavailable：收益口径不匹配，以下曲线仅作描述性比较，不能称严格跟踪误差。原因："+str(row.reasons))
        else:st.info("comparable 表示在披露假设下可比，并非独立数据认证；全收益研究参考不是官方价格基准。")
        chart(d,"date",["etf_cumulative_return","benchmark_cumulative_return"],percent=True)
        cols=["ticker","benchmark_code","comparison_role","status","matched_observation_count","tracking_difference","annualized_tracking_error","information_ratio","etf_annualized_volatility","benchmark_annualized_volatility","etf_maximum_drawdown","benchmark_maximum_drawdown"]
        table(row[cols].to_frame().T.infer_objects())
        if row.status=="comparable":
            chart(d,"date","rolling_tracking_error",percent=True)
            chart(d,"date","excess_return",percent=True)
        chart(d,"date","rolling_correlation")
        evidence_download(d,"tracking_selected.csv")
        with st.expander("全部基准映射与口径状态"):table(s[["ticker","benchmark_code","comparison_role","etf_value_type","benchmark_type","status","reasons"]])
        finish(findings(ROOT)[4],"510300/510500分红再投资依赖事件完整性与理论除息日约定；159915披露精度与历史修订未排除。黄金估值时点、国债净价与NAV差异限制可比性；不能将收益差全部归因于管理费或alpha。官方来源见数据附录。")
    elif page=="Walk-Forward Portfolio Research":
        freq=st.selectbox("调仓间隔（交易日）",[21,63])
        cost=st.selectbox("交易成本 bps",[0,5,10,20],index=2)
        start("最低风险是否来自分散配置，还是来自国债集中？交易摩擦如何改变结果？",
              "252个交易日估计窗口；仅使用执行日前历史。执行后首笔收益、非调仓日权重漂移；换手基于调仓前权重；0/5/10/20bps为比例成本假设。")
        s=read_table(ROOT,2,"summary");s=s[(s.rebalance_every==freq)&(s.cost_bps==cost)]
        d=read_table(ROOT,2,"daily");d=d[(d.rebalance_every==freq)&(d.cost_bps==cost)]
        st.caption(f"{s.start.iloc[0]} → {s.end.iloc[0]}；{s.observations.iloc[0]}个共同收益日；前复权市场价格；21/63交易日不等于日历月末/季末。")
        lines=d.melt(id_vars=["date","strategy"],value_vars=["gross_nav","net_nav"],var_name="basis",value_name="NAV")
        lines["series"]=lines.strategy+" / "+lines.basis
        chart(lines,"date","NAV","series")
        table(s);evidence_download(s,"portfolio_metrics.csv")
        chart(d,"date","hhi","strategy")
        chart(d,"date","maximum_weight","strategy",True)
        strategy=st.selectbox("查看成分权重",s.strategy.unique())
        w=read_table(ROOT,2,"weights");w=w[(w.rebalance_every==freq)&(w.cost_bps==cost)&(w.strategy==strategy)]
        chart(w,"date","end_weight","symbol",True)
        trades=read_table(ROOT,2,"trades");trades=trades[(trades.rebalance_every==freq)&(trades.cost_bps==cost)]
        with st.expander("调仓、初始建仓与交易成本明细"):table(trades)
        finish(findings(ROOT)[0]+" "+findings(ROOT)[1],
               "集中度结论的跨窗口证据来自Robustness页，不把本页单一窗口外推。固定样本、前复权价格、历史版本未知；费用不含完整价差、冲击、税费及容量约束。")
    elif page=="Index Construction Research":
        freq=st.selectbox("日历调仓频率",["monthly","quarterly"])
        start("等权与逆波动编制规则如何影响收益、换手和集中度？",
              "Universe → Eligibility → Weighting → Rebalance → Index Calculation。252日窗口；仅执行日前数据；日历月末/季末调仓，持仓自然漂移，初始指数1000。")
        s=read_table(ROOT,4,"summary");s=s[s.frequency==freq]
        d=read_table(ROOT,4,"daily");d=d[d.index_id.isin(s.index_id)]
        st.caption(f"首笔收益 {s.first_return_date.iloc[0]} → {s.end_date.iloc[0]}；{s.evaluation_count.iloc[0]}个共同收益日；前复权市场价格；Gross指数，未建模Net。")
        chart(d,"date","index_level","index_id")
        table(s);chart(d,"date","hhi","index_id");evidence_download(s,"index_metrics.csv")
        for name in ["components","rebalances"]:
            t=read_table(ROOT,4,name)
            if "index_id" in t:t=t[t.index_id.isin(s.index_id)]
            with st.expander("成分与权重" if name=="components" else "调仓与换手"):table(t)
        st.warning("Market Cap Weighted Index：跳过，没有可靠历史市值序列。")
        finish("Inverse Volatility Index的低波动伴随国债集中；Equal Weight更均衡但风险较高。不同调仓规则有收益与换手权衡，不选择收益最高的规则。",
               "五只ETF是固定研究Universe，不代表完整历史可投资集合。此处为ETF规则指数，非官方发布指数。日历调仓与Phase 2交易日间隔不同，不能无条件合并排名。")
    elif page=="Robustness Analysis":
        all_s=read_table(ROOT,5,"sensitivity")
        group=st.selectbox("共同评价组",["all_windows","extended_126_252"])
        period=st.selectbox("预定义子区间",all_s.loc[all_s.group_id==group,"period_id"].unique())
        engine=st.selectbox("研究对象",["phase2","phase4"])
        cost=st.selectbox("交易成本 bps",[0,5,10,20],index=2) if engine=="phase2" else 0
        s,f=robustness_view(ROOT,group,period,engine,cost)
        start("结论是否依赖窗口、日期或调仓规则？",
              "126/252/504日窗口；同组同区间共同评价日期；连续持仓只重基绩效，不在子区间重新建仓。504日不足明确跳过，不缩短窗口；全部参数保留，不选择最佳参数。")
        v=s[s.status=="ok"]
        st.caption(f"{v.first_return_date.iloc[0]} → {v.end_date.iloc[0]}；{v.evaluation_count.iloc[0]}个共同收益日；"+("Phase 2：21/63日；Net" if engine=="phase2" else "Phase 4：日历月/季；Gross"))
        basis="net" if engine=="phase2" else "gross"
        cols=["strategy","window","frequency","status","reason","evaluation_count",basis+"_annualized_return",basis+"_annualized_volatility",basis+"_sharpe_ratio",basis+"_maximum_drawdown","average_hhi","bond_daily_mean","annualized_maintenance_turnover"]
        table(s[cols]);evidence_download(s,"robustness_selected.csv")
        v=v.copy();v["series"]=v.strategy+" / "+v.frequency
        chart(v,"window",basis+"_annualized_volatility","series",True)
        chart(v,"window","average_hhi","series")
        st.write("月度减季度：正值表示月度更高。收益与换手须同时比较。")
        table(f)
        with st.expander("预定义比较的稳定性汇总"):
            stable=read_table(ROOT,5,"stability_summary")
            table(stable[stable.group_id==group])
        finish(findings(ROOT)[2]+" "+findings(ROOT)[3],
               "主组仅207日，较长组451日且无法评价504窗口；短子区间年化噪声大。完整期与子区间重叠，不是独立试验；无统计显著性结论。")
    else:
        st.subheader("数据与收益口径")
        st.write(CONVENTIONS);st.write(COMMON_LIMITS)
        st.write("Phase 1/2/4/5采用前复权市场价格，不是经独立认证的NAV总收益；旧快照抓取时间为unknown_legacy_snapshot。Phase 3另使用NAV/分红及基准序列，不能混用。")
        mapping=pd.read_json(ROOT/"config/benchmarks.json",typ="series")
        for item in mapping["etfs"]:
            b=item["official_benchmark"]
            st.markdown(f"**{item['ticker']}：{b['name']}（{b['code']}）**")
            for url in b.get("evidence",[]):st.markdown(f"[官方基准证据]({url})")
        st.write("缺失、重复与排除事件保存在各阶段报告；禁止未来填充，未认证的指标明确不可得。")
        for phase in range(1,6):
            p=ROOT/f"docs/audit/phase{phase}_report.md"
            st.download_button(f"下载 Phase {phase} 研究报告",p.read_bytes(),file_name=p.name)
        st.caption("output_verified 是旧错误结果审计记录，不作为有效研究证据。Phase 1–5结果原样保留。")
except ResearchResultsMissing:
    st.info("研究结果尚未生成，请先运行以下命令。")
    st.code("python scripts/build_research_demo.py", language="bash")
    st.write("本项目研究ETF跟踪、组合风险、指数规则与稳健性。生成过程使用固定公开来源样本，复用已有研究函数，不下载最新数据。")
    st.caption("如已使用自定义目录，请将 ETF_RESEARCH_RESULTS 设置为对应结果目录。现有目录不覆盖；选择新目录重新生成。")
    with st.expander("研究方法、发现和局限"):
        st.markdown((ROOT/"docs/RESEARCH_SUMMARY.md").read_text(encoding="utf-8"))
    st.info("数据与方法附录仍可直接访问。")
except (ResearchDataError,OSError,KeyError,ValueError) as error:
    st.error(f"研究证据不可用：{error}")
    st.stop()
