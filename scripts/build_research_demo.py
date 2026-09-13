"""Recompute the fixed-sample research pages offline after installation."""
import argparse
from pathlib import Path
import sys
from portfolio_analysis.research_bundle import build_bundle, ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research_results")
    parser.add_argument("--inputs", type=Path, default=ROOT / "data/research_demo")
    args = parser.parse_args(argv)
    try:
        meta = build_bundle(args.output_dir, args.inputs)
    except (ValueError, OSError) as exc:
        print(f"Research generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Complete in {meta['elapsed_seconds']:.1f}s: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
