# Phase 1 Methodology

This document supersedes the earlier calculation descriptions in the repository.
The work is a research-method correction, not a rolling backtest framework.

## Data and provenance

The five China-listed ETFs are 510300.SS, 510500.SS, 159915.SZ, 518880.SS and
511010.SS. Eastmoney daily forward-adjusted prices (fqt=1) are the primary input;
Yahoo adjusted close is a per-asset fallback. The normalized price column is
named close, but source, price_basis, retrieval_timestamp, requested_start and
requested_end accompany it and are persisted in prices and source_metadata.
Unadjusted, unknown, or conflicting within-asset price bases cannot produce
performance; the pipeline publishes a quality-only package instead.

For newly fetched data, retrieval_timestamp is UTC retrieval time. Timestamped,
SHA256-addressed JSON snapshots are saved and copied into each result package's
raw directory. Fixed-name raw caches are only convenience copies; immutable
snapshots are the provenance evidence. The source_metadata snapshot_path records
the original input location; the packaged raw file has the same basename.

Legacy raw JSON did not record the original retrieval time. The Phase 1 replay
therefore says unknown_legacy_snapshot, not today's date. replay_timestamp is the
time of replay. requested_start/end for this replay describe the analysis request
(2023-08-12 to 2026-08-12); the original network request cannot be independently
reconstructed from the legacy JSON alone. Provider-adjusted prices have not been
independently reconciled to dividend reinvestment or official total-return NAV.
They must not be described as independently verified total returns.

## Data quality and sample selection

The default XSHG calendar comes from exchange-calendars >=4.13.2. Its holiday
schedule is also used for the current Shenzhen-listed ETF. No generic business-day
approximation is used. Unsupported calendar years fail explicitly. A cross-market
extension requires explicit per-symbol session calendars.

Each ticker report includes first/last observed dates, observation count,
expected observations, missing count, raw excess-duplicate count, coverage,
anomaly count, cleaning removals and selected sample dates. Coverage is observed
valid sessions / expected sessions in the inclusive requested interval. It is
not inferred from dates seen in other assets. The first observation is not
assumed to be the ETF listing date; missing history before it is unverified.

The data_quality_events ledger distinguishes:

| Reason | Evidence and treatment |
|---|---|
| non_trading_day | Calendar closure; expected absence, not missing market data |
| different_asset_calendar | Another asset trades on this date; breaks common daily path |
| source_missing_unverified | Expected session without a valid price; cause unknown |
| suspension | Explicit caller-supplied status evidence; absent price remains missing |
| no_trade | Explicit status for an absent price, or zero reported volume for an existing close |
| invalid/missing price, invalid date/symbol | Remove with original row ID and reason |
| duplicate | Remove redundant identical observation |
| conflicting_duplicate | Quarantine every conflicting price for that symbol/date |
| large_absolute_return | Flag and retain; never automatically delete/winsorize |

A reported close with zero volume is retained as a marked valuation observation,
not treated as proof of executable liquidity. Without external status evidence,
a missing quote is not called a suspension. Current provider payloads do not
supply a complete suspension history.

Analysis chooses the longest fully observed contiguous price block on the
union of expected session dates, requiring all assets to be open and observed
at every selected session; ties choose the earlier block. This avoids bridging
unequal intervals after calendar intersection. Holidays shared by all assets
do not break a trading-day path. The selection rule uses availability, not
returns, but remains retrospective sample selection and can change the period.

All price rows excluded from analysis are logged for every affected asset.
The initial selected price has no preceding price: exactly one structural
return per asset is recorded as undefined. Internal missing returns are neither
filled nor silently removed. Metrics reject incomplete return vectors. With
fewer than 31 contiguous prices or incompatible basis, quality reports and raw
evidence are published without performance. CLI exit code 2 means quality-only;
it is distinct from a fetch/processing error (exit code 1).

Ledger affected_rows are stage-specific events. Do not sum calendar absences,
cleaning removals and analysis exclusions as though they were unique deleted
input records. Use cleaning stage counts to reconcile input/output and sample
selection stage counts for analytical exclusions.

Anomaly screening uses absolute daily return >=10% for non-bond assets and
>=2% for the government-bond ETF. These are configurable-in-code screening
choices, not exchange price limits or proof of bad data. No flags are removed
automatically. First 19 rolling-volatility entries are structurally unavailable.

