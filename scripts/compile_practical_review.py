#!/usr/bin/env python3
"""Compile the reviewed practical-variant table into build artifacts.

Reads ``build/practical_variant_review.tsv`` (reviewer edits preserved) and
writes:

- ``build/practical_spellings_from_review.txt`` : accepted words
- ``build/practical_variants_from_review.tsv``  : variant -> canonical links
- ``build/practical_corrections_from_review.tsv``: typed -> correction pairs

Decision values (case-insensitive):
- ``s`` / ``standard``           : accept as a standard word
- ``v`` / ``variant``            : accept and link to ``likely_standard``
- a Khmer word                   : the variant is a typo of that word
- blank                          : leave out for now

This script never rewrites the review table.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_REVIEW = BUILD_DIR / "practical_variant_review.tsv"


def normalize_decision(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if not text:
        return "skip", ""
    lowered = text.lower()
    if lowered in {"s", "standard"}:
        return "standard", ""
    if lowered in {"v", "variant"}:
        return "variant", ""
    if lowered in {"looks the same to me", "same", "ok", "yes"}:
        return "standard", ""
    return "correction", text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=BUILD_DIR)
    args = parser.parse_args()

    if not args.review.is_file():
        parser.error(f"review table not found: {args.review}")

    accepted: set[str] = set()
    variants: dict[str, str] = {}
    corrections: dict[str, str] = {}
    counts = {"standard": 0, "variant": 0, "correction": 0, "skip": 0}

    with args.review.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            word = (row.get("variant") or "").strip()
            if not word:
                continue
            kind, payload = normalize_decision(row.get("decision", ""))
            counts[kind] += 1
            if kind == "standard":
                accepted.add(word)
            elif kind == "variant":
                accepted.add(word)
                standard = (row.get("likely_standard") or "").strip()
                if standard:
                    variants[word] = standard
            elif kind == "correction":
                if payload and payload != word:
                    corrections[word] = payload

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "practical_spellings_from_review.txt").write_text(
        "\n".join(sorted(accepted)) + ("\n" if accepted else ""), encoding="utf-8"
    )
    with (args.output_dir / "practical_variants_from_review.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["variant", "canonical"])
        for word in sorted(variants):
            writer.writerow([word, variants[word]])
    with (args.output_dir / "practical_corrections_from_review.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["typed", "correction"])
        for word in sorted(corrections):
            writer.writerow([word, corrections[word]])

    print(
        f"decisions: {counts}\n"
        f"  accepted words: {len(accepted)}\n"
        f"  variant links: {len(variants)}\n"
        f"  corrections: {len(corrections)}\n"
        f"wrote artifacts under {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
