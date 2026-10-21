#!/usr/bin/env python
"""Build and publish the static site from a completed daily run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from turtlefw.site import build_and_publish, build_site, collect_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-dir", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, default=ROOT / "site")
    parser.add_argument("--no-publish", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.day_dir.is_dir():
        print(f"day directory not found: {args.day_dir}", file=sys.stderr)
        return 2
    reports = collect_reports(args.day_dir)
    if not reports:
        print(f"no reports found: {args.day_dir}", file=sys.stderr)
        return 2
    if args.no_publish:
        release = build_site(args.day_dir, args.site_root)
        print(f"release: {release}")
        return 0
    result = build_and_publish(args.day_dir, args.site_root)
    print(f"release: {result.release}")
    print(f"current: {args.site_root / 'current'}")
    print(f"reports: {len(result.reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