## Return and annualization conventions

Input returns are decimal daily **simple** returns r, with r > -1. The positive
price domain excludes total-loss/delisting cases; these require a separate model.
Simple return is P[t]/P[t-1]-1. Log return is log(P[t]/P[t-1]); log returns are
not directly linearly weighted as simple portfolio returns.

Use A=252 trading periods per year throughout:
- Geometric annual return = exp(A * mean(log(1+r))) - 1.
- Annual volatility = sample std(r, ddof=1) * sqrt(A).
- 20-session rolling volatility uses the same sample-standard-deviation rule.

This is trading-period annualization, not elapsed-calendar-year CAGR. It is not
a claim that each historical China calendar year contains exactly 252 sessions.
Square-root scaling is a convention relying on assumptions about serial
dependence; it is not a volatility forecast.

## Risk-free rate and Sharpe

The default 0.02 is an assumed annual **effective** risk-free rate, not a fetched
historical CNY series. It can be changed with --risk-free-rate. Convert using:

    daily_rf = (1 + annual_rf) ** (1/252) - 1
    excess[t] = simple_return[t] - daily_rf
    Sharpe = mean(excess) / sample_std(excess, ddof=1) * sqrt(252)

At 2%, daily_rf is approximately 0.000078584942. Do not use geometric annual
return minus the annual rate as the Sharpe numerator. A bond ETF is not used as
the risk-free asset. Zero computed standard deviation gives an undefined ratio
(NaN with a status record), not a fabricated zero or infinity.

## Drawdown, downside and ratios

Wealth starts at W[0]=1, before the first included return.
W[t]=product(1+r[1:t]); drawdown is W[t]/max(W[0:t])-1.
Maximum drawdown is the most negative drawdown, so [-10%,-10%] yields -19%.

The annual minimum acceptable return for downside measures defaults to zero,
independently of Sharpe's risk-free rate. Convert it to an effective daily target.
Downside volatility is sqrt(252 * mean(min(r-daily_target,0)^2)), using **all**
observations in the mean. Sortino uses annual arithmetic excess over that target
divided by annual downside volatility. Calmar is geometric annual return divided
by absolute same-period maximum drawdown. These are full-input-period ratios,
not a special trailing-36-month Calmar convention.

Undefined zero-downside/zero-drawdown ratios are NaN with explicit status in
methodology.json. Finite input and computed-overflow checks prevent invalid
numbers being silently interpreted as meaningful statistics.

## VaR and CVaR / Expected Shortfall

Confidence c=0.95; alpha=1-c=0.05. Let Q_r(p) be the sorted-sample return quantile
with linear interpolation at knots i/(n-1), the NumPy method='linear' convention.

    return_quantile = Q_r(alpha)
    loss_convention_VaR = -Q_r(alpha)
    linear_interpolated_ES = -(1/alpha) * integral[0,alpha] Q_r(p) dp

The ES integral is evaluated exactly over the piecewise-linear quantile curve.
It is not the discrete arithmetic mean of all observations at/below a threshold;
the two estimators can differ for small samples or quantile-boundary ties.
Both estimates use a one-trading-period horizon, and neither is annualized.

Negative VaR is allowed: if even the lower return quantile is positive, the
loss-convention quantile is negative. It does not mean negative volatility or
guaranteed profit. No clamping to zero is performed. ES follows the same signed
loss convention. Confidence must lie strictly between zero and one.

The asset metric aggregator defaults to at least 30 returns. Split samples must
each have at least two observations for covariance/sample standard deviation;
short evaluation reports are mathematically defined but can be extremely
unstable. A metadata flag identifies evaluation samples with fewer than ten
nominal 5% tail observations. Passing that screen is not statistical validation.

## Minimum variance and temporal boundary

The solver estimates sample covariance from **training returns only**. It uses
annual covariance (252 * daily covariance), normalized by the largest diagonal
element for numerical scale. The objective is convex quadratic variance under
w>=0 and sum(w)=1. SLSQP uses analytic gradient 2*Sigma*w, ftol=1e-12 and
maxiter=1000. Post-solve checks include finite bounded weights, full investment,
objective no worse than equal weight or every single-asset feasible portfolio,
and a simplex first-order optimality gap. optimizer.success alone is insufficient.
Diagnostics and feasible-baseline variances are saved.

