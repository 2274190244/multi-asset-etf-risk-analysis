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

## 干净克隆：安装、生成与启动

使用 **Python 3.12** 和 Git。从克隆的仓库根目录执行以下步骤；生成研究结果不需要账号、API Key、SQLite 或已有的 output_phase1–5。

```console
git clone --branch codex/phase1-research-audit https://github.com/2274190244/multi-asset-etf-risk-analysis.git
cd multi-asset-etf-risk-analysis
python -m venv .venv
```

激活虚拟环境，Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```sh
source .venv/bin/activate
```

如果 PowerShell 禁止执行激活脚本，可以直接用 `.\.venv\Scripts\python.exe` 替代下面每条命令中的 `python`，不必修改系统策略。

```console
python -m pip install -r requirements-repro.txt -e .
python scripts/build_research_demo.py
python -m streamlit run streamlit_app.py
```

`requirements-repro.txt` 固定经过验证的数值和应用依赖版本；Python 3.12 是本阶段验证版本。安装需访问 PyPI，受网络和平台影响，慢网可能超过 10 分钟；固定样本重算通常 10–60 秒，首次页面加载约 2–10 秒。实测环境和用时见 [Phase 7 验证报告](docs/audit/phase7_report.md)。

本阶段 Windows / Python 3.12.14 干净克隆实测：独立环境安装 124.3 秒（使用公开 PyPI 下载缓存），完整展示重算 15.3 秒；六个页面通过 AppTest，Streamlit 本地服务健康检查返回 200。此前补齐公开依赖的独立安装约 10 分钟，主要受下载速度影响。

构建命令校验约 0.5 MB 的[标准化历史输入](data/research_demo/README.md)，调用既有 Phase 2–5 引擎，重新生成 13 张页面所需 CSV、方法与哈希清单到 `research_results/`。保留 24 个 Phase 2 情景、4 个 Phase 4 指数及 Phase 5 的完整预设矩阵（140 个可计算路径、28 个历史不足路径），没有挑选最佳参数。该目录被 Git 忽略。Phase 1 在此流程提供共同日期和价格输入验证，完整原始数据质量审计不属于此紧凑包的范围。

侧栏包括研究概览、四条研究主线和数据与方法附录。页面只读结果、不联网重算；252 日为既定默认展示窗口。没有结果时页面显示“研究结果尚未生成”及生成命令；损坏、哈希不符的文件显示校验错误，不被当成缺失数据。

构建拒绝覆盖已有目录。需要再次生成时指定新目录，并让页面读取同一个目录。例如 PowerShell：

```powershell
python scripts/build_research_demo.py --output-dir research_results_v2
$env:ETF_RESEARCH_RESULTS = 'research_results_v2'
python -m streamlit run streamlit_app.py
```

macOS / Linux 使用 `export ETF_RESEARCH_RESULTS=research_results_v2`。建议把目录设为绝对路径或始终从仓库根目录启动。结果读取顺序为显式环境变量 → `research_results/` → 本地旧 Phase 归档（仅前两者未设置/不存在时）；不在不同目录间逐表拼接。归档目录不是 GitHub 干净克隆的依赖。

## 数据获取方式与复现边界

默认流程离线使用 **2023-08-14 至 2026-08-12** 的真实历史标准化输入，来源、口径、请求区间、已知采集时间和原始哈希随输入持久化。市场数据为东方财富前复权价格；Tracking 另含基金 NAV/分红、官方价格基准与全收益研究参考。逐序列说明见 [provenance.json](data/research_demo/provenance.json) 和 [Benchmark 配置](config/benchmarks.json)。

选择固定输入的原因是外部历史接口有连接失败、访问限制及历史修订风险。本阶段对原市场端点 HTTP/HTTPS 的探测均连接失败，因此不把实时下载设为页面运行前提。现有公开市场数据获取入口仍可用于尝试建立**新快照**：

