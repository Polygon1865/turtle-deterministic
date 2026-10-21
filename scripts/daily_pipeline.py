#!/usr/bin/env python
"""Run the daily Turtle pipeline on the local Windows host."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from turtlefw.daily import (  # noqa: E402
    DailyConfig,
    DailyError,
    DailyPaths,
    load_config,
    run_daily,
)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=_parse_date, default=date.today())
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "daily.toml")
    parser.add_argument("--top", type=int, default=None, help="number of ranked stocks")
    parser.add_argument("--llm-top", type=int, default=None, help="first N get LLM research")
    parser.add_argument("--runs-root", type=Path, default=ROOT / ".runs" / "daily")
    parser.add_argument("--site-root", type=Path, default=ROOT / "site")
    parser.add_argument("--pdf-root", type=Path, default=ROOT / "data" / "pdfs")
    parser.add_argument("--codes", default="", help="comma-separated codes; bypass screen")
    parser.add_argument("--skip-screen", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument("--retry-seconds", type=int, default=None)
    parser.add_argument("--screen-attempts", type=int, default=None)
    parser.add_argument("--stock-timeout", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.config.is_file():
        try:
            config = load_config(args.config)
        except DailyError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            return 2
    else:
        config = DailyConfig()

    overrides: dict[str, object] = {
        "top_n": args.top,
        "llm_top_n": args.llm_top,
        "retry_seconds": args.retry_seconds,
        "screen_attempts": args.screen_attempts,
        "stock_timeout_seconds": args.stock_timeout,
        "allow_stale": args.allow_stale,
        "project_root": str(ROOT),
    }
    config = DailyConfig(
        **{
            key: value
            for key, value in {**config.__dict__, **overrides}.items()
            if value is not None
        }
    )
    codes = tuple(code.strip() for code in args.codes.split(",") if code.strip())
    paths = DailyPaths(
        day=args.date,
        runs_root=args.runs_root,
        site_root=args.site_root,
        pdf_root=args.pdf_root,
    )
    try:
        result = run_daily(
            paths,
            config,
            codes=codes or None,
            skip_screen=args.skip_screen or bool(codes),
            publish=not args.no_publish,
        )
    except DailyError as exc:
        print(f"daily error: {exc}", file=sys.stderr)
        return 2

    print(f"date: {result['date']}")
    print(f"status: {'ok' if result['ok'] else 'failed'}")
    print(f"stocks: {len(result['stocks'])}")
    for row in result["stocks"]:
        print(
            f"  {row['rank']:>2} {row['code']:<12} {row['status']:<7} "
            f"qa={row['qa']:<7} research={row['research']:<9} "
            f"coverage={row['numeric_coverage'] or '—'}"
        )
        if row.get("error"):
            print(f"       error: {row['error'].splitlines()[0]}")
    print(f"site: {result.get('site') or '—'}")
    print(f"status_file: {paths.status_path}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
