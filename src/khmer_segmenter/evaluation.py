"""Utilities for evaluating segmentation against tokenized gold corpora."""

from __future__ import annotations

import json
import hashlib
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator


KHPOS_URL = (
    "https://raw.githubusercontent.com/ye-kyaw-thu/khPOS/master/"
    "corpus-draft-ver-1.0/data/after-replace/train.all2"
)
KHPOS_MARKERS = str.maketrans("", "", "_~^")
KHMER_ALT_URL = "https://zenodo.org/records/3937914/files/km-nova.zip?download=1"
KHMER_ALT_MEMBER = "km-nova/data_km.km-tok.nova"
DERIVED_SPLITS = {"train", "dev", "test", "all"}
CURATED_SPLITS = {"dev", "test", "all"}


def derived_split(dataset: str, source_id: str) -> str:
    """Assign a stable 80/10/10 split without relying on row order."""
    digest = hashlib.sha256(f"{dataset}:{source_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def clean_khpos_token(token: str) -> str:
    """Remove khPOS compound-annotation markers from a surface token."""
    return token.translate(KHPOS_MARKERS)


def parse_khpos_lines(lines: Iterable[str], split: str = "train") -> Iterator[dict]:
    """Parse khPOS ``word/POS`` lines into the common evaluation format."""
    if split not in DERIVED_SPLITS:
        raise ValueError(f"Unknown split {split!r}; use train, dev, test, or all")

    index = 0
    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        tokens = []
        pos_tags = []
        annotated_tokens = []
        for chunk in line.split():
            try:
                token, pos_tag = chunk.rsplit("/", 1)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid khPOS item on source line {line_number}: {chunk!r}"
                ) from exc
            annotated_tokens.append(token)
            tokens.append(clean_khpos_token(token))
            pos_tags.append(pos_tag)

        source_id = str(line_number)
        assigned_split = derived_split("khpos", source_id)
        if split != "all" and assigned_split != split:
            continue
        yield {
            "id": f"khpos:{assigned_split}:{index}",
            "dataset": "khpos",
            "split": assigned_split if split != "all" else "all",
            "tokens": tokens,
            "text": "".join(tokens),
            "metadata": {
                "source_line": line_number,
                "annotated_tokens": annotated_tokens,
                "pos_tags": pos_tags,
            },
        }
        index += 1


def load_khpos(
    split: str = "train",
    path: str | Path | None = None,
    cache_dir: str | Path = "dataset/benchmarks",
) -> Iterator[dict]:
    """Load khPOS from a local file, downloading and caching it when needed."""
    source = Path(path) if path else Path(cache_dir) / "khpos_train.all2"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(KHPOS_URL, source)
    with source.open(encoding="utf-8-sig") as handle:
        yield from parse_khpos_lines(handle, split=split)


def parse_khmer_alt_lines(lines: Iterable[str], split: str = "train") -> Iterator[dict]:
    """Parse Khmer ALT's ``sentence-id<TAB>space-tokenized-text`` format."""
    if split not in DERIVED_SPLITS:
        raise ValueError(f"Unknown split {split!r}; use train, dev, test, or all")

    index = 0
    for line_number, line in enumerate(lines, start=1):
        line = line.rstrip("\r\n")
        if not line:
            continue
        try:
            source_id, tokenized_text = line.split("\t", 1)
        except ValueError as exc:
            raise ValueError(f"Invalid Khmer ALT record on source line {line_number}") from exc
        tokens = tokenized_text.split()
        assigned_split = derived_split("khmer_alt_pos", source_id)
        if split != "all" and assigned_split != split:
            continue
        yield {
            "id": f"khmer_alt_pos:{assigned_split}:{index}",
            "dataset": "khmer_alt_pos",
            "split": assigned_split if split != "all" else "all",
            "tokens": tokens,
            "text": "".join(tokens),
            "metadata": {"source_line": line_number, "source_id": source_id},
        }
        index += 1


def load_khmer_alt(
    split: str = "train",
    path: str | Path | None = None,
    cache_dir: str | Path = "dataset/benchmarks",
) -> Iterator[dict]:
    """Load the tokenized Khmer ALT corpus from a local file or official ZIP."""
    if path:
        with Path(path).open(encoding="utf-8-sig") as handle:
            yield from parse_khmer_alt_lines(handle, split=split)
        return

    archive = Path(cache_dir) / "km-nova.zip"
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(KHMER_ALT_URL, archive)
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open(KHMER_ALT_MEMBER) as raw_handle:
            lines = (line.decode("utf-8-sig") for line in raw_handle)
            yield from parse_khmer_alt_lines(lines, split=split)


