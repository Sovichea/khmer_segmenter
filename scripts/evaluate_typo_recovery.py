#!/usr/bin/env python3
"""Evaluate deterministic missing-vowel recovery from the RAC lexicon."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter import KhmerSegmenter  # noqa: E402


def missing_vowel_cases(
    segmenter: KhmerSegmenter, limit: int
) -> list[tuple[str, str]]:
    """Return frequent words paired with one deterministic vowel deletion."""

    cases: list[tuple[str, str]] = []
    ranked_words = sorted(
        segmenter.word_frequencies.items(),
        key=lambda item: (-item[1], item[0]),
    )
    for word, _ in ranked_words:
        if word not in segmenter.spellcheck_words or len(word) < 3:
            continue
        for index, char in enumerate(word):
            if "\u17b6" <= char <= "\u17c5":
                corrupted = word[:index] + word[index + 1 :]
                if corrupted and corrupted not in segmenter.spellcheck_words:
                    cases.append((word, corrupted))
                    break
        if len(cases) >= limit:
            break
    return cases


def evaluate(segmenter: KhmerSegmenter, cases: list[tuple[str, str]]) -> dict:
    started = time.perf_counter()
    exact_span = top_1 = top_k = clean_false_positives = 0
    misses = []

    for expected, corrupted in cases:
        diagnostics = segmenter.detect_typos(corrupted)
        exact = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.start == 0 and diagnostic.end == len(corrupted)
        ]
        if exact:
            exact_span += 1
            suggestions = [suggestion.text for suggestion in exact[0].suggestions]
            top_1 += int(bool(suggestions) and suggestions[0] == expected)
            top_k += int(expected in suggestions)
        elif len(misses) < 25:
            misses.append({"expected": expected, "corrupted": corrupted})

        clean_false_positives += int(bool(segmenter.detect_typos(expected)))

    elapsed = time.perf_counter() - started
    total = len(cases)

    def ratio(count: int) -> float:
        return count / total if total else 0.0

    return {
        "benchmark": "synthetic_missing_dependent_vowel",
        "warning": "Dictionary-derived diagnostic; not a curated real-typo benchmark.",
        "cases": total,
        "whole_span_recall": ratio(exact_span),
        "top_1_accuracy": ratio(top_1),
        "top_k_recall": ratio(top_k),
        "clean_false_positive_rate": ratio(clean_false_positives),
        "elapsed_seconds": elapsed,
        "cases_per_second": total / elapsed if elapsed else 0.0,
        "sample_misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than zero")

    segmenter = KhmerSegmenter()
    report = evaluate(segmenter, missing_vowel_cases(segmenter, args.limit))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
