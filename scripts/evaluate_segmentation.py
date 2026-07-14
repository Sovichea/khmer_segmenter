#!/usr/bin/env python3
"""Evaluate khmer_segmenter against a manually segmented corpus."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.evaluation import (
    evaluate_records,
    load_khmer_alt,
    load_khpos,
    write_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", choices=["khpos", "khmer_alt_pos"], default="khpos"
    )
    parser.add_argument("--split", default="train")
    parser.add_argument("--dataset-path", help="Use a local khPOS train.all2 file")
    parser.add_argument("--limit", type=int, help="Evaluate only the first N records")
    parser.add_argument("--output", default="results/khpos_eval.json")
    parser.add_argument("--frequency-path")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / "khmer_segmenter" / "dictionary_data"
    segmenter = KhmerSegmenter(
        str(data_dir / "khmer_dictionary_words.txt"),
        args.frequency_path or str(data_dir / "khmer_word_frequencies.json"),
    )
    loader = load_khpos if args.dataset == "khpos" else load_khmer_alt
    records = loader(
        split=args.split,
        path=args.dataset_path,
        cache_dir=PROJECT_ROOT / "dataset" / "benchmarks",
    )
    report = evaluate_records(segmenter, records, limit=args.limit)
    write_report(report, args.output)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output} ({len(report['errors'])} disagreement records)")


if __name__ == "__main__":
    main()
