#!/usr/bin/env python3
"""Compile a local Khmer text dictionary and frequency JSON into KDIC."""

from __future__ import annotations

import argparse
from pathlib import Path

from prepare_data import step_compile_kdict, step_compile_klex


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile a local UTF-8 Khmer dictionary and frequency JSON into "
            "the KDIC format shared by the C and Rust implementations."
        )
    )
    parser.add_argument(
        "--lexicon",
        type=Path,
        help="single human-editable KLEX JSON source; replaces the separate input files",
    )
    parser.add_argument(
        "--dict",
        type=Path,
        default=(
            PROJECT_ROOT
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_dictionary_words.txt"
        ),
        help="UTF-8 text dictionary, one word per line",
    )
    parser.add_argument(
        "--freq",
        type=Path,
        default=(
            PROJECT_ROOT
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_word_frequencies.json"
        ),
        help="JSON object mapping words to occurrence counts",
    )
    parser.add_argument(
        "--supplemental",
        type=Path,
        default=(
            PROJECT_ROOT
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_dictionary_supplemental_words.txt"
        ),
        help="optional segmentation-only words; these receive a cost penalty",
    )
    parser.add_argument(
        "--spellcheck",
        type=Path,
        default=(
            PROJECT_ROOT
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_spellcheck_words.txt"
        ),
        help="curated forms that supplemental variants must not promote",
    )
    parser.add_argument(
        "--typo-corrections",
        type=Path,
        default=(
            PROJECT_ROOT
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_typo_corrections.tsv"
        ),
        help="approved typo-to-correction pairs to embed in KDIC v2",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "port" / "common" / "khmer_dictionary.kdict",
        help="Destination KDIC file",
    )
    args = parser.parse_args()

    if args.lexicon is not None:
        if not args.lexicon.is_file():
            parser.error(f"lexicon not found: {args.lexicon}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        step_compile_klex(args.lexicon, args.output)
        return

    for label, path in (("dictionary", args.dict), ("frequency file", args.freq)):
        if not path.is_file():
            parser.error(f"{label} not found: {path}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    step_compile_kdict(
        str(args.dict),
        str(args.freq),
        str(args.output),
        supplemental_path=str(args.supplemental),
        spellcheck_path=str(args.spellcheck),
        typo_corrections_path=str(args.typo_corrections),
    )


if __name__ == "__main__":
    main()
