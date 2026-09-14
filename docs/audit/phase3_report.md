# Phase 3 — ETF Benchmark / Tracking Analysis 完成报告

本阶段仅增加ETF基准/跟踪研究；未建设指数、Regime或重构Streamlit。原Phase1/Phase2和output_verified结果保留。结果中的comparable表示在已披露数据假设下口径可比，不是完整独立数据审计认证。

## 1. 官方基准及数据口径

| ETF | 官方代码 | 官方基准 | 类型 | 来源 |
| --- | --- | --- | --- | --- |
| 510300.SS | 000300 | 沪深300指数 | equity_price | [官方依据](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-10-28/510300_20251028_LQSR.pdf) |
| 510500.SS | 000905 | 中证500指数 | equity_price | [官方依据](https://www.nffund.com/main/files/2025/08/29/742110361683.pdf) |
| 159915.SZ | 399006 | 创业板指数 | equity_price | [官方依据](https://static.efunds.com.cn/html/fund/159915_fundinfo.htm) |
| 518880.SS | Au99.99 | 上海黄金交易所Au99.99收盘价 | gold_spot_close | [官方依据](https://www.sge.com.cn/cpfw/hjetf) |
| 511010.SS | 000140 | 上证5年期国债指数（净价） | bond_clean_price | [官方依据](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-03-25/511010_20250325_77AR.pdf) |

股票ETF另比较H00300、H00905、399606全收益参考序列，绝不替换上述官方价格基准。511010的000140为净价，H00140全价不是官方替代。原五只ETF快照各726行、无重复/缺失，2023-08-14—2026-08-12，属于前复权市场收盘价而非NAV，原抓取时刻仍为unknown_legacy_snapshot。

新数据：510300/510500使用Eastmoney单位净值及七笔已对照发行人公告的分红构造理论除息日再投资NAV总收益；事件完整性仍依赖供应商。159915使用易方达官方累计收益字段。黄金、国债使用明确标识的供应商NAV序列，因估值时点/收益口径未完全验证，不发布严格跟踪指标。CSI五条历史来自官方接口；创业板PR/TR历史来自Eastmoney，身份由国证官方编制方案核验；黄金收盘来自上金所原始日行情。

## 2. 各ETF跟踪结果

下表股票ETF均相对**全收益研究参考**；TD是累计收益之差（百分点），TE为年化标准差，IR用日超额均值/标准差再年化。所有收益值在文件内存为小数。

| ETF | 比较基准 | 状态 | 匹配收益数 | 累计TD（百分点） | 年化TD（百分点） | 年化TE | IR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 510300.SS | H00300 | comparable | 725 | -1.8090 | -0.5284 | 0.1556% | -3.1825 |
| 510500.SS | H00905 | comparable | 725 | -0.8629 | -0.2385 | 0.3127% | -0.6825 |
| 159915.SZ | 399606 | comparable | 725 | -0.8040 | -0.1962 | 0.1973% | -0.8831 |
| 518880.SS | Au99.99 | basis_mismatch | 603 | unavailable | unavailable | unavailable | unavailable |
| 511010.SS | 000140 | basis_mismatch | 725 | unavailable | unavailable | unavailable | unavailable |

三只股票ETF样本均为2023-08-14—2026-08-12，首笔收益2023-08-15，726个水平/725对收益。负TD表示ETF低于全收益参考，可能受到费用、现金头寸、复制差异、估值与数据处理影响；本阶段未做归因，不能把差额全部归于管理费。低TE不保证TD为零；稳定落后也可能产生较大负IR。

黄金选择2024-02-19—2026-08-12，首笔收益2024-02-20，604个水平/603对收益。2024-02-09黄金开市、股票休市，最长完整并集日历区间策略排除该日及此前122个共同水平日期；另记录两条周末NAV。该样本选择保守，不能与其余ETF直接按统计值排名。

## 3. 累计收益、波动率与回撤

黄金和国债以下仅为有明确口径限制的描述性比较，不称严格跟踪结果。

| ETF / 比较基准 | ETF累计收益 | 基准累计收益 | ETF年化波动 | 基准年化波动 | ETF最大回撤 | 基准最大回撤 |
| --- | --- | --- | --- | --- | --- | --- |
| 510300.SS / H00300 | 29.6494% | 31.4585% | 18.0998% | 18.1744% | -17.4161% | -17.2317% |
| 510500.SS / H00905 | 41.6508% | 42.5137% | 24.8429% | 24.8527% | -24.7469% | -24.5444% |
| 159915.SZ / 399606 | 71.5619% | 72.3659% | 33.6935% | 33.7284% | -29.1746% | -28.9992% |
| 518880.SS / Au99.99 | 96.2081% | 99.3139% | 22.4631% | 22.5045% | -30.2915% | -30.1057% |
| 511010.SS / 000140 | 9.3961% | 3.7120% | 1.2737% | 1.2431% | -1.5545% | -1.8469% |

## 4. 官方基准比较：不混称跟踪误差

| ETF | 官方基准 | 累计收益差（百分点） | TE / IR |
| --- | --- | --- | --- |
| 510300.SS | 000300 | 7.9941 | unavailable：basis_mismatch |
| 510500.SS | 000905 | 5.6768 | unavailable：basis_mismatch |
| 159915.SZ | 399006 | 5.1602 | unavailable：basis_mismatch |
| 518880.SS | Au99.99 | -3.1058 | unavailable：basis_mismatch |
| 511010.SS | 000140 | 5.6841 | unavailable：basis_mismatch |

股票基金总收益含分红再投资、官方价格指数不含相同收益，正差不能直接解释为alpha。国债NAV与净价基准存在票息/应计收益差异。黄金文件仅明确SGE市价估值，未证明特定收盘时点；未用ETF15:00市价代替SGE15:30基准价。

## 5. 测试与完整性

Baseline：193 collected / 193 passed / 0 failed / 0 skipped。最终：235 tests / 235 passed / 0 failed / 0 skipped / 0 errors，28.17秒；新增42项。结果来自实际pytest/JUnit运行，非源码函数计数。

覆盖：日期对齐、共同日历差异、缺口不跨越、无未来滚动数据、TD/TE/IR确定性算例、零TE、滚动窗口、缺失/重复、不可得基准、口径不匹配屏蔽、官方指数身份、现金分红、黄金收盘列/日期、来源哈希及真实八组比较的CSV/SQLite输出。

首次完整运行234通过、1项既有Phase1测试因Windows临时目录重命名拒绝访问失败；新目录单项重跑及完整重跑通过，未修改Phase1生产代码。更早日志包装器缺少终端接口导致测试启动失败，亦保留记录。间歇文件访问原因未确定，不把失败日志隐藏。

日志：[最终测试](phase3/final_tests.log)、[JUnit](phase3/final_tests.xml)、[首轮完整测试](phase3/full_attempt1.log)。旧结果校验：output_verified 9文件、Phase1 20文件、Phase2 30文件均无哈希差异；见[完整性记录](phase3/prior_outputs_integrity.json)。

## 6. 文件与复现

新增：config/benchmarks.json；src/portfolio_analysis/benchmark_config.py、benchmark_data.py、tracking.py、tracking_reporting.py；scripts/run_phase3.py；tests/test_benchmark_config.py、test_benchmark_data.py、test_tracking.py、test_tracking_reporting.py、test_phase3_workflow.py。更新README.md及docs/METHODOLOGY.md。原始响应/来源清单保存在docs/audit/phase3，最终结果单独保存output_phase3。

运行：python scripts/run_phase3.py --output-dir 新目录。默认output_phase3存在时拒绝覆盖。完整测试：python -m pytest。基准配置、请求时间、日期范围、口径、来源URL、原始文件哈希及分红事件均写入metadata.json；每日曲线及滚动指标在daily.csv，排除日志在exclusions.csv，所有表另存SQLite。

## 7. 剩余局限

1. 510300/510500已列现金分红逐项核对，但未独立证明事件列表完整或期间无未列拆分；2026年7月510500金额证据为发行人PDF券商镜像。再投资为除息日理论约定，不模拟真实到账执行。
2. 159915官方收益字段仍受披露精度和历史修订影响；创业板指数历史为供应商数据，未与第二官方历史源全面交叉验证。
3. 黄金估值时点、完整独立SGE日历未确认；国债净价与NAV总收益天然不同，因此严格TE/IR不可得。
4. 基准身份有官方证据，但未逐日核对整个历史期所有合同/方法版本变更。
5. 252日年化和63日滚动是统一研究约定；只有约三年历史，不能推断长期稳定跟踪能力。
6. 这是回顾性研究；未建立数据修订时间库、税收/费用归因、溢折价与申赎机制分析，不代表可交易超额收益。
7. 黄金因连续区间策略样本不同；完整数据中的排除数量已披露，不能跨ETF不加区分排名。

本阶段结束，不进入Index Construction、Regime或后续功能。
