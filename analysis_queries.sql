-- QUERY: Monthly Returns
WITH month_end_prices AS (
    SELECT
        symbol,
        date,
        close,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, strftime('%Y-%m', date)
            ORDER BY date DESC
        ) AS month_rank
    FROM prices
),
monthly_prices AS (
    SELECT symbol, date, close
    FROM month_end_prices
    WHERE month_rank = 1
)
SELECT
    symbol,
    date AS month_end_date,
    close AS month_end_close,
    close / LAG(close) OVER (PARTITION BY symbol ORDER BY date) - 1.0 AS monthly_return
FROM monthly_prices
ORDER BY symbol, month_end_date;

-- QUERY: Period Performance by Asset
WITH ranked_prices AS (
    SELECT
        symbol,
        date,
        close,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date) AS first_rank,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS last_rank
    FROM prices
),
period_bounds AS (
    SELECT
        symbol,
        MIN(CASE WHEN first_rank = 1 THEN date END) AS period_start,
        MAX(CASE WHEN last_rank = 1 THEN date END) AS period_end,
        MAX(CASE WHEN first_rank = 1 THEN close END) AS starting_close,
        MAX(CASE WHEN last_rank = 1 THEN close END) AS ending_close
    FROM ranked_prices
    GROUP BY symbol
)
SELECT
    symbol,
    period_start,
    period_end,
    starting_close,
    ending_close,
    ending_close / NULLIF(starting_close, 0) - 1.0 AS period_return
FROM period_bounds
ORDER BY symbol;

-- QUERY: Annualized Volatility Ranking
SELECT
    symbol,
    annualized_volatility,
    RANK() OVER (ORDER BY annualized_volatility) AS volatility_rank
FROM asset_metrics
ORDER BY volatility_rank, symbol;

-- QUERY: Missing and Duplicate Date Checks
WITH symbols AS (
    SELECT DISTINCT symbol
    FROM prices
),
observed_dates AS (
    SELECT DISTINCT date
    FROM prices
),
date_counts AS (
    SELECT symbol, date, COUNT(*) AS row_count
    FROM prices
    GROUP BY symbol, date
),
expected_dates AS (
    SELECT symbols.symbol, observed_dates.date
    FROM symbols
    JOIN (
        SELECT symbol, MIN(date) AS start_date, MAX(date) AS end_date
        FROM prices
        GROUP BY symbol
    ) AS coverage
        ON coverage.symbol = symbols.symbol
    JOIN observed_dates
        ON observed_dates.date BETWEEN coverage.start_date AND coverage.end_date
)
SELECT
    expected_dates.symbol,
    expected_dates.date,
    'missing' AS issue,
    1 AS affected_rows
FROM expected_dates
LEFT JOIN date_counts
    ON date_counts.symbol = expected_dates.symbol
    AND date_counts.date = expected_dates.date
WHERE date_counts.row_count IS NULL
UNION ALL
SELECT
    symbol,
    date,
    'duplicate' AS issue,
    row_count - 1 AS affected_rows
FROM date_counts
WHERE row_count > 1
ORDER BY symbol, date, issue;
