# Power BI — Phase 1 data contract

Import the CSVs from output_phase1/powerbi. Treat date columns as Date and numeric
returns, risks and weights as decimal fractions. Build Assets and Portfolios
dimensions from unique identifiers; relate asset or portfolio fact tables to them.
The source_metadata and data-quality event tables can have multiple rows per
asset, so they are facts, not unique asset dimensions.

## Sample labels

Asset metrics and correlation describe the full selected contiguous common window.
Portfolio metrics and time series describe evaluation only. Display
methodology.json training/evaluation dates beside portfolio panels. Do not apply
a date slicer to a static metric table and imply its values were recalculated.
The saved weights come only from training; filtering charts must not refit them.

## Measures and formats

Annual return, volatility, drawdown, VaR, CVaR and downside volatility are
percentages. Sharpe, Sortino and Calmar are unitless. Maximum drawdown is negative.
VaR/CVaR have a signed-loss convention and can be negative; do not clamp, take
absolute values or use a chart type that silently hides negative observations.
Undefined ratios remain blank with the status supplied in methodology.json.

portfolio_timeseries.cumulative_return already includes the first evaluation
return. Use the prior training close as the wealth origin. Do not divide again
by the first cumulative value: doing so removes the first evaluation return.
Rolling volatility's first 19 values are intentionally blank.

## Quality and provenance panels

Show asset_data_quality (first/last date, observed/expected counts, missing,
duplicates, coverage, anomalies and selected dates). Use data_quality_events
for stage-specific drilldown; never add all affected_rows across different
stages as a count of unique deletions. source_metadata supplies price basis and
retrieval/request information. Legacy retrieval_timestamp is explicitly unknown,
with replay_timestamp separate.

## Refresh

Generate a new non-existing output directory. Inspect methodology status and
sample dates, objective diagnostics and quality reports before updating the
Power BI source. For quality_only output, show quality evidence instead of
constructing a placeholder portfolio. Preserve output_verified and its archive.
See [Methodology](METHODOLOGY.md) for exact formulas and policies.
