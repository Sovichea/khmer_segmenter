#!/usr/bin/env python3
"""Compile the reviewed practical spellings into the shipped runtime layer.

Combines:
- the definition-based review (``build/practical_review_by_definition.tsv``)
- the reviewer's own decisions (``build/practical_variant_review.tsv``)
- the candidate source tags (``build/legacy_variants_review.tsv``)
- the existing reviewed legacy variants

Accepted forms (``standard`` / ``variant``) are written to
``khmer_dictionary_community_spellings.txt`` and are valid only under community
(practical) spelling authority. Each row is tagged with its source so the SBBIC
entries can be verified or dropped later.

Example:
    python scripts/compile_practical_policy.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_WORDS = DATA_DIR / "khmer_dictionary_community_spellings.txt"
DEFAULT_REVIEW = DATA_DIR / "khmer_dictionary_community_spellings_review.tsv"

EXISTING_VARIANTS = (
    ("អោយ", "legacy-variant-review", "Widely used legacy variant of ឱ្យ."),
    ("ឲ្យ", "legacy-variant-review", "Widely used legacy variant of ឱ្យ."),
)


def _normalize(value: str) -> str:
    text = (value or "").strip()
    lowered = text.lower()
    if not text:
        return ""
    if lowered in {"s", "standard", "looks the same to me", "same", "ok", "yes"}:
        return "standard"
    if lowered in {"v", "variant"}:
        return "variant"
    return text  # a correction word


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--definition-review", type=Path, default=BUILD_DIR / "practical_review_by_definition.tsv"
    )
    parser.add_argument(
        "--user-review", type=Path, default=BUILD_DIR / "practical_variant_review.tsv"
    )
    parser.add_argument(
        "--sources", type=Path, default=BUILD_DIR / "legacy_variants_review.tsv"
    )
    parser.add_argument("--words", type=Path, default=DEFAULT_WORDS)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()

    if not args.definition_review.is_file():
        parser.error(f"definition review not found: {args.definition_review}")

    source_of: dict[str, str] = {}
    if args.sources.is_file():
        with args.sources.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                source_of[row["word"]] = row.get("source", "")

    user_decisions: dict[str, str] = {}
    if args.user_review.is_file():
        with args.user_review.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                decision = _normalize(row.get("decision", ""))
                if decision:
                    user_decisions[row["variant"]] = decision

    accepted: dict[str, tuple[str, str, str]] = {}
    with args.definition_review.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            word = row["variant"]
            decision = user_decisions.get(word) or _normalize(row.get("decision", ""))
            source = "reviewed" if word in user_decisions else source_of.get(word, "unknown")
            if decision in {"standard", "variant"}:
                accepted[word] = (source, decision, row.get("reason", ""))
    for word, source, note in EXISTING_VARIANTS:
        accepted.setdefault(word, (source, "variant", note))

    args.words.write_text("\n".join(sorted(accepted)) + "\n", encoding="utf-8")
    with args.review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["word", "status", "source", "decision", "note"])
        for word in sorted(accepted):
            source, decision, note = accepted[word]
            writer.writerow([word, "approved", source, decision, note])

    from collections import Counter

    print(f"wrote {args.words} ({len(accepted):,} practical spellings)")
    print("sources:", dict(Counter(source for source, _, _ in accepted.values())))
    print(f"wrote {args.review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
