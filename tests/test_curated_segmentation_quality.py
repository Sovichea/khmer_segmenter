from pathlib import Path

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.evaluation import evaluate_records, load_curated_benchmark

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "curated" / "benchmark.jsonl"

# Release floors for the 300-sentence curated regression set. The bundled
# model is deterministic, so this gate is stable across platforms.
MIN_BOUNDARY_F1 = 0.99
MIN_EXACT_SENTENCE = 0.93
MAX_UNKNOWN_RATE = 0.01


def test_curated_benchmark_meets_release_floor():
    segmenter = KhmerSegmenter()
    records = list(load_curated_benchmark(BENCHMARK, split="all"))
    summary = evaluate_records(segmenter, records)["summary"]

    assert summary["num_sentences"] == 300
    assert summary["boundary_f1"] >= MIN_BOUNDARY_F1
    assert summary["exact_sentence_match"] >= MIN_EXACT_SENTENCE
    assert summary["unknown_word_rate"] <= MAX_UNKNOWN_RATE
