#!/usr/bin/env python3
"""Run a local, provenance-aware Hugging Face corpus frequency experiment.

Raw corpus samples and generated frequency files belong under ``experiments/``,
which is ignored by Git. This script never changes packaged linguistic data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter import KhmerSegmenter  # noqa: E402
from khmer_segmenter.evaluation import (  # noqa: E402
    boundary_offsets,
    evaluate_records,
    load_khmer_alt,
    load_khpos,
)


SOURCES = {
    "wikipedia": {
        "dataset": "wikimedia/wikipedia",
        "config": "20231101.km",
        "split": "train",
        "license": "CC BY-SA 3.0 and GFDL",
        "credit": "Wikimedia contributors and the Wikimedia Foundation",
        "url": "https://huggingface.co/datasets/wikimedia/wikipedia",
        "weight": 0.5,
    },
    "fineweb2": {
        "dataset": "HuggingFaceFW/fineweb-2",
        "config": "khm_Khmr",
        "split": "train",
        "license": "ODC-By 1.0; underlying Common Crawl terms also apply",
        "credit": "Hugging Face FineWeb2 authors and Common Crawl",
        "url": "https://huggingface.co/datasets/HuggingFaceFW/fineweb-2",
        "weight": 0.2,
    },
}


def stable_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_text(text: str, max_chars: int) -> str:
    """Normalize layout while retaining punctuation and sentence boundaries."""
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)[:max_chars]


def khmer_ratio(text: str) -> float:
    letters = sum(char.isalpha() for char in text)
    if not letters:
        return 0.0
    khmer = sum(char.isalpha() and "\u1780" <= char <= "\u17ff" for char in text)
    return khmer / letters


def iter_chunks(text: str, max_chars: int = 600):
    """Yield bounded sentence-like chunks without deleting delimiters."""
    start = 0
    for index, char in enumerate(text, start=1):
        if char in "។៕!?\n" or index - start >= max_chars:
            chunk = text[start:index].strip()
            if chunk:
                yield chunk
            start = index
    tail = text[start:].strip()
    if tail:
        yield tail


def download_samples(args: argparse.Namespace) -> dict:
    try:
        from datasets import load_dataset
        from huggingface_hub import dataset_info
    except ImportError as exc:
        raise SystemExit(
            "Install the optional research dependencies first: "
            "python -m pip install -e .[corpus]"
        ) from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "local segmentation frequency experiment; raw text is not redistributed",
        "sampling": {
            "seed": args.seed,
            "shuffle_buffer": args.shuffle_buffer,
            "minimum_khmer_ratio": args.minimum_khmer_ratio,
            "maximum_characters_per_document": args.max_chars,
        },
        "sources": {},
    }

    for source_name in args.sources:
        spec = SOURCES[source_name]
        limit = args.wikipedia_limit if source_name == "wikipedia" else args.fineweb2_limit
        destination = args.output_dir / f"{source_name}.jsonl"
        revision = dataset_info(spec["dataset"]).sha
        stream = load_dataset(
            spec["dataset"], spec["config"], split=spec["split"], streaming=True
        ).shuffle(seed=args.seed, buffer_size=args.shuffle_buffer)

        accepted = scanned = duplicate = low_khmer = 0
        seen = set()
        with destination.open("w", encoding="utf-8") as handle:
            for row in stream:
                if accepted >= limit:
                    break
                scanned += 1
                text = compact_text(str(row.get("text", "")), args.max_chars)
                if khmer_ratio(text) < args.minimum_khmer_ratio:
                    low_khmer += 1
                    continue
                digest = stable_digest(text)
                if digest in seen:
                    duplicate += 1
                    continue
                seen.add(digest)
                payload = {
                    "source": source_name,
                    "source_id": str(row.get("id", digest)),
                    "text_sha256": digest,
                    "text": text,
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                accepted += 1

        manifest["sources"][source_name] = {
            **spec,
            "revision": revision,
            "requested": limit,
            "accepted": accepted,
            "scanned": scanned,
            "duplicates_rejected": duplicate,
            "low_khmer_rejected": low_khmer,
            "local_file": destination.name,
            "local_sha256": file_digest(destination),
        }
        print(f"{source_name}: accepted {accepted:,} of {scanned:,} scanned documents")

    manifest_path = args.output_dir / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def is_lexical_token(segmenter: KhmerSegmenter, token: str) -> bool:
    return (
        token in segmenter.words
        and any("\u1780" <= char <= "\u17ff" for char in token)
        and not segmenter._is_separator(token)
    )


def is_unknown_lexical_token(segmenter: KhmerSegmenter, token: str) -> bool:
    """Return true for unknown Khmer letter spans, excluding numbers and signs."""
    return (
        token not in segmenter.words
        and any("\u1780" <= char <= "\u17b3" for char in token)
        and not segmenter._is_digit(token)
        and not segmenter._is_separator(token)
    )


def build_frequencies(args: argparse.Namespace) -> dict:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
    dictionary_path = data_dir / "khmer_dictionary_words.txt"
    baseline_path = data_dir / "khmer_word_frequencies.json"
    segmenter = KhmerSegmenter(dictionary_path, baseline_path)
    baseline = Counter(json.loads(baseline_path.read_text(encoding="utf-8")))

    source_counts = defaultdict(Counter)
    unknown_counts = defaultdict(Counter)
    stats = defaultdict(Counter)
    for source_name in args.sources:
        source_file = args.sample_dir / f"{source_name}.jsonl"
        with source_file.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                stats[source_name]["documents"] += 1
                for chunk in iter_chunks(record["text"], args.chunk_chars):
                    tokens = segmenter.segment(chunk)
                    lexical = [token for token in tokens if is_lexical_token(segmenter, token)]
                    unknown = [
                        token
                        for token in tokens
                        if is_unknown_lexical_token(segmenter, token)
                    ]
                    denominator = len(lexical) + len(unknown)
                    unknown_rate = len(unknown) / denominator if denominator else 0.0
                    stats[source_name]["chunks"] += 1
                    stats[source_name]["unknown_tokens"] += len(unknown)
                    unknown_counts[source_name].update(unknown)
                    if unknown_rate > args.maximum_unknown_rate:
                        stats[source_name]["chunks_rejected"] += 1
                        continue
                    source_counts[source_name].update(lexical)
                    stats[source_name]["accepted_tokens"] += len(lexical)

    weighted_total = sum(
        count * SOURCES[source]["weight"]
        for source, counts in source_counts.items()
        for count in counts.values()
    )
    target_addition = sum(baseline.values()) * args.corpus_share
    scale = target_addition / weighted_total if weighted_total else 0.0
    additions = Counter()
    additions_by_source = {}
    for source, counts in source_counts.items():
        weighted = Counter(
            {
                word: max(1, math.floor(count * SOURCES[source]["weight"] * scale))
                for word, count in counts.items()
            }
        )
        additions.update(weighted)
        additions_by_source[source] = sum(weighted.values())

    experimental = baseline + additions
    ordered = dict(sorted(experimental.items(), key=lambda item: (-item[1], item[0])))
    frequency_path = args.output_dir / "khmer_word_frequencies.experimental.json"
    frequency_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    candidate_path = args.output_dir / "unknown_candidates.json"
    candidate_path.write_text(
        json.dumps(
            {
                source: counts.most_common(args.unknown_candidate_limit)
                for source, counts in unknown_counts.items()
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "policy": {
            "sample_directory": str(args.sample_dir.resolve()),
            "counts_only_existing_dictionary_words": True,
            "maximum_chunk_characters": args.chunk_chars,
            "maximum_unknown_rate": args.maximum_unknown_rate,
            "target_corpus_share_of_baseline": args.corpus_share,
            "source_weights": {name: SOURCES[name]["weight"] for name in args.sources},
            "unknown_candidates_are_not_added_to_dictionary": True,
        },
        "baseline_tokens": sum(baseline.values()),
        "experimental_tokens": sum(experimental.values()),
        "added_weighted_tokens": sum(additions.values()),
        "added_weighted_tokens_by_source": additions_by_source,
        "source_statistics": {name: dict(values) for name, values in stats.items()},
        "frequency_file": frequency_path.name,
        "unknown_candidate_file": candidate_path.name,
    }
    (args.output_dir / "frequency_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def evaluate(args: argparse.Namespace) -> dict:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
    dictionary_path = data_dir / "khmer_dictionary_words.txt"
    models = {
        "baseline": data_dir / "khmer_word_frequencies.json",
        "experimental": args.output_dir / "khmer_word_frequencies.experimental.json",
    }
    datasets = {
        "khpos": lambda: load_khpos(
            split="test", cache_dir=PROJECT_ROOT / "dataset" / "benchmarks"
        ),
        "khmer_alt_pos": lambda: load_khmer_alt(
            split="test", cache_dir=PROJECT_ROOT / "dataset" / "benchmarks"
        ),
    }
    results = {}
    segmenters = {}
    for model_name, frequency_path in models.items():
        segmenter = KhmerSegmenter(dictionary_path, frequency_path)
        segmenters[model_name] = segmenter
        results[model_name] = {}
        for dataset_name, loader in datasets.items():
            report = evaluate_records(segmenter, loader(), limit=args.evaluation_limit)
            results[model_name][dataset_name] = report["summary"]

    deltas = {}
    for dataset_name in datasets:
        baseline = results["baseline"][dataset_name]
        experimental = results["experimental"][dataset_name]
        deltas[dataset_name] = {
            key: experimental[key] - baseline[key]
            for key in (
                "boundary_precision",
                "boundary_recall",
                "boundary_f1",
                "exact_sentence_match",
                "unknown_word_rate",
                "avg_latency_ms",
            )
        }
    paired = {}
    for dataset_name, loader in datasets.items():
        comparison = Counter()
        for index, record in enumerate(loader()):
            if args.evaluation_limit is not None and index >= args.evaluation_limit:
                break
            text = "".join(
                segmenters["baseline"].normalizer.normalize(token)
                for token in record["tokens"]
            )
            gold = boundary_offsets(
                segmenters["baseline"].normalizer.normalize(token)
                for token in record["tokens"]
            )
            baseline_tokens = segmenters["baseline"].segment(text)
            experimental_tokens = segmenters["experimental"].segment(text)
            baseline_boundaries = boundary_offsets(baseline_tokens)
            experimental_boundaries = boundary_offsets(experimental_tokens)
            if baseline_boundaries == experimental_boundaries:
                comparison["unchanged_sentences"] += 1
                continue
            comparison["changed_sentences"] += 1
            baseline_correct = len(gold & baseline_boundaries)
            experimental_correct = len(gold & experimental_boundaries)
            if experimental_correct > baseline_correct:
                comparison["more_correct_boundaries"] += 1
            elif experimental_correct < baseline_correct:
                comparison["fewer_correct_boundaries"] += 1
            else:
                comparison["same_correct_boundary_count"] += 1
            baseline_exact = baseline_boundaries == gold
            experimental_exact = experimental_boundaries == gold
            comparison["exact_sentences_gained"] += int(
                experimental_exact and not baseline_exact
            )
            comparison["exact_sentences_lost"] += int(
                baseline_exact and not experimental_exact
            )
        paired[dataset_name] = dict(comparison)

    payload = {
        "results": results,
        "experimental_minus_baseline": deltas,
        "paired_boundary_comparison": paired,
        "latency_note": (
            "Latency is observational only: models run sequentially in one process, "
            "so cache and warm-up order can affect the reported delta."
        ),
    }
    (args.output_dir / "evaluation_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "build", "evaluate", "all"])
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "experiments" / "hf-corpora"
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=None,
        help="Directory containing downloaded JSONL samples (build action)",
    )
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES), default=list(SOURCES))
    parser.add_argument("--wikipedia-limit", type=int, default=25_000)
    parser.add_argument("--fineweb2-limit", type=int, default=100_000)
    parser.add_argument("--max-chars", type=int, default=4_000)
    parser.add_argument("--minimum-khmer-ratio", type=float, default=0.70)
    parser.add_argument("--shuffle-buffer", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--chunk-chars", type=int, default=600)
    parser.add_argument("--maximum-unknown-rate", type=float, default=0.15)
    parser.add_argument("--corpus-share", type=float, default=0.20)
    parser.add_argument("--unknown-candidate-limit", type=int, default=2_000)
    parser.add_argument("--evaluation-limit", type=int)
    args = parser.parse_args()
    if args.sample_dir is None:
        args.sample_dir = args.output_dir
    return args


def main() -> None:
    args = parse_args()
    if args.action in {"download", "all"}:
        download_samples(args)
    if args.action in {"build", "all"}:
        build_frequencies(args)
    if args.action in {"evaluate", "all"}:
        evaluate(args)


if __name__ == "__main__":
    main()
