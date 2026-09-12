# ETF与多资产研究 | ETF & Multi-Asset Research

面向ETF、指数与量化研究岗位的可复现研究作品。使用五只中国ETF，研究跟踪口径、组合风险、指数规则与稳健性；不提供预测模型或参数择优结论。

## 核心研究结论
- Minimum Variance 在可用路径中持续高度集中于国债ETF：主比较组最低权重 95.57%，较长样本组 93.73%；不是跨市场、跨时期保证。
- Inverse Volatility 在已分析的同日期样本中持续降低相对 Equal Weight 的波动率，但明显集中于国债ETF，低风险不等于资产充分分散。
- 更频繁调仓通常增加换手，但月度调仓没有在所有子区间稳定提高收益；须同时查看费用和配对差异，不能写成所有情景均增加换手。
- Sharpe、回撤和集中度对估计窗口及样本区间敏感；没有选择最佳参数，重叠子区间不属于独立统计实验。
- 三只股票ETF可在已披露假设下相对全收益研究参考分析跟踪表现；官方价格基准未被替换，黄金与国债的严格跟踪指标保持 unavailable。

上述结论属于当前可用样本的描述，没有统计显著优势或实盘盈利能力主张。

## 四条研究主线

| 模块 | Research Question | Methodology | Evidence | Findings | Limitations |
|---|---|---|---|---|---|
| ETF Tracking Research | ETF与基准是否可比，偏离多少？ | 官方身份、共同日期、TD/TE/IR与滚动指标 | [Phase 3](docs/audit/phase3_report.md) | 股票ETF相对全收益参考有条件可分析 | 官方价格基准与全收益参考不同；黄金/国债严格指标不可得 |
| Walk-Forward Portfolio Research | 低风险是否依赖集中？ | 252日估计，21/63日调仓，漂移、费用 | [Phase 2](docs/audit/phase2_report.md) | 低波动伴随国债集中 | 固定样本、数据版本与执行假设 |
| Index Construction Research | 编制规则如何影响风险收益？ | Universe→Eligibility→Weighting→Rebalance→Calculation | [Phase 4](docs/audit/phase4_report.md) | 等权与逆波动有不同风险/集中度 | 固定ETF研究指数；市值加权跳过；Gross |
| Robustness Analysis | 结论依赖参数和样本吗？ | 126/252/504窗口、共同日期、连续持仓子区间 | [Phase 5](docs/audit/phase5_report.md) | 风险方向较一致，指标和收益优势不稳定 | 主组207日、扩展451日；重叠试验不独立 |

每个页面按Research Question → Methodology → Evidence → Findings → Limitations组织。[Research Summary](docs/RESEARCH_SUMMARY.md)包含完整解释与面试要点。

## 数据与方法边界
- ETF：510300.SS、510500.SS、159915.SZ、518880.SS、511010.SS。
- Phase 1/2/4/5为前复权市场价格，不是认证NAV总收益。Phase 3另使用NAV、分红及指数数据。
- 股票官方价格基准000300/000905/399006未被替换；H00300/H00905/399606是全收益研究参考。
- 执行日前估计，执行后收益；非调仓日允许漂移。历史时间隔离不等于前瞻实盘能力。
- Phase 2月/季为21/63交易日；Phase 4为日历月末/季末。不同阶段原始日期不同，不跨期排名。
- 年化252日，2%有效年RF按(1.02)^(1/252)-1转日RF；Sharpe按日超额均值/样本标准差年化。
- 页面比例用%，CSV用小数；TD差异为百分点。缺失不填0，禁止未来填充。详见[Methodology](docs/METHODOLOGY.md)。

## 运行研究页面
从仓库根目录运行：

    python -m pip install -e .
    python -m streamlit run streamlit_app.py

侧栏：研究概览、ETF Tracking Research、Walk-Forward Portfolio Research、Index Construction Research、Robustness Analysis、数据与方法附录。
读取归档结果，不联网、不重新优化。252日为既定展示默认，不代表最佳参数；缺失或哈希不匹配明确提示，不回退到旧结果。

## 离线复现与历史输出

    python scripts/rebuild_phase1.py --output-dir output_phase1_reproduced
    python scripts/run_phase2.py --output-dir output_phase2_reproduced
    python scripts/run_phase3.py --output-dir output_phase3_reproduced
    python scripts/run_phase4.py --output-dir output_phase4_reproduced
    python scripts/run_phase5.py --output-dir output_phase5_reproduced

目标目录必须不存在；各脚本参数见 --help。

| 目录 | 用途 |
|---|---|
| output_verified | 旧错误结果审计证据，不作为有效研究结果 |
| output_phase1 | 数据质量、指标修复、single split；[报告](docs/audit/phase1_report.md) |
| output_phase2 | Walk-Forward、Gross/Net、权重与交易 |
| output_phase3 | 基准、Tracking口径状态与来源 |
| output_phase4 | 规则指数、资格、成分与调仓 |
| output_phase5 | 参数敏感性、子区间与稳定性 |

Phase 1–5输出原样保留。旧页面和README保存在docs/audit/phase6。

## 工程结构与验证
独立金融计算模块 → 配置与审计 → CSV/SQLite归档 → research_display只读校验 → Streamlit。
页面和文档核心发现来自同一展示模块；金融函数与UI分离。

    python -m pytest tests -q -p no:cacheprovider --basetemp=.audit_tmp/new_test_run

测试临时目录使用新名称。Phase 6 baseline：287 collected / 287 passed / 0 failed / 0 skipped。
最终测试与完整性记录见[Phase 6交付报告](docs/audit/phase6_report.md)。

## 剩余局限
约三年历史，504日窗口后的共同评价仅207日，短子区间年化不稳定。固定Universe有选择/存续偏差，历史数据版本与可得时点未完全验证。
NAV分红、供应商指数历史、黄金时点及国债净价可比性有限制；费用未完整覆盖价差、冲击、税费与容量。
无显著性检验或独立前瞻验证，不挑最佳参数，不把重叠情景当作独立成功率。

[Research Summary、简历bullet与面试要点](docs/RESEARCH_SUMMARY.md)

最终完整测试：297 collected / 297 passed / 0 failed / 0 skipped（30.21秒）。本机使用短临时路径.t6通过；此前目录访问/路径失败详见交付报告，未隐藏。
