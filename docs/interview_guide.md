# Interview Guide

## Project Story

### Motivation

I wanted one reproducible project that connected data acquisition, defensive
cleaning, quantitative analysis, SQL persistence, optimization, and business
intelligence. The five ETFs represent distinct equity, gold, and government-bond
exposures, which makes diversification behavior visible without claiming that the
selection is a complete investment universe.

### Data Flow

1. The CLI accepts a date range and output directory.
2. Each configured symbol is fetched independently from Eastmoney's daily kline
   endpoint, with Yahoo's chart endpoint retained as a per-asset fallback.
3. The response is normalized to date, symbol, asset name, asset class, and close.
4. Cleaning removes missing, nonnumeric, nonpositive, and duplicate price rows and
   records the counts.
5. Daily returns and five risk metrics are calculated for each asset.
6. The wide return matrix is synchronized with `dropna` across all five assets.
7. Equal-weight and long-only minimum-volatility portfolios are evaluated on that
   shared window, including 20-trading-day annualized rolling volatility.
8. SQLite, UTF-8 Power BI CSVs, and run-derived resume facts are built in a unique
   sibling staging directory and published to a new immutable version directory
   with a single same-volume, no-replace directory rename on Windows. Existing or
   concurrently created destinations are preserved; result metadata records which
   provider served each asset. `output_verified` is the canonical verified example.

The fake-session integration test follows the same flow without network access.
The normal integration path returns realistic Eastmoney-shaped payloads for all
five assets, so calculations, storage, and exports are exercised rather than
mocked out. Yahoo-shaped fixture data is used only by the focused provider-fallback
test after one simulated Eastmoney failure.

## Metric Definitions

- **Annualized return:** geometric compound daily return, scaled to 252 trading days.
- **Annualized volatility:** sample standard deviation of daily returns times the
  square root of 252.
- **20-day rolling volatility:** sample standard deviation of each portfolio's
  latest 20 daily returns times the square root of 252. The initial 19 values are
  missing because a complete rolling window is not yet available.
- **Sharpe ratio:** annualized excess return over a fixed 2% risk-free rate divided
  by annualized volatility.
- **Maximum drawdown:** largest peak-to-trough percentage decline in cumulative wealth.
- **Historical VaR:** positive 95% one-day loss estimate based on the empirical fifth
  percentile of returns.
- **Correlation:** Pearson correlation between synchronized asset returns.

## Optimization Choice

I used SciPy SLSQP to minimize portfolio variance because the objective and
constraints are explicit: each weight is between zero and one and all weights sum
to one. The long-only constraint keeps the result interpretable for a portfolio
dashboard. Equal weight is always calculated first and serves as a transparent
benchmark. If the optimizer raises an error, reports failure, or returns invalid
weights, I retain only equal-weight output and record the optimizer failure in the
pipeline result. I never fabricate optimized weights.

All portfolio work uses the same complete five-asset return rows. This sacrifices
some observations but makes covariance estimation and portfolio comparison
internally consistent. If that complete shared window is empty, the pipeline
rejects the run before optimization or publication and leaves any previous output
package unchanged.

## Data-Quality Issue Encountered

The source histories can have nonmatching dates or a missing adjusted close. A
missing price affects both that date's return and the following return because the
pipeline deliberately does not fill across the gap. Asset metrics can still use
the valid observations for each asset, but optimization cannot accept a matrix
with missing values. I resolved this by applying complete-case synchronization
across all five return columns and exposing the resulting shared row count and date
range in `data_quality.csv`. This makes the data loss visible instead of silently
forward-filling prices.

## Likely Interview Questions

### 1. Why not compare raw ETF prices directly?

Raw prices have unrelated units and starting levels. Returns normalize price
changes, so risk, correlation, and portfolio calculations are comparable. The
dashboard keeps price history for inspection but uses returns for analytics.

### 2. Why use geometric annualized return instead of mean return times 252?

Geometric annualization respects compounding over the observed period. Arithmetic
scaling is useful for expected-return models, but it does not describe realized
compound performance as directly.

### 3. How did you prevent look-ahead bias?

The project is descriptive rather than a backtested trading strategy. It uses only
prices inside the requested period and makes no future-return claim. A production
strategy evaluation would additionally separate model estimation, validation, and
out-of-sample test windows.

### 4. What happens when one download or optimization fails?

Every asset fetch is attempted and failures are collected by symbol. Because the
final analysis requires all five assets, any missing asset produces a nonzero CLI
exit and no new package. Optimization failure is different: equal weight remains
valid, so it is exported while minimum-volatility weights are omitted and the exact
failure is retained in result metadata.

### 5. What would you improve next?

I would add a versioned data snapshot, configurable risk-free rates, transaction
costs and rebalancing, out-of-sample optimization evaluation, and a published Power
BI file. I would also compare covariance shrinkage with the sample covariance,
because minimum-variance weights can be sensitive to estimation error.

## Truthful Resume Use

Use only values from the selected versioned package's `resume_facts.json` after
checking them against its `analysis.sqlite`. For the delivered resume evidence,
the canonical file is `output_verified/resume_facts.json`. Do not quote counts
from test fixtures. A defensible
statement can describe building a five-asset pipeline and name the risk methods;
the exact row count and observed dates must come from the live run evidence.
