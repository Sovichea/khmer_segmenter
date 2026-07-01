#!/usr/bin/env python3
"""Build deterministic lexical POS candidates from khPOS training data."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from khmer_segmenter.evaluation import load_khpos
from khmer_segmenter.normalization import KhmerNormalizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_word_pos.json",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_word_pos_provenance.json",
    )
    args = parser.parse_args()

    normalizer = KhmerNormalizer()
    candidates = defaultdict(set)
    sentences = tokens = 0
    for record in load_khpos(
        split="train", cache_dir=PROJECT_ROOT / "dataset" / "benchmarks"
    ):
        sentences += 1
        for word, tag in zip(record["tokens"], record["metadata"]["pos_tags"]):
            candidates[normalizer.normalize(word)].add(tag)
            tokens += 1

    output = {word: sorted(tags) for word, tags in sorted(candidates.items())}
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "source": "khPOS",
        "split": "derived train only",
        "split_policy": "SHA-256 sentence ID buckets: 80% train, 10% dev, 10% test",
        "sentences": sentences,
        "tokens": tokens,
        "lexical_entries": len(output),
        "unambiguous_entries": sum(len(tags) == 1 for tags in output.values()),
        "ambiguous_entries": sum(len(tags) > 1 for tags in output.values()),
        "semantics": "Lexical candidates only; no contextual POS disambiguation",
    }
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
