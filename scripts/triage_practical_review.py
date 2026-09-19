#!/usr/bin/env python3
"""Triage practical-variant candidates into decided and ambiguous sets.

Rules (reviewer decisions are always preserved):

- a candidate listed as the ``typed`` side of a reviewed typo -> ``correction``
- an edit limited to dependent vowels/signs, where the candidate is a real
  lexical entry (Chuon Nath headword or corpus frequency) -> ``variant``
- everything else (base-consonant or COENG edits, or unverified forms)
  -> ambiguous, written to a separate review file

Outputs:
    build/practical_review_decided.tsv
    build/practical_review_ambiguous.tsv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.normalization import KhmerNormalizer  # noqa: E402
from khmer_segmenter.spelling import weighted_edits  # noqa: E402

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
SPICE_DIR = PROJECT_ROOT / "dataset" / "khmer-dict-spice"
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_REVIEW = BUILD_DIR / "practical_variant_review.tsv"


def _char_kind(char: str) -> str:
    code = ord(char)
    if 0x1780 <= code <= 0x17B3:
        return "base"
    if code == 0x17D2:
        return "coeng"
    if 0x17B6 <= code <= 0x17C5:
        return "vowel"
    if 0x17C6 <= code <= 0x17D1 or code in (0x17D3, 0x17DD):
        return "sign"
    return "other"


def _is_diacritic_only(candidate: str, standard: str) -> bool:
    _, edits = weighted_edits(candidate, standard)
    if not edits:
        return False
    kinds = set()
    for edit in edits:
        if edit.kind == "insert":
            kinds.add(_char_kind(edit.text))
        elif edit.kind == "delete":
            kinds.add(_char_kind(candidate[edit.start]))
        else:
            kinds.add(_char_kind(candidate[edit.start]))
            kinds.add(_char_kind(edit.text))
    return not (kinds & {"base", "coeng", "other"})


def _load_typed_corrections() -> dict[str, str]:
    path = DATA_DIR / "khmer_typo_corrections.tsv"
    corrections: dict[str, str] = {}
    if not path.is_file():
        return corrections
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("status") not in {"approved", "pending"}:
                continue
            typed = (row.get("typed") or "").strip()
            correction = (row.get("correction") or "").strip()
            if typed and correction:
                corrections.setdefault(typed, correction)
    return corrections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=BUILD_DIR)
    args = parser.parse_args()

    if not args.review.is_file():
        parser.error(f"review table not found: {args.review}")

    normalizer = KhmerNormalizer()
    choun: set[str] = set()
    choun_csv = SPICE_DIR / "kh_dictionary.csv"
    if choun_csv.is_file():
        with choun_csv.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                word = normalizer.normalize((row.get("word") or "").strip())
                if word:
                    choun.add(word)
    freq_path = DATA_DIR / "khmer_word_frequencies_chuon.json"
    frequencies = (
        json.loads(freq_path.read_text(encoding="utf-8")) if freq_path.is_file() else {}
    )
    typo_corrections = _load_typed_corrections()

    decided: list[dict] = []
    ambiguous: list[dict] = []
    with args.review.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            variant = (row.get("variant") or "").strip()
            standard = (row.get("likely_standard") or "").strip()
            if not variant:
                continue
            existing = (row.get("decision") or "").strip()
            record = {
                "variant": variant,
                "likely_standard": standard,
                "edit_cost": row.get("edit_cost", ""),
                "chuon_freq": row.get("chuon_freq", ""),
                "decision": existing,
                "confidence": "user",
                "reason": "reviewer decision",
                "source": "reviewed",
            }
            if existing:
                decided.append(record)
                continue
            if variant in typo_corrections:
                correction = typo_corrections[variant]
                legacy = ("ំ" in variant) != ("ំ" in correction) and (
                    "្រ" in variant
                    or "្រ" in correction
                    or "រ" in variant
                    or "រ" in correction
                )
                if legacy:
                    record.update(
                        decision="variant",
                        confidence="high",
                        reason="legacy nikahit vs medial-RA orthography",
                    )
                else:
                    record.update(
                        decision=correction,
                        confidence="high",
                        reason="reviewed typo pair",
                    )
                decided.append(record)
                continue
            if (
                len(variant) == len(standard)
                and _is_diacritic_only(variant, standard)
                and (variant in choun or float(frequencies.get(variant, 0) or 0) > 0)
            ):
                record.update(
                    decision="variant",
                    confidence="medium",
                    reason="diacritic-only edit to a real lexical entry",
                )
                decided.append(record)
                continue
            record.update(
                decision="",
                confidence="low",
                reason="structural edit or unverified form",
            )
            ambiguous.append(record)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "variant",
        "likely_standard",
        "edit_cost",
        "chuon_freq",
        "decision",
        "confidence",
        "reason",
        "source",
    ]
    for name, rows in (
        ("practical_review_decided.tsv", decided),
        ("practical_review_ambiguous.tsv", ambiguous),
    ):
        with (args.output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    print(
        f"decided: {len(decided):,}  ambiguous: {len(ambiguous):,}\n"
        f"wrote {args.output_dir / 'practical_review_decided.tsv'}\n"
        f"wrote {args.output_dir / 'practical_review_ambiguous.tsv'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
