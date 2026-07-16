#!/usr/bin/env python3
"""Benchmark opt-in missing-mark diagnostics without changing segmentation."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.evaluation import load_khmer_alt, load_khpos
from khmer_segmenter.typo_recovery import is_recoverable_mark


PREFIX = "ខ្ញុំមាន"
SUFFIX = "ច្រើន"


def deletion_cases(segmenter: KhmerSegmenter):
    for word in sorted(segmenter.words):
        if len(word) < 3:
            continue
        for offset, char in enumerate(word):
            if not is_recoverable_mark(char):
                continue
            surface = word[:offset] + word[offset + 1 :]
            if surface and surface not in segmenter.words:
                yield word, surface


def corpus_diagnostic_incidence(segmenter, records):
    sentence_count = diagnostic_sentences = diagnostic_count = 0
    latencies = []
    for record in records:
        text = "".join(segmenter.normalizer.normalize(item) for item in record["tokens"])
        baseline = segmenter.segment(text)
        started = time.perf_counter_ns()
        analysis = segmenter.analyze(text, typo_recovery=True)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        if [token.text for token in analysis] != baseline:
            raise RuntimeError("typo analysis changed segmentation")
        sentence_count += 1
        diagnostic_count += len(analysis.diagnostics)
        diagnostic_sentences += bool(analysis.diagnostics)
    return {
        "sentences": sentence_count,
        "sentences_with_diagnostics": diagnostic_sentences,
        "sentence_diagnostic_rate": (
            diagnostic_sentences / sentence_count if sentence_count else 0.0
        ),
        "diagnostics": diagnostic_count,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--clean-limit", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260716)
    parser.add_argument("--khpos", type=Path)
    parser.add_argument("--khmer-alt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    segmenter = KhmerSegmenter()
    cases = list(deletion_cases(segmenter))
    rng = random.Random(args.seed)
    if args.limit >= 0 and len(cases) > args.limit:
        cases = rng.sample(cases, args.limit)

    index_started = time.perf_counter()
    if cases:
        segmenter.analyze(cases[0][1], typo_recovery=True)
    index_build_seconds = time.perf_counter() - index_started

    whole_span_hits = top1_hits = unchanged_segmentations = 0
    latencies = []
    for word, typo in cases:
        text = PREFIX + typo + SUFFIX
        expected_start = len(PREFIX)
        expected_end = expected_start + len(typo)
        baseline = segmenter.segment(text)
        started = time.perf_counter_ns()
        analysis = segmenter.analyze(text, typo_recovery=True)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        unchanged_segmentations += [token.text for token in analysis] == baseline
        matching = [
            item
            for item in analysis.diagnostics
            if item.start == expected_start and item.end == expected_end
        ]
        whole_span_hits += bool(matching)
        top1_hits += bool(matching and matching[0].candidate == word)

    clean_words = sorted(segmenter.words)
    if len(clean_words) > args.clean_limit:
        clean_words = rng.sample(clean_words, args.clean_limit)
    clean_diagnostics = clean_changed = 0
    clean_latencies = []
    for word in clean_words:
        baseline = segmenter.segment(word)
        started = time.perf_counter_ns()
        analysis = segmenter.analyze(word, typo_recovery=True)
        clean_latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        clean_changed += [token.text for token in analysis] != baseline
        clean_diagnostics += len(analysis.diagnostics)

    case_count = len(cases)
    report = {
        "configuration": {
            "dictionary_words": len(segmenter.words),
            "missing_mark_index_keys": len(segmenter._missing_mark_index or ()),
            "synthetic_cases": case_count,
            "sampling_seed": args.seed,
            "index_build_seconds": index_build_seconds,
        },
        "synthetic_missing_mark": {
            "whole_span_recall": whole_span_hits / case_count if case_count else 0.0,
            "top1_correction_accuracy": top1_hits / case_count if case_count else 0.0,
            "unchanged_segmentation_rate": (
                unchanged_segmentations / case_count if case_count else 1.0
            ),
            "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        },
        "clean_dictionary_words": {
            "words_tested": len(clean_words),
            "changed_segmentations": clean_changed,
            "diagnostics": clean_diagnostics,
            "median_latency_ms": (
                statistics.median(clean_latencies) if clean_latencies else 0.0
            ),
        },
        "gold_corpus_diagnostic_incidence": {},
    }
    if args.khpos:
        report["gold_corpus_diagnostic_incidence"]["khpos"] = (
            corpus_diagnostic_incidence(
                segmenter,
                load_khpos(split="test", path=args.khpos),
            )
        )
    if args.khmer_alt:
        report["gold_corpus_diagnostic_incidence"]["khmer_alt"] = (
            corpus_diagnostic_incidence(
                segmenter,
                load_khmer_alt(split="test", path=args.khmer_alt),
            )
        )

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
