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
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--risk-free-rate", type=float, default=0.02,
                        help="Annual effective assumed rate, decimal units")
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error("--start must not be later than --end")

    if not 0 < args.train_fraction < 1:
        parser.error("--train-fraction must lie strictly between 0 and 1")
    if not -1 < args.risk_free_rate < float("inf"):
        parser.error("--risk-free-rate must be finite and greater than -1")
    market_session = session if session is not None else create_market_session()
    try:
        result = run_pipeline(
            args.start, args.end, args.output_dir, session=market_session,
            train_fraction=args.train_fraction, risk_free_rate=args.risk_free_rate
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
    if metadata.get("status") == "quality_only":
        print(f"Quality report saved: {result.output_dir}. {metadata.get('reason', '')}")
        return 2
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
