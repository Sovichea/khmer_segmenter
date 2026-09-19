#!/usr/bin/env python3
"""Review practical-variant candidates by comparing dictionary definitions.

Rule (as requested):

- if the Chuon Nath definition of the candidate is similar to the RAC
  definition of ``likely_standard``, the candidate is a ``variant``
- otherwise there is no RAC definition for the form, so it is treated as a
  legacy word and accepted as ``standard``
- candidates already listed as reviewed typos are routed to ``correction``
  (except the legacy nikahit/medial-RA family, which is accepted)

Output: ``build/practical_review_by_definition.tsv``.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.normalization import KhmerNormalizer  # noqa: E402

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
RAC_CSV = PROJECT_ROOT / "dataset" / "RAC-Khmer-Dict-2022.csv"
CHUON_CSV = PROJECT_ROOT / "dataset" / "khmer-dict-spice" / "kh_dictionary.csv"
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_REVIEW = BUILD_DIR / "practical_variant_review.tsv"

_ANNOTATION = re.compile(r'<"\d+">')
_KHMER_RUN = re.compile(r"[\u1780-\u17d3\u17dd]+")


def _clean(text: str) -> str:
    text = _ANNOTATION.sub(" ", text or "")
    text = text.replace("/a", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(_KHMER_RUN.findall(text))


def _similar(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    # Short glosses share common words and create false matches, so require a
    # minimum amount of content before scoring.
    if len(a) < 3 or len(b) < 3:
        return 0.0
    return len(a & b) / len(a | b)


def _load_rac(normalizer: KhmerNormalizer) -> dict[str, str]:
    definitions: dict[str, str] = {}
    if not RAC_CSV.is_file():
        return definitions
    with RAC_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            word = normalizer.normalize((row.get("t_main") or "").strip())
            if word and word not in definitions:
                definitions[word] = _clean(row.get("t_exp") or "")
            subword = normalizer.normalize((row.get("t_subword") or "").strip())
            if subword and subword not in definitions:
                definitions[subword] = _clean(row.get("t_exp") or "")
    return definitions


def _load_chuon(normalizer: KhmerNormalizer) -> dict[str, str]:
    definitions: dict[str, str] = {}
    if not CHUON_CSV.is_file():
        return definitions
    with CHUON_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            word = normalizer.normalize((row.get("word") or "").strip())
            if word and word not in definitions:
                definitions[word] = _clean(row.get("definition") or "")
    return definitions


def _load_typos() -> dict[str, str]:
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
    parser.add_argument("--output", type=Path, default=BUILD_DIR / "practical_review_by_definition.tsv")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    if not args.review.is_file():
        parser.error(f"review table not found: {args.review}")

    normalizer = KhmerNormalizer()
    rac = _load_rac(normalizer)
    chuon = _load_chuon(normalizer)
    typos = _load_typos()

    rows = []
    with args.review.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            variant = (row.get("variant") or "").strip()
            standard = (row.get("likely_standard") or "").strip()
            if not variant:
                continue
            chuon_def = chuon.get(variant, "")
            rac_def = rac.get(standard, "")
            score = _similar(chuon_def, rac_def) if chuon_def and rac_def else 0.0
            if variant in typos:
                correction = typos[variant]
                legacy = ("ំ" in variant) != ("ំ" in correction) and (
                    "្រ" in variant or "្រ" in correction or "រ" in variant or "រ" in correction
                )
                decision = "variant" if legacy else correction
                reason = "legacy orthography" if legacy else "reviewed typo pair"
            elif chuon_def:
                # Compare against every RAC definition, not only the skeleton
                # match, so a variant can be linked to its true counterpart.
                best_word = standard
                best_score = 0.0
                for rac_word, candidate_def in rac.items():
                    candidate_score = _similar(chuon_def, candidate_def)
                    if candidate_score > best_score:
                        best_score = candidate_score
                        best_word = rac_word
                if best_score >= args.threshold:
                    decision = "variant"
                    standard = best_word
                    rac_def = rac.get(best_word, "")
                    score = best_score
                    reason = f"definition match {best_score:.2f}"
                else:
                    decision = "standard"
                    reason = "no matching RAC definition; legacy word"
            else:
                decision = "standard"
                reason = "no Chuon definition; legacy word"
            rows.append(
                {
                    "variant": variant,
                    "likely_standard": standard,
                    "similarity": f"{score:.2f}",
                    "decision": decision,
                    "reason": reason,
                    "chuon_definition": chuon_def[:120],
                    "rac_definition": rac_def[:120],
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "variant",
                "likely_standard",
                "similarity",
                "decision",
                "reason",
                "chuon_definition",
                "rac_definition",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter

    print(f"wrote {args.output} ({len(rows):,} rows)")
    print("decisions:", dict(Counter(r["decision"] for r in rows)))
    print("reasons:", dict(Counter(r["reason"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
