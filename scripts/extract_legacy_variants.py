#!/usr/bin/env python3
"""Extract legacy orthography candidates from the Chuon Nath and SBBIC lists.

Forms that appear in those dictionaries but not in the RAC model are legacy
spellings worth reviewing as practical variants. The output is a review TSV and
a clean candidate list; nothing is accepted automatically.

Requires the pinned sources; run ``python scripts/fetch_sources.py`` first.

Example:
    python scripts/extract_legacy_variants.py
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

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
SPICE_DIR = PROJECT_ROOT / "dataset" / "khmer-dict-spice"
LEXICON_DIR = PROJECT_ROOT / "dataset" / "lexicon" / "generated"
OUTPUT_DIR = PROJECT_ROOT / "build"

# Every reviewed spelling-authority layer already in the model.
KNOWN_WORD_FILES = (
    "khmer_spellcheck_words.txt",
    "khmer_dictionary_words.txt",
    "khmer_dictionary_author_curated_words.txt",
    "khmer_dictionary_rac_derived_words.txt",
    "khmer_dictionary_rac_usage_words.txt",
    "khmer_dictionary_community_spellings.txt",
)


def _is_lexical_khmer(text: str) -> bool:
    if not text or any(character.isspace() for character in text):
        return False
    if not ("\u1780" <= text[0] <= "\u17b3"):
        return False
    return all("\u1780" <= c <= "\u17d3" or c == "\u17dd" for c in text)


def _load_words(path: Path) -> set[str]:
    return {line for line in path.read_text(encoding="utf-8").splitlines() if line}


def _known_forms(normalizer: KhmerNormalizer, lexicon_dir: Path) -> set[str]:
    """Return every reviewed spelling form already covered by the model."""

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
    if lexicon_dir.is_dir():
        for path in sorted(lexicon_dir.glob("*.klex.json")):
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice-dir", type=Path, default=SPICE_DIR)
    parser.add_argument("--lexicon-dir", type=Path, default=LEXICON_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    choun_csv = args.spice_dir / "kh_dictionary.csv"
    sbbic_txt = args.spice_dir / "SBBICkm_KH.txt"
    if not choun_csv.is_file() and not sbbic_txt.is_file():
        parser.error(
            "Chuon Nath sources not found; run 'python scripts/fetch_sources.py'."
        )

    normalizer = KhmerNormalizer()
    known = _known_forms(normalizer, args.lexicon_dir)

    sources: dict[str, set[str]] = {}
    if choun_csv.is_file():
        words = set()
        with choun_csv.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                word = normalizer.normalize((row.get("word") or "").strip())
                if word:
                    words.add(word)
        sources["chuon-nath-1967"] = words
    if sbbic_txt.is_file():
        sources["sbbic-khmer-wordlist"] = {
            normalizer.normalize(line.strip())
            for line in sbbic_txt.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    candidates: dict[str, str] = {}
    for source, words in sources.items():
        for word in words:
            if word in known or not _is_lexical_khmer(word):
                continue
            candidates.setdefault(word, source)

    ordered = sorted(candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    review = args.output_dir / "legacy_variants_review.tsv"
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["word", "source", "status", "note"])
        for word in ordered:
            writer.writerow(
                [word, candidates[word], "pending", "Legacy orthography candidate."]
            )
    (args.output_dir / "legacy_variants_candidates.txt").write_text(
        "\n".join(ordered) + ("\n" if ordered else ""), encoding="utf-8"
    )
    print(
        f"wrote {review}\n"
        f"  sources: {', '.join(f'{k} ({len(v):,})' for k, v in sources.items())}\n"
        f"  known forms: {len(known):,}\n"
        f"  clean candidates: {len(ordered):,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
