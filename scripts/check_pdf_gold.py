from __future__ import annotations

import argparse
import json
import sys

from turtlefw.pdf.gold import check


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-PDF gold set")
    parser.add_argument("--root", default=".")
    parser.add_argument("--fixtures", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check(args.root, args.fixtures)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["results"]:
            print(f"{item['status']:4} {item['fixture']}")
            for error in item.get("errors", []):
                print(f"     {error}")
        print(f"passed={result['passed']} failed={result['failed']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
