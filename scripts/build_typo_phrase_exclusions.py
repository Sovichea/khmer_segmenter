#!/usr/bin/env python3
"""Compile reviewed phrase collisions that must not be treated as typos.

The typo detector derives one-character substitution aliases from dictionary
words. Some of those aliases are really phrases of common words, such as
ត្រីសួរ ("fish asked") resembling the rare compound ត្រីសូរ. This script
collects those collisions and writes the shared exclusion list consumed by the
Python and Rust ports.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.spelling import TypoDetector, load_approved_typo_corrections

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
DEFAULT_OUTPUT = DATA_DIR / "khmer_typo_phrase_exclusions.txt"
DEFAULT_RUST_OUTPUT = PROJECT_ROOT / "port" / "rust" / "data" / "khmer_typo_phrase_exclusions.txt"

FREQUENCY_FLOOR = 5.0
PHRASE_OVERRIDE_RATIO = 45.0

# RO insertions/deletions overlap heavily with real missing/extra-RO typos such
# as ចងកា -> ចងការ, so they are not collected automatically. These reviewed
# phrases are unambiguous and are added by hand.
CURATED_PHRASES = {
    "ដើរមក",  # ដើរ + មក, not ដើមក
    "ជាភាព",  # ជា + ភាព, not ជរាភាព
    "ជាធម៌",
    "ជាទុក្ខ",
    "ជារោគ",
    "ជាលក្ខណៈ",
    "វាជើង",
    "ភ្នែកគោ",
    "ស្រូវវា",
}


def collect(segmenter: KhmerSegmenter) -> list[str]:
    # Build the detector without phrase exclusions so regeneration is stable.
    corrections = load_approved_typo_corrections(segmenter.data_files.typo_corrections)
    detector = TypoDetector(
        segmenter.spellcheck_words,
        segmenter.word_frequencies,
        corrections,
        autocomplete_words=segmenter.autocomplete_words,
    )
    approved = set(corrections)
    frequencies = detector.frequencies
    exclusions: set[str] = set(CURATED_PHRASES)
    for alias, intended in detector.reviewed_typos.items():
        if alias in approved:
            continue
        if len(alias) != len(intended):
            continue
        if sum(left != right for left, right in zip(alias, intended)) != 1:
            continue
        tokens = segmenter.segment(alias)
        if len(tokens) < 2:
            continue
        if any(len(token) == 1 for token in tokens):
            continue
        intended_frequency = max(float(frequencies.get(intended, 0) or 0), FREQUENCY_FLOOR)
        rarest = min(
            max(float(frequencies.get(token, 0) or 0), FREQUENCY_FLOOR) for token in tokens
        )
        if rarest > PHRASE_OVERRIDE_RATIO * intended_frequency:
            exclusions.add(alias)
    return sorted(exclusions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rust-output", type=Path, default=DEFAULT_RUST_OUTPUT)
    args = parser.parse_args()

    segmenter = KhmerSegmenter()
    exclusions = collect(segmenter)
    body = "\n".join(exclusions) + ("\n" if exclusions else "")
    args.output.write_text(body, encoding="utf-8")
    args.rust_output.write_text(body, encoding="utf-8")
    print(f"wrote {len(exclusions)} phrase exclusions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
