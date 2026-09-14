# Interview Guide — Phase 1

## Project narrative

I built a five-China-ETF research pipeline combining provider data, auditable
cleaning, Python risk metrics, constrained optimization, SQLite and Streamlit.
An audit found that passing tests and a successful optimizer status were not
sufficient evidence of research correctness.

The original solver returned equal weights after one iteration. A single-asset
government-bond portfolio was already a feasible lower-variance solution, so
the equal-weight result could not be the minimum. I corrected objective scale,
provided analytic gradients, set explicit tolerances and checked the result
against feasible portfolios and a first-order optimality condition.

## What changed in evaluation

Previously the entire history estimated covariance and evaluated the resulting
weights. That is an in-sample descriptive calculation; it cannot demonstrate
implementable historical strategy performance. The corrected pipeline uses one
chronological 70/30 training/evaluation split. Weight fitting never accesses
evaluation returns, and a test changes evaluation returns while checking the
training weights remain unchanged. Rolling/walk-forward evaluation is deferred.

I would not claim that selecting data inside the requested date range prevents
look-ahead bias. Future observations relative to each trading date can still
enter covariance estimation. Nor would I call the split an untouched test:
the historical sample has already been inspected.

## Financial definitions

The geometric annual return describes compound growth under a 252-session
convention. Sharpe has a different numerator: mean daily excess return. The annual
effective risk-free assumption is converted to daily before subtracting it.
Maximum drawdown starts with wealth 1, so initial losses are not omitted.
VaR is the negative linear lower-return quantile and can be negative; this is
a signed-loss convention, not a reason to clamp the estimate.

Downside volatility, Sortino, Calmar and integrated-linear-quantile CVaR are
independent tested functions. See [Methodology](METHODOLOGY.md) for inputs, units,
minimum sample sizes and estimator choices.

## Missing observations

A holiday is an expected absence; a missing quote on an expected session is not.
Without status evidence I cannot infer that a fund was suspended. Zero volume
with a reported close is retained and flagged as possible stale valuation,
not treated as executable liquidity. All removals and analytical exclusions
are recorded by asset and date.

The current 726 price dates match the China calendar, yielding 725 common
returns. For incomplete data the pipeline selects the longest contiguous complete
block and discloses excluded records. If a reliable analysis cannot be formed,
it publishes quality evidence without portfolio performance.

## What the results do and do not show

The unconstrained long-only minimum-variance portfolio is heavily concentrated
in the government-bond ETF. This follows from the objective and covariance:
there is no required return or asset-class allocation constraint. I would not
present this as evidence that diversification is unnecessary, or add constraints
after looking at performance merely to make weights visually balanced.

Evaluation results exclude costs, tax, turnover execution and liquidity effects.
Price adjustments have not been independently reconciled to total-return NAV,
and the risk-free rate is an assumption. The sample and asset universe are small.
These are research limitations, not bugs solved by a polished dashboard.

## Resume evidence

Use the corrected output_phase1 package and its methodology.json, database and
resume_facts.json. The old output_verified package remains unchanged and archived.
The before/after report separates solver/formula corrections on the same sample
from changes caused by the evaluation window. Never claim a test count from
counting source functions; use the actual pytest run report.
