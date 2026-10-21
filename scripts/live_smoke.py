from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from turtlefw.config import load_dotenv
from turtlefw.live_smoke import (
    DEFAULT_CODES,
    DEFAULT_MIN_COVERAGE,
    format_report,
    run_suite,
    to_payload,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Turtle live smoke")
    parser.add_argument(
        "--codes",
        default=",".join(DEFAULT_CODES),
        help="comma-separated codes",
    )
    parser.add_argument("--output-dir", default=".runs/nightly")
    parser.add_argument("--no-run", action="store_true", help="validate existing artifacts")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    args = parser.parse_args(argv)

    if not args.no_run and not os.environ.get("TUSHARE_TOKEN", "").strip():
        print("TUSHARE_TOKEN is not set; live smoke skipped")
        return 0

    codes = tuple(code.strip() for code in args.codes.split(",") if code.strip())
    if not codes:
        print("no codes supplied", file=sys.stderr)
        return 2
    root = Path(args.output_dir)
    results = run_suite(
        codes,
        root,
        run=not args.no_run,
        min_coverage=args.min_coverage,
    )
    print(format_report(results))
    if args.json_out:
        target = Path(args.json_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(to_payload(results), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"json: {target.resolve()}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
