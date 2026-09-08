"""Compile the human review sheet into the curated benchmark JSONL format."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


EXPECTED_CATEGORIES = {
    "News and formal prose": 60,
    "Conversational text": 40,
    "Public administration": 40,
    "Education": 35,
    "Literary and religious text": 35,
    "Technical text": 30,
    "Names and locations": 25,
    "Repetition forms and numerals": 20,
    "Valid but difficult Unicode": 15,
}
EXPECTED_SPLITS = {"dev": 200, "test": 100}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("benchmarks/curated/review_300.model.tsv"),
        help="UTF-8 TSV in which spaces in segmented_text are token boundaries",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/curated/benchmark.draft.jsonl"),
    )
    parser.add_argument("--primary-reviewer", default="unassigned")
    parser.add_argument("--secondary-reviewer")
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Reject the sheet unless every row is approved",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {
            "id",
            "split",
            "category",
            "segmented_text",
            "review_status",
            "reviewer_notes",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"Missing TSV columns: {', '.join(missing)}")
        return list(reader)


def validate_rows(rows: list[dict[str, str]], require_approved: bool) -> None:
    if len(rows) != 300:
        raise ValueError(f"Expected 300 rows, found {len(rows)}")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
        raise ValueError(f"Duplicate IDs: {', '.join(duplicates)}")

    category_counts = Counter(row["category"] for row in rows)
    if dict(category_counts) != EXPECTED_CATEGORIES:
        raise ValueError(f"Category counts do not match release quotas: {category_counts}")
    split_counts = Counter(row["split"] for row in rows)
    if dict(split_counts) != EXPECTED_SPLITS:
        raise ValueError(f"Split counts do not match release quotas: {split_counts}")

    for row in rows:
        tokens = row["segmented_text"].split()
        if not tokens:
            raise ValueError(f"{row['id']}: segmented_text is empty")
        reconstructed = "".join(tokens)
        source_text = row.get("source_text")
        if source_text and reconstructed != source_text:
            raise ValueError(
                f"{row['id']}: reviewed boundaries do not reconstruct source_text"
            )
        model_segmented = row.get("model_segmented_text")
        if source_text and model_segmented and "".join(model_segmented.split()) != source_text:
            raise ValueError(
                f"{row['id']}: model boundaries do not reconstruct source_text"
            )
        if any(character in row["segmented_text"] for character in ("\u200b", "\u200c")):
            raise ValueError(f"{row['id']}: remove ZWSP/ZWNJ before review")
        if row["review_status"] not in {"draft", "approved", "rejected"}:
            raise ValueError(f"{row['id']}: invalid review_status")
        if require_approved and row["review_status"] != "approved":
            raise ValueError(f"{row['id']}: is not approved")


def build_record(
    row: dict[str, str], primary_reviewer: str, secondary_reviewer: str | None
) -> dict[str, object]:
    tokens = row["segmented_text"].split()
    return {
        "id": row["id"],
        "split": row["split"],
        "text": "".join(tokens),
        "tokens": tokens,
        "category": row["category"],
        "source": {
            "title": "Project-authored Khmer segmentation benchmark sentences",
            "url": "project-authored",
            "license": "CC0-1.0",
            "attribution": "Khmer Segmenter contributors",
        },
        "review": {
            "status": row["review_status"],
            "primary": primary_reviewer,
            "secondary": secondary_reviewer,
            "adjudication_notes": row["reviewer_notes"],
        },
    }


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    validate_rows(rows, args.require_approved)
    if args.require_approved and args.primary_reviewer == "unassigned":
        raise ValueError("Set --primary-reviewer when compiling approved records")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            record = build_record(row, args.primary_reviewer, args.secondary_reviewer)
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    print(f"Wrote {len(rows)} records to {args.output}")


if __name__ == "__main__":
    main()
