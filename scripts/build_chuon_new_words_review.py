#!/usr/bin/env python3
"""Build a review of Chuon Nath headwords missing from the current model.

These are new words and name entities rather than orthographic variants, so they
are listed with their dictionary definition and a coarse category to make
review practical.

Outputs ``build/chuon_new_words_review.tsv``.
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
from khmer_segmenter.orthography import coeng_da_ta_variants  # noqa: E402
from khmer_segmenter.spelling import _base_skeleton  # noqa: E402

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
SPICE_DIR = PROJECT_ROOT / "dataset" / "khmer-dict-spice"
LEXICON_DIR = PROJECT_ROOT / "dataset" / "lexicon" / "generated"
BUILD_DIR = PROJECT_ROOT / "build"

KNOWN_WORD_FILES = (
    "khmer_spellcheck_words.txt",
    "khmer_dictionary_words.txt",
    "khmer_dictionary_author_curated_words.txt",
    "khmer_dictionary_rac_derived_words.txt",
    "khmer_dictionary_rac_usage_words.txt",
    "khmer_dictionary_community_spellings.txt",
)

# Ordered: the first matching marker wins.
CATEGORY_MARKERS = (
    ("person_name", ("ឈ្មោះ",)),
    ("place", ("ស្រុក", "ក្រុង", "ខេត្ត", "កោះ", "ទន្លេ")),
    ("ethnicity", ("ជនជាតិ", "ជាតិ")),
    ("ancient", ("បុរាណ",)),
    ("verb", ("(កិ.)",)),
    ("adjective", ("(គុ.)",)),
    ("noun", ("(ន.)",)),
)


def _known_forms(normalizer: KhmerNormalizer) -> set[str]:
    forms: set[str] = set()
    for name in KNOWN_WORD_FILES:
        path = DATA_DIR / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            word = normalizer.normalize(line.strip())
            if word:
                forms.add(word)
                forms.update(coeng_da_ta_variants(word))
    if LEXICON_DIR.is_dir():
        for path in sorted(LEXICON_DIR.glob("*.klex.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for entry in data.get("entries", ()):
                word = normalizer.normalize(str(entry.get("word", "")).strip())
                if word:
                    forms.add(word)
                    forms.update(coeng_da_ta_variants(word))
    return forms


def _category(definition: str) -> str:
    for name, markers in CATEGORY_MARKERS:
        if any(marker in definition for marker in markers):
            return name
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice-dir", type=Path, default=SPICE_DIR)
    parser.add_argument("--output", type=Path, default=BUILD_DIR / "chuon_new_words_review.tsv")
    args = parser.parse_args()

    source = args.spice_dir / "kh_dictionary.csv"
    if not source.is_file():
        parser.error("Chuon Nath source not found; run 'python scripts/fetch_sources.py'.")

    normalizer = KhmerNormalizer()
    known = _known_forms(normalizer)
    known_skeletons = {_base_skeleton(word) for word in known}
    freq_path = DATA_DIR / "khmer_word_frequencies_chuon.json"
    frequencies = (
        json.loads(freq_path.read_text(encoding="utf-8")) if freq_path.is_file() else {}
    )

    rows = []
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            word = normalizer.normalize((row.get("word") or "").strip())
            if not word or word in known:
                continue
            if any(c.isspace() for c in word) or not all(
                "\u1780" <= c <= "\u17d3" or c == "\u17dd" for c in word
            ):
                continue
            if _base_skeleton(word) in known_skeletons:
                continue
            definition = (row.get("definition") or "").replace("\n", " ")
            rows.append(
                {
                    "word": word,
                    "category": _category(definition),
                    "chuon_freq": frequencies.get(word, 0),
                    "definition": definition[:140],
                    "decision": "",
                }
            )
    rows.sort(key=lambda item: (-int(item["chuon_freq"]), item["category"], item["word"]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["word", "category", "chuon_freq", "definition", "decision"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output} ({len(rows):,} new words/names)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
