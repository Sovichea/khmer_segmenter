import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "curated"


def test_release_benchmark_is_frozen_and_fully_approved():
    benchmark = ROOT / "benchmark.jsonl"
    metadata = json.loads((ROOT / "benchmark.meta.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in benchmark.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(records) == metadata["records"] == 300
    assert Counter(record["split"] for record in records) == {"dev": 200, "test": 100}
    assert Counter(record["category"] for record in records) == metadata["categories"]
    assert all(record["review"]["status"] == "approved" for record in records)
    assert hashlib.sha256(benchmark.read_bytes()).hexdigest() == metadata["benchmark_sha256"]
