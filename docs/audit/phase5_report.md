# Phase 5 Robustness / Sub-period Analysis

## Scope and reproducibility
Only Phase 2/4 robustness is added. No optimal parameter is selected. Run:
`python scripts/run_phase5.py --output-dir output_phase5_new`.
Rules: config/robustness_rules.json. Source is the archived Phase 1 five-ETF snapshot, independently checked against raw hashes by the Phase 4 source loader.
Results include daily paths, holdings, targets, eligibility, trades, sensitivity, paired frequency/risk comparisons, window ranges, stability summary, SQLite and SHA256 manifest.

## Evaluation design
- all_windows: execution anchor 2025-09-30; returns 2025-10-09–2026-08-12 (207). Subperiods: 2025Q4 60; 2026Q1 56; remainder 91.
- extended_126_252: anchor 2024-09-30; returns 2024-10-08–2026-08-12 (451). Subperiods: 2024Q4 61; 2025 243; 2026YTD 147.
- 168 scenarios: 140 successful and 28 explicitly skipped for insufficient 504-day history in the extended group. 672 sensitivity rows: 560 scored and 112 skipped. Skipped rows have zero evaluated observations and missing metrics, with expected counts separately retained.
- Identical evaluation dates within each group/period. Never rank across groups with different dates. Full and subperiod rows overlap and are not independent experiments.
- Signals use only returns dated strictly before execution; first return follows execution. Shared anchors remove false window sensitivity caused by different starting dates.
- Phase 2 monthly/quarterly means 21/63 sessions; Phase 4 means actual calendar month/quarter. These schedule definitions differ and results must retain engine labels.
- Continuous holdings drift between trades. Subperiod performance is rebased, holdings are never restarted. Initial cash allocation and its cost occur once; maintenance turnover is separate.
- Phase 2 costs 0/5/10/20 bps use existing self-financing accounting. Phase 4 indices are gross; no fictitious net result is reported.
- Effective annual RF 2% converts to daily (1.02)^(1/252)-1; Sharpe uses daily excess mean/sample std times sqrt(252). Return is geometric, volatility sample std times sqrt(252), drawdown starts at wealth 1. Annualized short-period estimates are descriptive.

## Findings
Minimum Variance is heavily concentrated in government bonds in every available full path: minimum across start/pretrade/end and targets is 95.57% in the primary group and 93.73% in the extended group. The predeclared 70% threshold is descriptive, not a portfolio constraint. No concentration cap is imposed.

Inverse Volatility has lower gross volatility than Equal Weight in all 24 primary and 16 extended cases per engine (windows × schedules × periods). These cases overlap; this is not an independent statistical success rate. Low risk is consistent in the available snapshot, but its magnitude is window-sensitive and largely reflects bond allocation.

Monthly rebalancing does not improve returns consistently across subperiods, for any strategy/cost group. Full-period gains can hide subperiod reversals. Added turnover is reported separately; no best schedule is selected.

Equal Weight has exactly zero window sensitivity within a fixed engine/schedule/group, as expected because its signal does not use volatility. For primary monthly Phase 2, Minimum Variance Sharpe ranges 0.985–1.057 and drawdown -0.300% to -0.358%; Inverse Volatility Sharpe ranges 0.648–0.787 and drawdown -1.754% to -2.944%. Low volatility magnitude, concentration and Sharpe are not invariant to window length.

## Primary monthly, gross, full-period sensitivity
Values are decimals (0.01 = 1%); HHI is sum of squared weights. These rows are an illustration, not parameter selection.

