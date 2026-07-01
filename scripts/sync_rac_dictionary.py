#!/usr/bin/env python3
"""Build the runtime dictionary from RAC 2022 and community vocabularies."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from khmer_segmenter.normalization import KhmerNormalizer


REFERENCE_NAME = "Khmer Dictionary 2022"
REFERENCE_AUTHORITY = (
    "National Council of Khmer Language, Royal Academy of Cambodia"
)
EXTRACTION_URL = (
    "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k"
)
EXTRACTION_CREDIT = "Seanghay Hay (Hugging Face user seanghay)"


def read_words(path: Path, tsv: bool = False) -> tuple[list[str], int]:
    normalizer = KhmerNormalizer()
    words = []
    rejected = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            raw = line.rstrip("\r\n")
            if tsv:
                raw = raw.split("\t", 1)[0]
            word = normalizer.normalize(raw.strip())
            # Entries containing whitespace cannot be matched by this segmenter.
            if not word or any(char.isspace() for char in word):
                rejected += 1
                continue
            words.append(word)
    return words, rejected


def write_words(path: Path, words: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize RAC-approved and supplemental Khmer vocabulary"
    )
    parser.add_argument("--rac-tsv", required=True, type=Path)
    parser.add_argument(
        "--dictionary-dir",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data",
    )
    parser.add_argument(
        "--port-dictionary",
        type=Path,
        default=PROJECT_ROOT / "port" / "common" / "khmer_dictionary_words.txt",
    )
    args = parser.parse_args()

    runtime_path = args.dictionary_dir / "khmer_dictionary_words.txt"
    official_path = args.dictionary_dir / "khmer_dictionary_official_2022_words.txt"
    supplemental_path = args.dictionary_dir / "khmer_dictionary_supplemental_words.txt"
    report_path = args.dictionary_dir / "khmer_dictionary_provenance.json"

    reference_rows, reference_rejected = read_words(args.rac_tsv, tsv=True)
    # Once provenance files exist, they are the canonical inputs. Re-reading the
    # generated union can accidentally promote merge markers or official words
    # into the supplemental vocabulary.
    existing_source = supplemental_path if supplemental_path.exists() else runtime_path
    existing_rows, existing_rejected = read_words(existing_source)
    official = set(reference_rows)
    existing = set(existing_rows)
    supplemental = existing - official
    runtime = official | supplemental

    write_words(official_path, official)
    write_words(supplemental_path, supplemental)
    write_words(runtime_path, runtime)
    args.port_dictionary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime_path, args.port_dictionary)

    report = {
        "reference": {
            "name": REFERENCE_NAME,
            "authority": REFERENCE_AUTHORITY,
            "extraction": EXTRACTION_URL,
            "extraction_credit": EXTRACTION_CREDIT,
            "source_metadata_accessed": "2026-07-01",
            "terms": "Research purpose only; not for commercial use",
            "usage": "Community-approved for this non-profit open-source project",
            "source_rows": len(reference_rows) + reference_rejected,
            "accepted_unique_headwords": len(official),
            "rejected_rows": reference_rejected,
        },
        "supplemental_policy": (
            "Existing words absent from the RAC extraction are retained as "
            "community vocabulary; absence is not proof of invalidity."
        ),
        "counts": {
            "official_headwords": len(official),
            "supplemental_retained": len(supplemental),
            "runtime_union": len(runtime),
            "supplemental_rejected": existing_rejected,
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
