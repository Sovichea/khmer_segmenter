#!/usr/bin/env python3
"""Repository wrapper for the public local-dictionary preparation API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.preparation import prepare_dictionary, read_words  # noqa: E402

__all__ = ["read_words"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize a user-obtained RAC dictionary TSV for local use"
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
    report = prepare_dictionary(
        args.rac_tsv,
        args.dictionary_dir,
        port_dictionary=args.port_dictionary,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
