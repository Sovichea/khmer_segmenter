#!/usr/bin/env python3
"""Augment corpus frequencies with training-only gold token counts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from khmer_segmenter.evaluation import load_khmer_alt, load_khpos
from khmer_segmenter.normalization import KhmerNormalizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_word_frequencies_corpus.json",
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_dictionary_words.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_word_frequencies.json",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
        / "khmer_word_frequencies_provenance.json",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=["khpos", "khmer_alt_pos"],
        default=["khpos", "khmer_alt_pos"],
    )
    args = parser.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    dictionary = set(args.dictionary.read_text(encoding="utf-8").splitlines())
    normalizer = KhmerNormalizer()
    gold_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()
    dataset_sentences = Counter()
    rejected = Counter()

    loaders = {"khpos": load_khpos, "khmer_alt_pos": load_khmer_alt}
    for dataset in args.datasets:
        loader = loaders[dataset]
        for record in loader(
            split="train", cache_dir=PROJECT_ROOT / "dataset" / "benchmarks"
        ):
            dataset_sentences[dataset] += 1
            sentence_words = set()
            for raw_token in record["tokens"]:
                token = normalizer.normalize(raw_token)
                if token not in dictionary:
                    rejected[dataset] += 1
                    continue
                gold_counts[token] += 1
                sentence_words.add(token)
            document_counts.update(sentence_words)

    combined = Counter({word: int(count) for word, count in base.items()})
    combined.update(gold_counts)
    ordered = dict(sorted(combined.items(), key=lambda item: (-item[1], item[0])))
    args.output.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )

    metadata = {
        "method": "corpus occurrence counts plus gold-train occurrence counts",
        "datasets": args.datasets,
        "split_policy": "SHA-256 sentence ID buckets: 80% train, 10% dev, 10% test",
        "base_file": args.base.name,
        "base_unique_words": len(base),
        "base_tokens": sum(base.values()),
        "gold_sentences": dict(dataset_sentences),
        "gold_tokens_added": sum(gold_counts.values()),
        "gold_unique_words_added_or_updated": len(gold_counts),
        "gold_tokens_absent_from_dictionary": dict(rejected),
        "document_frequency": dict(document_counts.most_common()),
        "combined_unique_words": len(ordered),
        "combined_tokens": sum(ordered.values()),
    }
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in metadata.items() if k != "document_frequency"}, indent=2))


if __name__ == "__main__":
    main()
