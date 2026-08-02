#!/usr/bin/env python3
"""Compare the RAC-only model with uncurated machine-produced segmentations.

This is a compatibility diagnostic, not a linguistic accuracy evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from khmer_segmenter import KhmerSegmenter  # noqa: E402
from khmer_segmenter.normalization import KhmerNormalizer  # noqa: E402


def lexical_char(char: str) -> bool:
    code = ord(char)
    return 0x1780 <= code <= 0x17D3 or code in {0x17D7, 0x17DD}


def project(text: str) -> str:
    return "".join(char for char in text if lexical_char(char))


def projected_boundaries(tokens: list[str]) -> tuple[str, set[int]]:
    pieces: list[str] = []
    boundaries: set[int] = set()
    position = 0
    for token in tokens:
        piece = project(token)
        if not piece:
            continue
        pieces.append(piece)
        position += len(piece)
        boundaries.add(position)
    text = "".join(pieces)
    boundaries.discard(len(text))
    return text, boundaries


def parse_reference(text: str, normalizer: KhmerNormalizer) -> list[str]:
    return [value for part in text.split("\u200b") if (value := normalizer.normalize(part))]


def select_evenly(items: list[Path], limit: int) -> list[Path]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indices = sorted({round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)})
    return [items[index] for index in indices]


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def summarize(stats: Counter) -> dict[str, float | int]:
    precision = safe_ratio(stats["matched"], stats["predicted"])
    recall = safe_ratio(stats["matched"], stats["reference"])
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "documents": stats["documents"],
        "boundary_precision_vs_machine_reference": precision,
        "boundary_recall_vs_machine_reference": recall,
        "boundary_f1_vs_machine_reference": f1,
        "exact_document_lexical_boundaries": safe_ratio(stats["exact"], stats["documents"]),
        "unknown_token_rate": safe_ratio(stats["unknown_tokens"], stats["lexical_tokens"]),
        "unknown_character_rate": safe_ratio(stats["unknown_chars"], stats["lexical_chars"]),
        "matched_boundaries": stats["matched"],
        "reference_boundaries": stats["reference"],
        "predicted_boundaries": stats["predicted"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir", type=Path)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "src" / "khmer_segmenter" / "dictionary_data",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    normalizer = KhmerNormalizer()
    segmenter = KhmerSegmenter(data_dir=args.data_dir)
    files = sorted(args.corpus_dir.glob("*_orig.txt"))
    selected = select_evenly(files, args.sample)
    stats: Counter = Counter()
    skipped = 0

    for original_path in selected:
        document_id = original_path.name.removesuffix("_orig.txt")
        reference_path = original_path.with_name(document_id + "_seg_200b.txt")
        if not reference_path.exists():
            continue
        original = normalizer.normalize(
            original_path.read_text(encoding="utf-8-sig", errors="replace")
        )
        reference_tokens = parse_reference(
            reference_path.read_text(encoding="utf-8-sig", errors="replace"), normalizer
        )
        reference_text, reference_boundaries = projected_boundaries(reference_tokens)
        if reference_text != project(original):
            skipped += 1
            continue
        predicted_tokens = segmenter.segment(original, normalize=False)
        predicted_text, predicted_boundaries = projected_boundaries(predicted_tokens)
        if predicted_text != reference_text:
            raise RuntimeError(f"projection mismatch for {document_id}")
        stats["matched"] += len(reference_boundaries & predicted_boundaries)
        stats["reference"] += len(reference_boundaries)
        stats["predicted"] += len(predicted_boundaries)
        stats["exact"] += int(reference_boundaries == predicted_boundaries)
        stats["documents"] += 1
        for token in predicted_tokens:
            if segmenter._is_separator(token) or segmenter._is_digit(token):
                continue
            stats["lexical_tokens"] += 1
            stats["lexical_chars"] += len(token)
            if token not in segmenter.words:
                stats["unknown_tokens"] += 1
                stats["unknown_chars"] += len(token)

    result = {
        "warning": "The reference is machine-produced and uncurated; these numbers measure compatibility, not linguistic accuracy.",
        "available_documents": len(files),
        "requested_sample": args.sample,
        "normalization_mismatches_skipped": skipped,
        "rac_weighted": summarize(stats),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
