# Power BI Build Guide

## Load and Model

Use **Get data > Text/CSV** to import every file in the selected versioned
package's `powerbi/` directory. For the resume evidence delivered here, use
`output_verified/powerbi/`. Keep the
file name as the query name. Set all date fields to `Date`, return/risk/weight
fields to `Decimal number`, and count fields to `Whole number`.

Create these one-to-many relationships:

- `prices[symbol]` to `asset_metrics[symbol]` is not needed; both tables are
  asset-level facts. Create an `Assets` dimension from distinct `prices[symbol]`,
  then relate `Assets[symbol]` one-to-many to both tables.
- Relate an optional distinct `Portfolios[portfolio]` dimension one-to-many to
  `portfolio_timeseries`, `portfolio_metrics`, and `portfolio_weights`.
- Keep `correlation_matrix` disconnected because each row contains two asset keys.
- Keep `data_quality` disconnected because it is a single run-level record.

Recommended measures:

```DAX
Latest Close =
CALCULATE(MAX(prices[close]), LASTDATE(prices[date]))

Portfolio Growth Index =
1 + MAX(portfolio_timeseries[cumulative_return])

Weight % =
SUM(portfolio_weights[weight])
```

## Report Page 1: Market Overview

### Adjusted Price History

- Visual: line chart
- CSV: `prices.csv`
- X-axis: `date`
- Y-axis: `close`
- Legend: `asset_name`
- Filters: date range; `asset_class`; `symbol`
- Formatting: continuous date axis; two decimal places; title "Adjusted Price History"

Prices have different scales, so do not use this chart to imply relative return.
Use small multiples by `asset_name` when lines are difficult to compare.

### Asset Risk and Return

- Visual: scatter chart
- CSV: `asset_metrics.csv`
- X-axis: `annualized_volatility`
- Y-axis: `annualized_return`
- Size: `historical_var`
- Details: `asset_name`
- Tooltips: `symbol`, `asset_class`, `sharpe_ratio`, `maximum_drawdown`
- Filters: `asset_class`; `symbol`
- Formatting: axes and tooltips as percentages except `sharpe_ratio`, shown to two decimals

### Asset Metric Table

- Visual: matrix
- CSV: `asset_metrics.csv`
- Rows: `asset_name`, then `symbol`
- Values: `annualized_return`, `annualized_volatility`, `sharpe_ratio`,
  `maximum_drawdown`, `historical_var`
- Filters: `asset_class`
- Formatting: return, volatility, drawdown, and VaR as percentages; Sharpe to two decimals;
  conditional color scale on return and Sharpe; data bars on volatility

## Report Page 2: Portfolio Comparison

### Cumulative Portfolio Performance

- Visual: line chart
- CSV: `portfolio_timeseries.csv`
- X-axis: `date`
- Y-axis: `cumulative_return`
- Legend: `portfolio`
- Filters: `portfolio`; shared date range
- Formatting: percentage axis; continuous dates; zero reference line

Both series use the same complete five-asset return window shown in
`data_quality.csv`. If optimization failed, only `equal_weight` is present; do
not create a placeholder minimum-volatility series.

### Portfolio Risk Comparison

- Visual: clustered bar chart
- CSV: `portfolio_metrics.csv`
- X-axis: `portfolio`
- Y-axis: `annualized_volatility`
- Tooltips: `annualized_return`, `sharpe_ratio`, `maximum_drawdown`, `historical_var`
- Filters: `portfolio`
- Formatting: percentage values; data labels on; sort by volatility ascending

### Portfolio Allocation

- Visual: 100% stacked bar chart
- CSV: `portfolio_weights.csv`
- Y-axis: `portfolio`
- X-axis: `weight`
- Legend: `symbol`
- Tooltips: `symbol`, `weight`
- Filters: `portfolio`; `symbol`
- Formatting: percentage labels; fixed asset colors used consistently across pages

### Daily Portfolio Returns

- Visual: column chart
- CSV: `portfolio_timeseries.csv`
- X-axis: `date`
- Y-axis: `daily_return`
- Small multiples: `portfolio`
- Filters: date range; `portfolio`
- Formatting: percentage axis; positive bars muted green and negative bars muted red

### 20-Day Rolling Volatility

- Visual: line chart
- CSV: `portfolio_timeseries.csv`
- X-axis: `date`
- Y-axis: `rolling_volatility_20d`
- Legend: `portfolio`
- Filters: date range; `portfolio`
- Formatting: percentage axis; continuous dates; title "20-Day Annualized Rolling Volatility"

The field is the sample standard deviation of the latest 20 portfolio daily
returns multiplied by `sqrt(252)`. The first 19 observations for each portfolio
are blank by design and should remain blank rather than being replaced with zero.

## Report Page 3: Diversification and Quality

### Correlation Heatmap

- Visual: matrix with conditional background formatting
- CSV: `correlation_matrix.csv`
- Rows: `symbol`
- Columns: `correlated_symbol`
- Values: `correlation`
- Filters: none by default
- Formatting: two decimals; diverging scale from -1 through 0 to 1; hide subtotals

### Data Quality Cards

- Visual: six cards
- CSV: `data_quality.csv`
- Fields: `input_rows`, `output_rows`, `duplicates_removed`,
  `invalid_prices_removed`, `missing_close_removed`, `shared_window_rows`
- Filters: none
- Formatting: whole numbers; use descriptive titles; flag any nonzero removal count

### Coverage and Shared Window

- Visual: table
- CSV: `data_quality.csv`
- Fields: `start_date`, `end_date`, `shared_window_start`, `shared_window_end`
- Filters: none
- Formatting: `yyyy-mm-dd`; title "Observed and Shared Portfolio Windows"

The observed dates cover all cleaned prices. The shared dates are narrower when
any asset lacks a return and are the only dates used for portfolio optimization,
portfolio metrics, portfolio time series, and correlation.

## Refresh Checklist

1. Run the pipeline into a new versioned directory such as `output_20260812`; never
   reuse an existing destination. `output_verified` is the canonical verified example.
   Publication uses a single same-volume, no-replace directory rename on Windows,
   so a destination created concurrently is preserved and the refresh fails clearly.
2. Confirm the terminal summary is successful, then open that version's
   `resume_facts.json` and check that `asset_count` is five.
3. Point the Power BI queries to the selected version and refresh all queries.
4. Confirm each portfolio allocation totals 100%.
5. Confirm the correlation diagonal is 1.00.
6. Confirm page filters do not compare portfolio series outside the shared window.
