# Phase 7 — GitHub / Streamlit 可复现性

验证日期：2026-09-13。研究逻辑基线为 `0966ecd863ce10244dc4659af2512202c5f5d86f`；实现和干净克隆测试候选为 `5bd8b683c1c366bf21039fc13485ec7e04ae1371`。本报告与 README 的实测用时补充在后续文档提交中，不改变实现、数据或参数。

## 结论及发布状态

本地候选通过完整归档测试、独立安装、干净 Git 克隆、离线结果生成、六页 AppTest 和 Streamlit HTTP 检查。本阶段的复现阻断已解决。

此次使用 `git clone --no-local --branch codex/phase1-research-audit` 克隆**当前本地候选分支**，不是把未推送内容描述为已在 GitHub 发布。没有复制原工作区的忽略目录、结果或 Python site-packages；允许 pip 使用公开发行包的下载缓存。没有执行 push 或 merge。

最近一次远端检查中，`origin/main` 为 `37767652d78f8198ebbde38864aa0bb97356958c`，是候选提交祖先，当前提交关系不存在 merge conflict。GitHub feature 分支仍为 Phase 1–6 的 `0966ecd`；该 head/base 的 open PR 查询返回空列表。因此：**工程验收满足本阶段要求；GitHub 合并流程仍需发布 Phase 7 提交、建立/更新 PR 并按远端检查结果确认**。没有声称已有可直接合并的 PR。

## 依赖审计

原页面需要 13 张未跟踪表及对应 Phase 哈希清单：

| 页面/模块 | 直接数据依赖 |
|---|---|
| 研究概览 | Phase 5 stability_summary |
| ETF Tracking | Phase 3 summary、daily |
| Walk-Forward | Phase 2 summary、daily、weights、trades |
| Index Construction | Phase 4 summary、daily、components、rebalances |
| Robustness | Phase 5 sensitivity、frequency_comparison、stability_summary |
| 数据与方法附录 | 已跟踪的 benchmarks 配置、Methodology/研究说明、Phase 1–5 报告 |

Phase 1 提供上游共同日期与价格。旧完整重放脚本还依赖 `output_phase1` 原始行情、`docs/audit/phase3` NAV/指数/黄金原始响应、分红核对证据等。仅把运行命令列在 README 中，不能消除这些未发布依赖。

## 方案与改动范围

约 0.52 MB 的 `data/research_demo` 保存标准化市场价格、Tracking 序列、来源与哈希。五只 ETF 的市场样本为 2023-08-14 至 2026-08-12，726 个共同价格日。Tracking 保留 13 条各自日期的序列及 8 组比較口径，不未来填充。

`scripts/prepare_research_inputs.py` 是需要完整归档的维护者提取入口。它复用原 Phase 1 来源验证及原 Phase 3 解析、分红核对、口径判断，核对提取后的 Tracking 汇总；不要求普通克隆运行此脚本。

`scripts/build_research_demo.py` 调用新的薄编排模块 `research_bundle.py`，再调用既有 Phase 2–5 引擎。生成 13 张必要展示 CSV 及 JSON 到新的 `research_results/`，合计约 10.8 MB，受 Git 忽略；没有 SQLite、原始响应或中间全量路径归档。完整预声明参数保留：Phase 2 为 24 个情景，Phase 4 为 4 个指数，Phase 5 为 140 个可计算路径、28 个历史不足路径。后者是研究矩阵的状态，不是 pytest 的 skip 计数。

结果目录已存在时拒绝覆盖；生成失败不发布部分结果。记录输入清单、配置、引擎源码哈希及数值依赖版本。结果文件逐表校验哈希。输入用 `.gitattributes` 保留原始行尾字节，避免 Windows / Unix 换行转换破坏哈希。

展示层区分缺失与损坏：缺失提供生成命令和方法说明，损坏保留明确校验错误。`ETF_RESEARCH_RESULTS` 可指定一个完整结果目录；不在不同运行之间逐表拼接。页面未新增研究模型或重新优化按钮。

源码范围为结果编排、输入提取、展示读取、缺失提示、依赖/忽略配置、README 和测试。金融指标、策略、指数、稳健性引擎、研究参数、Methodology 与 Research Summary 均未修改。

## 数据与方法边界

标准化输入是实际历史数值，不是合成示例或手工填好的绩效结论。来源包括行情供应商、基金披露与指数/黄金供应商，逐序列 URL、身份、口径、请求区间、已知采集时间与原始哈希在 provenance 中保留。旧市场快照的采集时间仍为 `unknown_legacy_snapshot`，没有用打包时间冒充。

原始 HTTP 响应、PDF 和完整采集证据未发布，因此本方案证明标准化输入之后的计算复现，不证明从公开网站到每条历史 NAV 的完整独立验证链。候选 NAV 质量记录和最终计算来源分开说明：159915 的 Eastmoney 候选没有用于最终 Tracking，实际使用 E Fund 序列。