| engine | strategy | window | gross_annualized_return | gross_annualized_volatility | gross_sharpe_ratio | gross_maximum_drawdown | bond_daily_mean | average_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| phase2 | equal_weight | 126 | 0.096685 | 0.187152 | 0.480792 | -0.1181 | 0.199725 | 0.200186 |
| phase2 | equal_weight | 252 | 0.096685 | 0.187152 | 0.480792 | -0.1181 | 0.199725 | 0.200186 |
| phase2 | equal_weight | 504 | 0.096685 | 0.187152 | 0.480792 | -0.1181 | 0.199725 | 0.200186 |
| phase2 | minimum_variance | 126 | 0.028196 | 0.008158 | 0.98522 | -0.003005 | 0.986568 | 0.973504 |
| phase2 | minimum_variance | 252 | 0.028734 | 0.00865 | 0.990063 | -0.003132 | 0.974147 | 0.949673 |
| phase2 | minimum_variance | 504 | 0.030557 | 0.009788 | 1.056939 | -0.003579 | 0.967917 | 0.937483 |
| phase2 | inverse_volatility | 126 | 0.045625 | 0.034308 | 0.740381 | -0.017538 | 0.849508 | 0.729023 |
| phase2 | inverse_volatility | 252 | 0.054535 | 0.043524 | 0.786819 | -0.024551 | 0.806771 | 0.663029 |
| phase2 | inverse_volatility | 504 | 0.051657 | 0.048998 | 0.648282 | -0.029444 | 0.786769 | 0.631617 |
| phase4 | equal_weight | 126 | 0.106482 | 0.184728 | 0.532805 | -0.112369 | 0.199706 | 0.2003 |
| phase4 | equal_weight | 252 | 0.106482 | 0.184728 | 0.532805 | -0.112369 | 0.199706 | 0.2003 |
| phase4 | equal_weight | 504 | 0.106482 | 0.184728 | 0.532805 | -0.112369 | 0.199706 | 0.2003 |
| phase4 | inverse_volatility | 126 | 0.049975 | 0.033951 | 0.870118 | -0.016251 | 0.846881 | 0.724824 |
| phase4 | inverse_volatility | 252 | 0.057709 | 0.042473 | 0.875985 | -0.023891 | 0.806319 | 0.662533 |
| phase4 | inverse_volatility | 504 | 0.055592 | 0.04802 | 0.738286 | -0.028285 | 0.786236 | 0.630891 |

## Stable versus sample-dependent
Supported in available cases: Minimum Variance bond concentration; Inverse Volatility lower risk than EW; EW invariance to lookback after aligning inception.
Not stable: monthly return advantage, numerical Sharpe/drawdown/concentration levels, and the magnitude of risk reduction.
No claim extends these observations beyond the current universe and archived sample.

## Remaining limitations
Only 725 historical daily returns are available; the all-window common sample has only 207 observations, less than one 252-day year. Annualizing 56–91 day slices can amplify noise. The longer comparison cannot validate 504-day estimation.
Prices are forward-adjusted traded market prices, not certified reinvested NAV total returns. Original retrieval versions are unavailable; source metadata preserves legacy uncertainty. Prior-close availability assumes next-session 09:00 and is not publication-time proof.
The fixed five-ETF universe carries hindsight/survivorship limitations. No delisting history, point-in-time universe reconstruction, market impact, tax, spread or capacity model is added. Phase 2 fees are simplified proportional costs; index net performance is not modelled.
No significance testing, causal claim, parameter winner, prediction or independent regime classification is produced.

## Verification
Baseline: 267 collected/passed, 0 failed/skipped (24.83s).
First full run: 286 collected, 285 passed, 1 failed: Windows denied temporary output-directory rename in an existing Phase 1 test. The failure log is preserved.
Final rerun: 287 collected, 287 passed, 0 failed, 0 skipped, 0 errors (28.57s). Results are recorded in phase5/final_tests_retry.log and XML. Original output_verified and Phase 1–4 manifests are checked in phase5/preservation_check.json.

## Files changed in Phase 5

New: config/robustness_rules.json; src/portfolio_analysis/robustness.py; src/portfolio_analysis/robustness_reporting.py; scripts/run_phase5.py; tests/test_robustness.py; docs/audit/phase5_report.md; docs/audit/phase5/*; output_phase5/*.
Modified: src/portfolio_analysis/backtest.py and index_construction.py (optional common inception only; defaults retained); README.md; docs/METHODOLOGY.md.