One chronological split is used: floor(0.7*n) training returns followed by the
remaining evaluation returns. The first evaluation return is after the last
training close. Both portfolios use identical evaluation dates; altering
evaluation returns does not change training weights. No walk-forward or rolling
optimization framework is implemented.

Fixed weights are restored daily when computing r_portfolio=sum(w*r_asset).
This is a frictionless constant-weight calculation, not buy-and-hold with
drifting weights. Execution at the boundary, turnover, fees, tax, spread,
liquidity and tracking effects are not modeled.

Asset statistics and correlation are descriptive full-selected-window outputs.
Portfolio statistics are evaluation-only. UI labels distinguish these samples.
The portfolio curve includes the first selected day's return; its initial wealth
belongs to the preceding close. Asset price-normalization charts start from the
first selected close, a different display convention explicitly labeled in UI.

## Evidence, comparison and limitations

output_verified is unchanged legacy evidence and must not be used as corrected
research. Its ZIP archive and SHA256 manifest are in docs/audit.
output_phase1 holds corrected results. Offline reproduction reads its preserved raw files, verifies their SHA256 hashes and exact agreement with legacy price records, and does not use mutable live-download caches. before_vs_after.csv contains three rows:
legacy full sample, corrected full-sample **diagnostic only**, and train/evaluation.
same_evaluation_control.csv separately compares old equal weights and trained
minimum variance under identical evaluation dates and corrected formulas.

Do not attribute all before/after differences to the solver: weights, Sharpe
definition and evaluation dates changed. MDD/VaR differences are primarily path
and sample changes; correcting an initial-wealth bug need not change every
historical sample's maximum drawdown.

The history was already inspected before this split. The evaluation is temporally
separated, not a pristine never-seen validation set. Universe selection,
retrospective longest-block selection, covariance estimation error, concentration
in government bonds, price-adjustment uncertainty, fixed risk-free assumptions,
a short tail sample and excluded trading costs remain material limitations.

SQL monthly returns are last-observed-close to last-observed-close in consecutive
calendar months. Entire missing months produce NULL, not mislabeled multi-month
returns. Partial months or missing true month-end prices still require consulting
the quality report; these queries do not certify official month-end total returns.