def parse_curated_jsonl(lines: Iterable[str], split: str = "all") -> Iterator[dict]:
    """Parse the project-owned, human-reviewed benchmark JSONL format."""

    if split not in CURATED_SPLITS:
        raise ValueError(f"Unknown curated split {split!r}; use dev, test, or all")
    seen_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        required = {"id", "split", "text", "tokens", "category", "source", "review"}
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Curated record on line {line_number} is missing: {sorted(missing)}")
        record_id = str(record["id"])
        if record_id in seen_ids:
            raise ValueError(f"Duplicate curated record id: {record_id}")
        seen_ids.add(record_id)
        record_split = record["split"]
        if record_split not in {"dev", "test"}:
            raise ValueError(f"Invalid curated split on line {line_number}: {record_split!r}")
        if "".join(record["tokens"]) != record["text"]:
            raise ValueError(f"Tokens do not reconstruct text for curated record {record_id}")
        if record["review"].get("status") != "approved":
            continue
        if split != "all" and record_split != split:
            continue
        yield {
            **record,
            "dataset": "khmer_segmenter_curated",
            "metadata": {
                "category": record["category"],
                "source": record["source"],
                "review": record["review"],
            },
        }


def load_curated_benchmark(
    path: str | Path,
    split: str = "all",
) -> Iterator[dict]:
    """Load the redistribution-cleared benchmark maintained by this project."""

    with Path(path).open(encoding="utf-8-sig") as handle:
        yield from parse_curated_jsonl(handle, split=split)


def boundary_offsets(tokens: Iterable[str]) -> set[int]:
    """Return code-point offsets after every token except the final token."""
    token_list = list(tokens)
    offsets = set()
    position = 0
    for token in token_list[:-1]:
        position += len(token)
        offsets.add(position)
    return offsets


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate_records(segmenter, records: Iterable[dict], limit: int | None = None) -> dict:
    """Evaluate a segmenter and return a JSON-serializable report."""
    import time

    normalizer = segmenter.normalizer
    errors = []
    correct = predicted_total = gold_total = exact = unknown_total = token_total = 0
    latency_seconds = 0.0
    count = 0
    dataset_name = None
    split_name = None
    category_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "predicted": 0, "gold": 0, "exact": 0, "sentences": 0}
    )

    for record in records:
        if limit is not None and count >= limit:
            break

        dataset_name = dataset_name or record["dataset"]
        split_name = split_name or record["split"]
        gold_tokens = [normalizer.normalize(token) for token in record["tokens"]]
        text = "".join(gold_tokens)
        start = time.perf_counter()
        predicted_tokens = segmenter.segment(text)
        latency_seconds += time.perf_counter() - start

        predicted_text = "".join(predicted_tokens)
        if predicted_text != text:
            raise ValueError(
                f"Segmenter changed normalized text for {record['id']}: "
                f"{text!r} != {predicted_text!r}"
            )

        gold_boundaries = boundary_offsets(gold_tokens)
        predicted_boundaries = boundary_offsets(predicted_tokens)
        matched = gold_boundaries & predicted_boundaries
        missing = sorted(gold_boundaries - predicted_boundaries)
        extra = sorted(predicted_boundaries - gold_boundaries)

        correct += len(matched)
        predicted_total += len(predicted_boundaries)
        gold_total += len(gold_boundaries)
        is_exact = not missing and not extra
        exact += int(is_exact)
        category = record.get("category") or record.get("metadata", {}).get(
            "category", "uncategorized"
        )
        category_row = category_counts[category]
        category_row["correct"] += len(matched)
        category_row["predicted"] += len(predicted_boundaries)
        category_row["gold"] += len(gold_boundaries)
        category_row["exact"] += int(is_exact)
        category_row["sentences"] += 1

        unknown_tokens = [
            token
            for token in predicted_tokens
            if token not in segmenter.words
            and not segmenter._is_digit(token)
            and not segmenter._is_separator(token)
        ]
        unknown_total += len(unknown_tokens)
        token_total += len(predicted_tokens)

        if not is_exact:
            errors.append(
                {
                    "id": record["id"],
                    "text": text,
                    "gold_tokens": gold_tokens,
                    "pred_tokens": predicted_tokens,
                    "missing_boundaries": missing,
                    "extra_boundaries": extra,
                    "unknown_tokens": unknown_tokens,
                }
            )
        count += 1

    precision = safe_ratio(correct, predicted_total)
    recall = safe_ratio(correct, gold_total)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    categories = {}
    for category, values in sorted(category_counts.items()):
        category_precision = safe_ratio(values["correct"], values["predicted"])
        category_recall = safe_ratio(values["correct"], values["gold"])
        category_f1 = (
            2 * category_precision * category_recall / (category_precision + category_recall)
            if category_precision + category_recall
            else 0.0
        )
        categories[category] = {
            "num_sentences": values["sentences"],
            "boundary_precision": category_precision,
            "boundary_recall": category_recall,
            "boundary_f1": category_f1,
            "exact_sentence_match": safe_ratio(values["exact"], values["sentences"]),
        }
    return {
        "summary": {
            "dataset": dataset_name or "khpos",
            "split": split_name or "train",
            "num_sentences": count,
            "boundary_precision": precision,
            "boundary_recall": recall,
            "boundary_f1": f1,
            "exact_sentence_match": safe_ratio(exact, count),
            "unknown_word_rate": safe_ratio(unknown_total, token_total),
            "avg_latency_ms": safe_ratio(int(latency_seconds * 1_000_000), count) / 1000,
            "total_latency_seconds": latency_seconds,
        },
        "categories": categories,
        "errors": errors,
    }


def write_report(report: dict, output: str | Path) -> None:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
