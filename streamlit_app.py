
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from portfolio_analysis.dashboard_data import (
    DashboardDataError,
    asset_cumulative_returns,
    correlation_wide,
    load_dashboard_data,
    portfolio_cumulative_returns,
    portfolio_drawdowns,
)


ASSET_COLORS = {
    "沪深300ETF": "#1F4E79",
    "中证500ETF": "#168C8C",
    "创业板ETF": "#D97706",
    "黄金ETF": "#7A6A36",
    "国债ETF": "#6B7280",
}
PORTFOLIO_LABELS = {
    "equal_weight": "等权组合",
    "minimum_volatility": "最低波动组合",
}
PORTFOLIO_COLORS = {
    "等权组合": "#1F4E79",
    "最低波动组合": "#D97706",
}
st.set_page_config(
    page_title="多资产 ETF 收益与风险分析",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    :root {
        --navy: #1F4E79;
        --teal: #168C8C;
        --orange: #D97706;
        --ink: #18212B;
        --muted: #5E6B78;
        --line: #DCE3EA;
        --surface: #F7F9FB;
    }
    .stApp { background: #FFFFFF; color: var(--ink); }
    .block-container { max-width: 1480px; padding-top: 1.25rem; padding-bottom: 2.5rem; }
    h1, h2, h3 { color: var(--navy); letter-spacing: 0; }
    h1 { font-size: 2rem !important; line-height: 1.2 !important; margin-bottom: 0.25rem !important; }
    h2 { font-size: 1.35rem !important; }
    h3 { font-size: 1.05rem !important; }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 6px;
        min-height: 104px;
        padding: 0.85rem 1rem;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--ink); font-weight: 650; }
    [data-testid="stSidebar"] { background: #F7F9FB; border-right: 1px solid var(--line); }
    [data-baseweb="tab-list"] { gap: 0.35rem; border-bottom: 1px solid var(--line); }
    [data-baseweb="tab"] { min-height: 44px; padding-left: 1rem; padding-right: 1rem; }
    [data-baseweb="tab"][aria-selected="true"] { color: var(--navy); font-weight: 650; }
    .section-note { color: var(--muted); font-size: 0.88rem; line-height: 1.55; }
    .method-strip {
        border-left: 3px solid var(--teal);
        background: #F5FAFA;
        padding: 0.65rem 0.85rem;
        color: #344451;
        font-size: 0.88rem;
        margin: 0.35rem 0 0.9rem 0;
    }
    .footer-note { color: var(--muted); font-size: 0.82rem; border-top: 1px solid var(--line); padding-top: 0.8rem; }
    @media (max-width: 700px) {
        .block-container { padding-top: 3rem; padding-left: 1rem; padding-right: 1rem; }
        h1 { font-size: 1.32rem !important; }
        [data-testid="stMetric"] { min-height: 92px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def get_dashboard_data():
    return load_dashboard_data(PROJECT_ROOT)


def polish_figure(figure, *, percent_y=False, height=430):
    figure.update_layout(
        height=height,
        margin=dict(l=24, r=18, t=48, b=24),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color="#263442", size=13),
        hoverlabel=dict(bgcolor="#FFFFFF", font_color="#18212B"),
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    figure.update_xaxes(showgrid=False, linecolor="#DCE3EA", zeroline=False)
    figure.update_yaxes(gridcolor="#E8EDF2", linecolor="#DCE3EA", zeroline=False)
    if percent_y:
        figure.update_yaxes(tickformat=".1%")
    return figure


def metric_table(frame, include_asset=True):
    columns = [
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "maximum_drawdown",
        "historical_var",
    ]
    labels = {
        "asset_name": "资产",
        "portfolio_label": "组合",
        "annualized_return": "年化收益率",
        "annualized_volatility": "年化波动率",
        "sharpe_ratio": "夏普比率",
        "maximum_drawdown": "最大回撤",
        "historical_var": "95% 历史 VaR",
    }
    name_column = "asset_name" if include_asset else "portfolio_label"
    display = frame[[name_column, *columns]].rename(columns=labels).copy()
    return display.style.format(
        {
            "年化收益率": "{:.2%}",
            "年化波动率": "{:.2%}",
            "夏普比率": "{:.2f}",
            "最大回撤": "{:.2%}",
            "95% 历史 VaR": "{:.2%}",
        }
    )


try:
    data = get_dashboard_data()
except DashboardDataError as exc:
    st.error(f"看板数据校验失败：{exc}")
    st.stop()


facts = data.resume_facts
min_date = data.prices["date"].min().date()
max_date = data.prices["date"].max().date()

st.title("多资产 ETF 收益与风险分析平台")
st.caption(
    f"数据区间：{facts['start_date']} 至 {facts['end_date']} ｜ "
    "来源：东方财富，Yahoo Finance 作为单资产回退 ｜ 个人项目，AI Agent 辅助开发"
)

overview_columns = st.columns(4)
overview_columns[0].metric("价格记录", f"{facts['price_rows']:,}")
overview_columns[1].metric("ETF 数量", str(facts["asset_count"]))
overview_columns[2].metric("收益与风险指标", str(facts["risk_metric_count"]))
overview_columns[3].metric("投资组合", str(facts["portfolio_count"]))


with st.sidebar:
    st.header("筛选条件")
    symbols = list(data.asset_names)
    selected_symbols = st.multiselect(
        "ETF",
        options=symbols,
        default=symbols,
        format_func=lambda symbol: data.asset_names[symbol],
        help="筛选市场表现和资产风险图表。",
    )
    selected_dates = st.date_input(
        "日期范围",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        format="YYYY-MM-DD",
        help="日期筛选会重新计算所选区间累计收益，并用于组合时间序列图。",
    )
    st.markdown("### 指标口径")
    st.caption(
        "年化收益率采用几何复合；波动率按 252 个交易日年化；夏普比率使用 2% 无风险利率；"
        "VaR 为 95% 置信水平的一日历史损失估计。"
    )


if isinstance(selected_dates, (tuple, list)) and len(selected_dates) >= 2:
    selected_start, selected_end = selected_dates[:2]
elif isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 1:
    selected_start = selected_end = selected_dates[0]
elif isinstance(selected_dates, (tuple, list)):
    selected_start, selected_end = min_date, max_date
else:
    selected_start = selected_end = selected_dates

try:
    asset_performance = asset_cumulative_returns(
        data.prices,
        symbols=selected_symbols,
        start_date=selected_start,
        end_date=selected_end,
    )
except DashboardDataError as exc:
    st.warning(str(exc))
    st.stop()

selected_metrics = data.asset_metrics.loc[
    data.asset_metrics["symbol"].isin(selected_symbols)
].copy()

market_tab, risk_tab, portfolio_tab, quality_tab = st.tabs(
    ["市场表现", "风险分析", "组合分析", "数据质量"]
)


with market_tab:
    st.subheader("所选区间累计收益")
    st.markdown(
        '<div class="method-strip">各 ETF 在筛选区间首个交易日统一归一为 0%，便于比较价格路径，不代表实际持仓收益。</div>',
        unsafe_allow_html=True,
    )
    performance_figure = px.line(
        asset_performance,
        x="date",
        y="cumulative_return",
        color="asset_name",
        line_dash="asset_name",
        color_discrete_map=ASSET_COLORS,
        line_dash_sequence=["solid", "dash", "dot", "dashdot", "longdash"],
        labels={"date": "日期", "cumulative_return": "累计收益", "asset_name": "ETF"},
    )
    performance_figure.update_traces(line=dict(width=2.2), hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2%}<extra>%{fullData.name}</extra>")
    st.plotly_chart(polish_figure(performance_figure, percent_y=True), width="stretch")

    st.subheader("收益与波动特征")
    scatter = px.scatter(
        selected_metrics,
        x="annualized_volatility",
        y="annualized_return",
        color="asset_name",
        text="asset_name",
        color_discrete_map=ASSET_COLORS,
        labels={
            "annualized_volatility": "年化波动率",
            "annualized_return": "年化收益率",
            "asset_name": "ETF",
        },
    )
    scatter.update_traces(marker=dict(size=12, line=dict(width=1, color="#FFFFFF")), textposition="top center")
    scatter.update_xaxes(tickformat=".1%")
    scatter.update_yaxes(tickformat=".1%")
    st.plotly_chart(polish_figure(scatter, height=420), width="stretch")

    st.markdown("#### 资产指标明细")
    st.caption("以下指标采用完整验证区间计算，不随侧边栏日期变化。")
    st.dataframe(metric_table(selected_metrics), width="stretch", hide_index=True)


with risk_tab:
    st.subheader("核心风险指标")
    left_chart, right_chart = st.columns(2)
    risk_frame = selected_metrics[["asset_name", "maximum_drawdown", "historical_var"]].copy()
    risk_frame["最大回撤幅度"] = risk_frame["maximum_drawdown"].abs()
    risk_long = risk_frame.melt(
        id_vars="asset_name",
        value_vars=["最大回撤幅度", "historical_var"],
        var_name="指标",
        value_name="数值",
    )
    risk_long["指标"] = risk_long["指标"].replace({"historical_var": "95% 历史 VaR"})
    risk_bar = px.bar(
        risk_long,
        x="asset_name",
        y="数值",
        color="指标",
        barmode="group",
        color_discrete_map={"最大回撤幅度": "#1F4E79", "95% 历史 VaR": "#D97706"},
        labels={"asset_name": "ETF", "数值": "风险幅度"},
    )
    risk_bar.update_traces(hovertemplate="%{x}<br>%{y:.2%}<extra>%{fullData.name}</extra>")
    left_chart.plotly_chart(polish_figure(risk_bar, percent_y=True, height=410), width="stretch")

    sharpe_bar = px.bar(
        selected_metrics.sort_values("sharpe_ratio"),
        x="asset_name",
        y="sharpe_ratio",
        color="asset_name",
        color_discrete_map=ASSET_COLORS,
        labels={"asset_name": "ETF", "sharpe_ratio": "夏普比率"},
    )
    sharpe_bar.update_traces(hovertemplate="%{x}<br>夏普比率 %{y:.2f}<extra></extra>")
    right_chart.plotly_chart(polish_figure(sharpe_bar, height=410), width="stretch")

    st.subheader("资产收益相关性")
    correlation = correlation_wide(data.correlation_matrix, data.asset_names)
    heatmap = go.Figure(
        data=go.Heatmap(
            z=correlation.to_numpy(),
            x=correlation.columns,
            y=correlation.index,
            zmin=-1,
            zmax=1,
            colorscale=[[0, "#B7503B"], [0.5, "#F4F6F8"], [1, "#168C8C"]],
            text=np.round(correlation.to_numpy(), 2),
            texttemplate="%{text:.2f}",
            hovertemplate="%{y} / %{x}<br>相关系数 %{z:.3f}<extra></extra>",
            colorbar=dict(title="相关系数"),
        )
    )
    heatmap.update_layout(yaxis_autorange="reversed")
    st.plotly_chart(polish_figure(heatmap, height=500), width="stretch")
    st.caption(
        "相关性始终展示五只 ETF，并基于共同交易窗口的日收益率计算；"
        "VaR 以正数表示潜在损失幅度。"
    )


with portfolio_tab:
    st.subheader("组合收益路径")
    try:
        portfolio_series = portfolio_cumulative_returns(
            data.portfolio_timeseries,
            start_date=selected_start,
            end_date=selected_end,
        )
    except DashboardDataError as exc:
        st.info(f"{exc}，请扩大日期范围。")
        portfolio_series = None

    if portfolio_series is not None:
        portfolio_series["portfolio_label"] = portfolio_series["portfolio"].map(
            PORTFOLIO_LABELS
        )
        portfolio_line = px.line(
            portfolio_series,
            x="date",
            y="cumulative_return",
            color="portfolio_label",
            line_dash="portfolio_label",
            color_discrete_map=PORTFOLIO_COLORS,
            line_dash_map={"等权组合": "solid", "最低波动组合": "dash"},
            labels={
                "date": "日期",
                "cumulative_return": "累计收益",
                "portfolio_label": "组合",
            },
        )
        portfolio_line.update_traces(
            line=dict(width=2.4),
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>%{y:.2%}<extra>%{fullData.name}</extra>"
            ),
        )
        st.plotly_chart(
            polish_figure(portfolio_line, percent_y=True), width="stretch"
        )

        st.subheader("组合回撤")
        drawdowns = portfolio_drawdowns(portfolio_series)
        drawdowns["portfolio_label"] = drawdowns["portfolio"].map(PORTFOLIO_LABELS)
        drawdown_line = px.line(
            drawdowns,
            x="date",
            y="drawdown",
            color="portfolio_label",
            line_dash="portfolio_label",
            color_discrete_map=PORTFOLIO_COLORS,
            line_dash_map={"等权组合": "solid", "最低波动组合": "dash"},
            labels={
                "date": "日期",
                "drawdown": "回撤",
                "portfolio_label": "组合",
            },
        )
        drawdown_line.update_traces(
            line=dict(width=2.2),
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>%{y:.2%}<extra>%{fullData.name}</extra>"
            ),
        )
        st.plotly_chart(
            polish_figure(drawdown_line, percent_y=True, height=380), width="stretch"
        )

    weight_column, metric_column = st.columns([1.1, 1])
    weights = data.portfolio_weights.copy()
    weights["asset_name"] = weights["symbol"].map(data.asset_names)
    weights["portfolio_label"] = weights["portfolio"].map(PORTFOLIO_LABELS)
    weight_figure = px.bar(
        weights,
        x="asset_name",
        y="weight",
        color="portfolio_label",
        barmode="group",
        color_discrete_map=PORTFOLIO_COLORS,
        labels={"asset_name": "ETF", "weight": "组合权重", "portfolio_label": "组合"},
    )
    weight_figure.update_traces(hovertemplate="%{x}<br>权重 %{y:.2%}<extra>%{fullData.name}</extra>")
    weight_column.markdown("#### 组合权重")
    weight_column.plotly_chart(polish_figure(weight_figure, percent_y=True, height=390), width="stretch")

    portfolio_metrics = data.portfolio_metrics.copy()
    portfolio_metrics["portfolio_label"] = portfolio_metrics["portfolio"].map(PORTFOLIO_LABELS)
    metric_column.markdown("#### 组合指标")
    metric_column.caption("指标采用完整验证区间计算。")
    metric_column.dataframe(
        metric_table(portfolio_metrics, include_asset=False),
        width="stretch",
        hide_index=True,
    )
    st.caption("当前验证样本中两个组合结果一致；看板保留真实计算结果，不人为制造差异。")


with quality_tab:
    st.subheader("数据处理与覆盖范围")
    quality = data.data_quality.iloc[0]
    quality_columns = st.columns(3)
    quality_columns[0].metric("输入记录", f"{int(quality['input_rows']):,}")
    quality_columns[1].metric("输出记录", f"{int(quality['output_rows']):,}")
    quality_columns[2].metric("共同窗口记录", f"{int(quality['shared_window_rows']):,}")
    removal_columns = st.columns(3)
    removal_columns[0].metric("去除重复值", f"{int(quality['duplicates_removed']):,}")
    removal_columns[1].metric("去除无效价格", f"{int(quality['invalid_prices_removed']):,}")
    removal_columns[2].metric("去除缺失收盘价", f"{int(quality['missing_close_removed']):,}")

    coverage = pd.DataFrame(
        {
            "范围": ["价格数据覆盖", "五资产共同收益窗口"],
            "开始日期": [quality["start_date"].date(), quality["shared_window_start"].date()],
            "结束日期": [quality["end_date"].date(), quality["shared_window_end"].date()],
            "记录数": [int(quality["output_rows"]), int(quality["shared_window_rows"])],
        }
    )
    st.dataframe(coverage, width="stretch", hide_index=True)
    st.markdown(
        """
        <div class="method-strip">
        数据管道优先从东方财富获取前复权日线，单资产失败时才尝试 Yahoo Finance；五只资产必须全部可用后才发布分析包。
        原始响应保存在仓库中以便追溯，本页面仅读取 <code>output_verified</code>，不调用实时接口，也不构成投资建议。
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(
    '<div class="footer-note">方法：252 个交易日年化，2% 无风险利率，95% 一日历史 VaR，长仓且权重和为 1 的最低波动组合。</div>',
    unsafe_allow_html=True,
)