Sources: [Sharpe's definition](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm),
[SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html),
[SSE closure notices](https://www.sse.com.cn/disclosure/dealinstruc/closed/list/).


## Phase 2: rolling execution, turnover and costs

Phase 2 is separate from the unchanged Phase 1 single-split pipeline and dashboard.
Run three strategies (Equal Weight, Minimum Variance, Inverse Volatility) for both
21- and 63-session intervals, with each of 0/5/10/20 bps proportional fees: 24 scenarios.

### Information and execution boundary
At close t, form the target using exactly the preceding 252 daily returns,
through t-1. The existing holdings first earn the close-to-close return dated t;
the target is executed at close t and first earns the return dated t+1.
This conservative extra execution session avoids assuming an order can use the
same closing price at which it executes. The first 252 return observations and
the initial execution session contribute no strategy market return.
The preserved input yields initial execution 2024-08-28, first return 2024-08-29,
and 472 common return dates ending 2026-08-12. This is a simulated close fill,
not evidence that an actual order would fill exactly at that price.

Rolling windows have fixed length, not expanding history. 21 and 63 are trading
session intervals anchored at first execution, not calendar month/quarter ends.
Equal Weight only resets at scheduled executions. Inverse Volatility normalizes
the reciprocal sample standard deviations (ddof=1); zero/nonfinite volatility
fails explicitly. Minimum Variance reuses the Phase 1 gradient, scaling,
feasibility, feasible-baseline and optimality checks. No concentration cap is added.
No strategy substitutions or dropped evaluation dates are permitted on failure.

### Holdings and self-financing trade accounting
For start-of-day risky weights w and simple asset returns r, gross return is
g=sum(w*r). Before any close execution, drifted weights are w*(1+r)/(1+g).
Without execution these are the next day's starting weights.

Let V be pretrade net wealth, p its risky weights, a the desired post-fee target,
and k the per-side fee in decimal units (bps/10000). Solve
q = k * sum(abs((1-q)*a-p)).
Then posttrade holdings equal V*(1-q)*a, signed trades equal
V*((1-q)*a-p), cost equals V*q, and net wealth equals V*(1-q).
Initial p is all zero (cash weight one), so q=k/(1+k). This respects the budget;
it does not finance fees with additional contributions or implicit borrowing.
Once invested, buys minus sells equal negative fees. Cost changes wealth, while
relative target and subsequent drifted weights stay common across cost scenarios.

Nominal turnover is half the L1 distance between pretrade and target weights,
including cash. Initial turnover is 1. Actual traded notional/wealth is reported
separately and includes the adjustment needed to pay fees. Fees apply to BOTH
actual purchases and sales. Annualized turnover excludes initial entry:
sum(subsequent nominal turnover)*252/number of evaluation returns.

The actual initial execution and cost appear on their true date in trades.
For a shared return index, the entry fee is allocated to the first reported net
return, so product(1+net_return) equals wealth from pre-entry capital 1.
That first observation combines one entry fee and one market return; it is
explicitly labelled initial_transaction_cost. Daily turnover and transaction_cost
also allocate entry to that first row; is_rebalance only denotes an execution
on that row's own date. Use the trades ledger for exact execution timing.
Subsequent close costs affect that day's net return. There is no terminal
liquidation and no final-day rebalance with no subsequent holding period.

Gross/Net metric calculations use the Phase 1 definitions, 252-day convention,
annual effective rf 2%, zero Sortino target and signed 95% VaR/CVaR. Undefined
ratios retain NaN plus explicit metric_status. Gross and net paths match at 0 bps.
Sum of fees (units of initial capital) differs from terminal wealth drag because
fees change subsequent compounding; report both, never subtract summed fees
from CAGR.

### Concentration and comparison
Maximum Weight=max(w); HHI=sum(w^2). Report daily end-of-day actual holdings and
execution targets separately. For five equal weights HHI is 0.2; full concentration
is 1. These diagnose allocation concentration, not covariance-based risk contribution.

Phase 1 comparison reports both native periods and identical overlapping dates.
The latter retains Phase 2 pre-existing holdings and original schedule; no
re-estimation/re-entry occurs at the comparison boundary. Conditional subperiod
returns do not re-charge costs already paid before that boundary. Phase 1 has
implicit daily fixed-weight rebalancing and no recorded costs; its gross series
is not an executable net benchmark.

Limitations: the universe and historical sample were already inspected; rolling
execution avoids mechanical future-return leakage, not researcher selection
bias or provider revision bias. Preserved forward-adjusted snapshots are not
point-in-time data vintages and are not verified total-return series. Flat fee
scenarios omit minimum commissions, spreads varying by asset/time, market impact,
taxes, lot sizes, volume constraints and failed close fills. No terminal sale
cost is assumed. The roughly two-year evaluation and finite tail sample do not
establish performance across all regimes. Risk-free rate and annualization are
assumptions. Minimum Variance concentration and covariance estimation error remain
visible. Phase 2 stops here: no Benchmark, Index, Regime or Streamlit rebuild.

## Phase 3 — ETF benchmark / tracking analysis

### 官方基准与研究参考分开
基准身份由基金公司、交易所或指数公司文件确认，持久化于
`config/benchmarks.json`，每次运行完整复制进 `metadata.json`。
510300: 000300；510500: 000905；159915: 399006；518880: SGE Au99.99收盘价；
511010: 000140净价指数。H00140是全价版本，不能替换000140。
H00300、H00905、399606是额外全收益研究参考，不是重新定义基金官方基准。

### ETF收益口径
Phase1保留的五只ETF都是Eastmoney前复权市场收盘价，并非NAV；原始抓取时刻
无法追溯，仍标记unknown_legacy_snapshot。本阶段不把这一快照视作NAV跟踪数据。
新增510300/510500使用供应商单位净值和已核对现金分红，以
`(NAV_t + cash_t) / NAV_(t-1) - 1` 构造理论除息日再投资总收益；
这不等于实际到账日再投资。已列七笔现金分红已与发行人公告对照，其中510500
2026年7月金额的发行人文件来自券商镜像。供应商事件列表的完整性、期间不存在
未列分红/拆分仍是明确假设，未取得独立完整性证明。
159915优先使用易方达官方EnumSourceTypeAccIncomeRatio，财富水平为1+该字段，
而不是直接使用累计净值；all/1y快照重叠74条完全相同，去重数量记录在metadata。
黄金和国债仍保留供应商NAV构造过程，但收益口径/估值时点未完全验证。

### 共同日期与缺失
调用者必须提供明确日历。校验日期唯一、递增、规范化、无时区；有效水平必须为正、
有限。先把两个水平序列映射到日历并集，再选择最长连续完整共同区间，长度相同选
最早区间。仅在此区间内计算相邻水平收益；不先丢失缺口再计算跨日收益，不前填、
后填或未来填充。记录全部排除日期、原因、受影响资产、总匹配水平数、
实际选中水平数、匹配收益数和第一条结构性未定义收益。
股票日历使用exchange_calendars的XSHG；本样本深市与之日期一致。
黄金使用已观察SGE日期并入XSHG作为保守参照，未声称独立认证SGE完整休市日历。
2024-02-09仅黄金开市，故黄金选择2024-02-19起的最长区间。
NAV有2023-12-31、2024-06-30两条非交易日估值记录，明确排除。
回顾性“最长完整区间”选择会影响样本，不能当成实时可实施的数据选择规则。

### 指标定义
所有收益为日简单收益、小数单位。日Excess Return = ETF收益 - Benchmark收益。
累计曲线起点为0（初始财富1）。Tracking Difference (TD) =
ETF累计收益 - Benchmark累计收益，以百分点解释；年化TD是两个几何年化收益之差，
并非把日超额收益复利累乘。Annualized TE = std(日超额收益, ddof=1)*sqrt(252)。
IR = mean(日超额收益)/std(日超额收益, ddof=1)*sqrt(252)，不减无风险利率；
零TE时IR为NaN且记录undefined_zero_tracking_error。
滚动TE/相关系数默认63个完整尾随观测，窗口前62条为NaN；常数窗口相关系数未定义。
ETF/Benchmark各自波动率采用ddof=1、sqrt(252)，最大回撤包含初始财富1。
matched_observation_count表示实际用于计算的收益对数，区别于价格/NAV数量。

### 可比性与结果发布
仅当元数据确认NAV总收益、相同已知币种与估值时点，并有对应全收益（或已验证
相同黄金合约）依据，才发布TD/TE/IR。未知合约、未知时点或未验证收益口径均不通过。
基金总收益与官方价格指数/债券净价指数可做明确标注的描述性比较，但严格TD、
TE、IR及滚动TE为空；每日差值、累计差、波动率、回撤、滚动相关仍保留。
不可比不是零跟踪误差；基准不可得则status=unavailable、原因明确且不制造收益。
对510300/510500的可比结论依赖上述供应商事件完整性假设，不等于独立审计证明。
债券净值含票息、应计收益和分红影响，净价指数不含相同收益，不能把差值解读为alpha。
黄金估值条款仅明确SGE市价，未确认具体收盘时点，不能称严格跟踪误差。

### 可重现性
`python scripts/run_phase3.py --output-dir output_phase3` 从归档原始响应离线运行，
逐一校验请求清单中的SHA256。每条来源保留source、price_basis、retrieval timestamp、
requested start/end、精确URL、原始路径及哈希。NAV端点返回全历史时明确注明分析截取
范围与实际请求URL的区别。CSV、SQLite、元数据和校验清单写入全新目录，
存在同名目录即拒绝覆盖。Phase1/Phase2/原始output_verified不变。

## Phase 4 — Fixed ETF Index Construction

### Universe → Eligibility → Weighting → Rebalance → Index Calculation
规则配置保存在 `config/index_rules.json`，每次输出复制配置与SHA256。
Universe为固定的五只ETF，不按历史收益筛选；eligible_from是研究配置生效边界，
不是上市日期，也不证明当时已选定该资产池。存在事后选池和幸存者偏差。
本阶段统一使用Eastmoney前复权市场价格，不混入Phase3的NAV；命名为ETF复权价格
口径研究指数，不宣称标准全收益指数。无可靠历史市值/份额及发布时间，
Market Cap Weighted明确跳过；ETF AUM不是底层股票市值权重。

### 数据与时间边界
来源原始响应与保存价格逐项对照，并核对source、price_basis、retrieval timestamp、
requested start/end及raw SHA256。仅使用完整请求日历，不读取Phase1事后选中的
shared_window边界。缺失价格保留为NaN，导致的当日及下一日未定义收益均记录；
不前填、后填，不把缺口两端连成一天收益。没有日历行时补的是NaN行而不是价格。
原始legacy抓取时间仍为unknown_legacy_snapshot。
默认available_at为下一交易日09:00（Asia/Shanghai）；这是保守研究假设，
不是已核验的历史发布时间。调用接口也支持提供逐条可得时间，原精度保留到CSV/SQLite。
数据修订、前复权历史重算未有历史版本库，不能声称真正完全point-in-time数据。

每个调仓日t的决策截止14:59；观察日期必须严格小于t，并已在截止时间前可得。
只检查之前恰好252个日历收益行，不向更早处搜索252个非缺失值。
每只ETF分别记录资格、历史区间、缺失数量、不可得数量及原因。
历史缺口使该资产在本期不合格，不使其他未受影响资产自动失败。
已持有资产当日缺失/非法收益时先停止路径，不能在调仓日先移除它以掩盖缺失。
目标新资产当日缺少执行估值也停止。无合格资产时不回退现金或伪造等权。
失败轨迹标为failed，保留用于诊断，但不出具年化收益等绩效结果。

### 权重与调仓
等权为1/N；逆波动率为(1/sigma_i)/sum(1/sigma_j)，sigma使用252日样本标准差
(ddof=1)。共同年化系数不影响逆波动率相对权重。逆波动率不利用相关矩阵，
不是最小方差优化，也不是股票低波因子选股。零波动输入明确失败，不加波动率下限。
不设权重上限，保留可能很高的国债权重。

自然月末/季末最后交易日收盘调仓，不是每21/63日。日历覆盖期末之后，
不能把最后一条样本数据误当月末。四组指数共同在有252个之前收益后的首个季度末
初始化，不因未来更干净的样本选择更晚起点。初始化后按各自频率执行；目标权重
从t+1收益生效。终点无后续收益时不执行无意义调仓，也不模拟期末清仓。

### 点位、换手与集中度
初始点位1000，初始行收益未定义并单独标记。每日收益为期初权重乘资产简单收益之和，
点位为前日点位乘(1+r)。调仓前权重=w_start*(1+r_asset)/(1+r_index)，
非调仓日延续这些漂移权重，绝不隐含每日再平衡。
维护换手率=0.5*sum(abs(target-pretrade))。现金到指数的初始建仓换手为100%，
单列且不计入维护换手。年化维护换手=sum(maintenance_turnover)*252/收益观测数。
交易次数不含初始建仓；平均每次维护换手也不含初始。
HHI=sum(w_i^2)，报告每日收盘权重的平均/最大HHI、最大权重，同时保存调仓目标
和调仓前持仓峰值，避免仅看目标权重掩盖漂移。

累计收益为终值/1000-1；年化收益采用252交易日几何年化，不是日历年CAGR；
波动率为样本标准差*sqrt(252)；Sharpe使用固定假设有效年化RF=2%，转日频
(1.02)^(1/252)-1后，以日超额均值/日超额样本标准差*sqrt(252)计算；
最大回撤包含初始1000点。RF不是历史实际无风险利率曲线。
本阶段指数不额外扣交易成本；不能理解为投资者实际净收益。
基金费用已反映在ETF价格中，不再次扣除。

### 复现与输出
`python scripts/run_phase4.py --output-dir output_phase4` 离线重放；已有目录拒绝覆盖。
输出包含Universe、Eligibility、每期成分/目标、每日漂移持仓、调仓账本、可得时间、
来源缺失事件、指标、monthly-minus-quarterly比较、跳过市值指数原因、SQLite及哈希。
复制原始Phase1证据到input_phase1，可复核价格及来源。Phase1/2/3实现和原输出保持不变。


## Phase 5 robustness

Predeclared 126/252/504-day windows, shared evaluation anchors, continuous subperiod holdings and paired schedule comparisons. No parameter selection. Phase 2 uses 21/63 sessions and modelled costs; Phase 4 uses calendar schedules and gross indices. See [Phase 5 report](audit/phase5_report.md) and config/robustness_rules.json.


## Phase 6 presentation conventions

Research pages read hash-checked archived evidence without rerunning strategies. Each module follows Research Question, Methodology, Evidence, Findings, Limitations. Official price benchmarks remain distinct from total-return research references. Mismatched tracking metrics are unavailable. Robustness selections retain skipped rows and compare dates within one group/period only. Phase 2 21/63 sessions and Phase 4 calendar schedules are labelled separately. Percent display does not change decimal CSV values; missing values are never zero-filled. See RESEARCH_SUMMARY.md.
