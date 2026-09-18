#!/usr/bin/env python3
"""Generate the runtime composition keep-list.

The runtime composition policy splits accepted words that are cheap
compositions of smaller accepted words. RAC headwords are lexical units even
when they are transparent, so they are protected here. The output is shipped
with the package and read by :class:`KhmerSegmenter` at load time.

Requires the pinned RAC source; run ``python scripts/fetch_sources.py`` first.

Example:
    python scripts/build_composition_keep.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.composition import (
    composition_parts,
    is_composition,
    max_part_length,
)
from khmer_segmenter.normalization import KhmerNormalizer
from khmer_segmenter.rac_rebuild import _clean_reasons

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
DEFAULT_RAC = PROJECT_ROOT / "dataset" / "RAC-Khmer-Dict-2022.csv"
DEFAULT_OUTPUT = DATA_DIR / "khmer_dictionary_composition_keep.txt"

# Curated layers that are authoritative units even when transparent.
PROTECTED_FILES = (
    "khmer_dictionary_supplemental_words.txt",
    "khmer_dictionary_author_curated_words.txt",
    "khmer_dictionary_rac_derived_words.txt",
    "khmer_dictionary_rac_usage_words.txt",
)


def rac_headwords(rac_csv: Path) -> set[str]:
    normalizer = KhmerNormalizer()
    with rac_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headwords = set()
        for row in reader:
            raw = (row.get("t_main") or "").strip()
            if not raw:
                continue
            word = normalizer.normalize(raw)
            if word and not _clean_reasons(word):
                headwords.add(word)
    return headwords


def protected_layers(data_dir: Path, normalizer: KhmerNormalizer) -> set[str]:
    words: set[str] = set()
    names = PROTECTED_FILES + ("khmer_dictionary_words.txt",)
    for name in names:
        path = data_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            word = normalizer.normalize(line.strip())
            if not word:
                continue
            # Repetition forms are lexical units and must remain one token.
            if name.endswith("khmer_dictionary_words.txt") and "ៗ" not in word:
                continue
            words.add(word)
    return words


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rac-csv", type=Path, default=DEFAULT_RAC)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--guard", type=float, default=5.0)
    parser.add_argument("--min-part-clusters", type=int, default=2)
    args = parser.parse_args()

    if not args.rac_csv.is_file():
        parser.error(
            f"RAC CSV not found: {args.rac_csv}\n"
            "Run 'python scripts/fetch_sources.py' to download the pinned source."
        )

    segmenter = KhmerSegmenter(data_dir=args.data_dir, composition=False)
    frequencies = segmenter.word_frequencies
    parts = composition_parts(
        segmenter.spellcheck_words, min_clusters=args.min_part_clusters
    )
    part_length = max_part_length(parts)
    composable = {
        word
        for word in segmenter.words
        if float(frequencies.get(word, 0) or 0) < args.guard
        and is_composition(word, parts, max_part_length=part_length)
    }
    normalizer = KhmerNormalizer()
    protected = rac_headwords(args.rac_csv) | protected_layers(args.data_dir, normalizer)
    keep = sorted(composable & protected)
    args.output.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    print(
        f"wrote {args.output}\n"
        f"  accepted words: {len(segmenter.words):,}\n"
        f"  composition candidates: {len(composable):,}\n"
        f"  protected headwords: {len(keep):,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
