#!/usr/bin/env python3
"""Fill undecided practical-variant rows so the reviewer can verify them.

Blank rows are filled with ``standard`` (accept as a practical spelling) and
tagged ``auto`` in a new ``source`` column. Existing reviewer decisions are
preserved and tagged ``reviewed``. The original review file is not modified.

Example:
    python scripts/autofill_practical_review.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_REVIEW = BUILD_DIR / "practical_variant_review.tsv"
DEFAULT_OUTPUT = BUILD_DIR / "practical_variant_review_filled.tsv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.review.is_file():
        parser.error(f"review table not found: {args.review}")

    with args.review.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    reviewed = 0
    filled = 0
    for row in rows:
        decision = (row.get("decision") or "").strip()
        if decision:
            reviewed += 1
            row["source"] = "reviewed"
        else:
            row["decision"] = "standard"
            row["source"] = "auto"
            filled += 1

    fieldnames = ["variant", "likely_standard", "edit_cost", "chuon_freq", "decision", "source"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"wrote {args.output}\n"
        f"  reviewed: {reviewed:,}\n"
        f"  auto-filled (standard): {filled:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
