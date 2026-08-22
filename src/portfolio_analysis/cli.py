"""Command-line entry point for the portfolio analysis pipeline."""

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Any, Sequence

from portfolio_analysis.config import default_date_range
from portfolio_analysis.data_source import create_market_session
from portfolio_analysis.pipeline import run_pipeline


def main(argv: Sequence[str] | None = None, session: Any = None) -> int:
    """Run the pipeline and return a process-compatible status code."""
    today = date.today()
    default_start, default_end = default_date_range(today)
    parser = argparse.ArgumentParser(description="Build the portfolio analysis package.")
    parser.add_argument("--start", type=date.fromisoformat, default=default_start)
    parser.add_argument("--end", type=date.fromisoformat, default=default_end)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(f"output_{today:%Y%m%d}"),
        help=(
            "new versioned destination that must not already exist "
            "(for example, output_20260812; add a unique suffix for another refresh)"
        ),
    )
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error("--start must not be later than --end")

    market_session = session if session is not None else create_market_session()
    try:
        result = run_pipeline(
            args.start, args.end, args.output_dir, session=market_session
        )
    except Exception as error:
        print(f"Pipeline failed: {error}.", file=sys.stderr)
        return 1

    if result.failures:
        details = ", ".join(
            f"{symbol} ({_concise_failure(message)})"
            for symbol, message in result.failures.items()
        )
        print(f"Pipeline failed: missing {details}.", file=sys.stderr)
        return 1

    metadata = result.metadata
    print(
        f"Complete: {metadata['price_rows']} price rows, "
        f"{metadata['asset_count']} assets, "
        f"{metadata['portfolio_count']} portfolios, "
        f"{metadata['start_date']} to {metadata['end_date']}."
    )
    return 0


def _concise_failure(message: str) -> str:
    """Remove verbose request URLs while retaining actionable failure details."""
    return message.split(" for url:", 1)[0]


if __name__ == "__main__":
    raise SystemExit(main())