```console
python -m portfolio_analysis.cli --start 2023-08-12 --end 2026-08-12 --output-dir output_phase1_live_new
```

此命令获取五只 ETF 行情并输出 Phase 1 质量/分析包，依赖供应商可用性；不是完整 Phase 3 NAV、分红及指数采集器，也不会自动更新页面的固定样本。退出失败或质量检查未通过时须检查原因，不能拿不完整数据替换既有证据。重新下载的历史数值可能修订，不保证复现旧结果。

紧凑输入从本地已核对的原始归档提取；公开包没有原始响应、基金公告 PDF 或完整采集审计链。它可验证标准化数值之后的研究计算，**不能宣称完整独立重建全部原始证据**。旧市场快照的采集时刻无法恢复，明确标为 `unknown_legacy_snapshot`。来源数据权利与使用限制仍归各提供方，见输入说明。

## 完整本地归档重放与历史输出

以下入口保留供持有原始归档的维护者使用，**不是干净克隆的操作步骤**：

```console
python scripts/rebuild_phase1.py --output-dir output_phase1_reproduced
python scripts/run_phase2.py --output-dir output_phase2_reproduced
python scripts/run_phase3.py --output-dir output_phase3_reproduced
python scripts/run_phase4.py --output-dir output_phase4_reproduced
python scripts/run_phase5.py --output-dir output_phase5_reproduced
```

这些脚本依赖本地 `output_phase1`、`docs/audit/phase3` 等完整来源证据；目标目录必须不存在，各参数见 `--help`。Phase 7 没有削弱这些入口的原始哈希或日期检查。

| 目录 | 用途 |
|---|---|
| output_verified | 旧错误结果审计证据，不作为有效研究结果 |
| output_phase1 | 数据质量、指标修复、single split；[报告](docs/audit/phase1_report.md) |
| output_phase2 | Walk-Forward、Gross/Net、权重与交易 |
| output_phase3 | 基准、Tracking口径状态与来源 |
| output_phase4 | 规则指数、资格、成分与调仓 |
| output_phase5 | 参数敏感性、子区间与稳定性 |

Phase 1–5 本地历史输出和 Phase 6 本地页面/README 快照原样保留；这些归档未随当前公共研究包发布。历史报告继续保留在 Git。`output_verified` 中少量旧文件从早期主分支就已跟踪，仅作错误结果审计证据，不能作为本阶段的有效输入。

## 工程结构与验证
独立金融计算模块 → 配置与审计 → CSV/SQLite归档 → research_display只读校验 → Streamlit。
页面和文档核心发现来自同一展示模块；金融函数与UI分离。

```console
python -m pytest tests -ra -p no:cacheprovider --basetemp=.t7tests
```

测试会实际重算公开样本并通过 AppTest 加载六个页面，也检查无结果、哈希损坏和数据口径状态。依赖未公开原始采集证据的旧测试带 `archive` 标记：干净克隆会明确 `skipped` 并报告缺失原因，绝不计为 passed。持有完整归档时增加 `--require-archives` 可强制要求归档存在，并执行原结果与新数值的逐表一致性检查。Windows 使用较短的测试临时路径；不要把 `--basetemp` 指向需要保留的目录。

完整测试计数、干净克隆结果与原归档完整性记录见 [Phase 7 交付报告](docs/audit/phase7_report.md)。之前阶段的验证记录保持在 [Phase 6 报告](docs/audit/phase6_report.md)。

## 剩余局限
约三年历史，504日窗口后的共同评价仅207日，短子区间年化不稳定。固定Universe有选择/存续偏差，历史数据版本与可得时点未完全验证。
NAV分红、供应商指数历史、黄金时点及国债净价可比性有限制；费用未完整覆盖价差、冲击、税费与容量。
无显著性检验或独立前瞻验证，不挑最佳参数，不把重叠情景当作独立成功率。

[Research Summary、简历bullet与面试要点](docs/RESEARCH_SUMMARY.md)