三只股票 ETF 相对全收益研究参考仍有条件可分析；相对官方价格指数的口径不一致状态保留。黄金和国债严格跟踪指标仍不可用。没有把可用参考基准替代官方基准。原研究对样本、可得时点、分红、执行费用和集中度的限制全部保留。

公开市场端点的 HTTP 与 HTTPS 探测在本阶段均连接失败；PyPI 安装可用。这不代表所有公共数据源均不可用。README 保留已有公开行情采集入口用于尝试新快照，明确其供应商可用性、数据修订和 Phase 3 采集不完整的限制。

## 测试证据

计数来自 pytest 实际执行结果及 JUnit XML，不使用源码函数数量推算。

| 环境 | Collected | Passed | Failed | Skipped | 用时 |
|---|---:|---:|---:|---:|---:|
| 修改生产代码前 baseline，完整本地归档 | 297 | 297 | 0 | 0 | 29.09 秒 |
| 最终实现，独立 PyPI 安装环境，完整本地归档 | 303 | 303 | 0 | 0 | 53.46 秒 |
| 干净克隆，独立环境，原始归档不存在 | 303 | 282 | 0 | 21 | 25.98 秒 |

失败原因：以上三次完整执行均无失败。

干净克隆的 21 项明确跳过包括：Phase 1 来源/对比重放 3、旧 dashboard 归档读取 12、Phase 3 原始来源重放 1、Phase 4 原始来源重放 2、Phase 1 全量重放 1、全部旧展示表对照 1、Phase 5 旧序列化结果核对 1。它们缺少未分发的原始来源或旧输出，并非本次功能测试失败后被隐藏；全部在本地完整归档环境中通过。

新集成 fixture 每次实际从公开标准化输入重算，并在计算期间禁止 socket 连接，保证没有隐藏下载。展示测试改为使用本次重算结果。新增覆盖输入哈希、完整情景数、共同评价计数、Tracking 门禁、缺失/损坏提示、不覆盖已有目标、13 张表与原结果的一致性。

13 张表与原归档的数值比对容差为 `rtol=1e-8, atol=1e-10`，允许表示与浮点求解的微小差异；不宣称输出文件字节完全一致。独立代码复核亦在内存重算全部 13 张表并通过相同核对。

`--require-archives` 在完整本地环境通过；在干净克隆中明确以退出码 4 拒绝缺失归档，验证了严格模式没有将缺失证据视作成功。`pip check` 无依赖冲突。

## Fresh clone 实测

操作顺序：Git 克隆候选 → 确认 output_phase1–5、原始审计和旧环境不存在 → Python 3.12 创建独立 venv → 按 README 安装 → 未生成状态页面检查 → 一条命令生成 → 六页 AppTest → 本地 HTTP 服务 → 完整测试。

| 检查 | 结果 |
|---|---|
| 操作系统 / Python | Windows / 3.12.14 |
| 独立安装 | 124.3 秒，使用公开 PyPI wheel 下载缓存；未复用旧 site-packages |
| 安装前补齐公开依赖的独立试装 | 约 10 分钟，主要受下载速度影响 |
| 未生成状态 | 正常提示生成命令，附录可访问 |
| `python scripts/build_research_demo.py` | 成功，15.3 秒 |
| 六个页面 AppTest | 全部正常，无 exception / error |
| Streamlit 健康接口与主页 | HTTP 200；约 1.6 秒就绪 |
| 隔离检查 | 解释器来自克隆自己的 venv，项目模块来自克隆 src，用户 site-packages 禁用 |
| 生成结果、测试缓存和验证日志 | 保持在忽略目录，未被 Git 跟踪；克隆工作区 clean |

测试日志与 XML 留在本地审计/临时目录，不上传 GitHub。未部署 Streamlit Cloud，也未声称 Linux / macOS 已实测。

## README 最短运行流程

创建并激活 Python 3.12 虚拟环境后，从仓库根目录运行：

```console
python -m pip install -r requirements-repro.txt -e .
python scripts/build_research_demo.py
python -m streamlit run streamlit_app.py
```

重新生成时使用新的 `--output-dir`，通过 `ETF_RESEARCH_RESULTS` 指向该目录。完整安装、数据刷新、原始归档重放和限制见根 README。

## 完整性与剩余局限

`output_verified`、output_phase1–5 共 141 个原文件重新计算哈希，全部与 Phase 7 修改前一致。历史报告和 Phase 1–6 研究逻辑未改动。本次提交不含数据库、临时环境、生成研究目录、原始 HTTP 响应、凭据或本机绝对路径；对新增文本做了相关模式检查和人工复核。早期 main 已跟踪的少量 output_verified 文件仍保留，不作为有效研究结果。

标准化输入发布不能替代完整原始证据公开；公开下载仍有网络、历史版本与使用条款限制。依赖文件固定数值/应用的直接依赖，未声称所有平台、所有间接依赖和构建工具均已完整锁定。当前验证为本机独立克隆与本地 Streamlit，不代表托管服务部署已验收。Phase 7 完成后停止，没有新增策略、模型或 Regime。
