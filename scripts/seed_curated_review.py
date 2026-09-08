"""Seed the curated review sheet with the current segmenter's boundaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from khmer_segmenter import KhmerSegmenter, __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("benchmarks/curated/review_300.tsv"),
        help="Original candidate worksheet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/curated/review_300.model.tsv"),
        help="New worksheet seeded with model boundaries",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 300:
        raise ValueError(f"Expected 300 candidates, found {len(rows)}")

    segmenter = KhmerSegmenter()
    fieldnames = [
        "id",
        "split",
        "category",
        "source_text",
        "model_segmented_text",
        "segmented_text",
        "review_status",
        "reviewer_notes",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            previous = row["segmented_text"]
            source_text = row.get("source_text") or "".join(previous.split())
            model_segmented = " ".join(segmenter.segment(source_text))
            writer.writerow(
                {
                    "id": row["id"],
                    "split": row["split"],
                    "category": row["category"],
                    "source_text": source_text,
                    "model_segmented_text": model_segmented,
                    "segmented_text": model_segmented,
                    "review_status": "draft",
                    "reviewer_notes": "Pending review of Khmer Segmenter output.",
                }
            )

    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "khmer_segmenter"
        / "dictionary_data"
        / "khmer_model_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = {
        "segmenter_version": __version__,
        "model_id": manifest.get("model_id"),
        "model_manifest_sha256": sha256(manifest_path),
        "source_revision": manifest.get("source", {}).get("revision"),
        "records": len(rows),
        "review_column": "segmented_text",
        "immutable_baseline_column": "model_segmented_text",
    }
    metadata_path = args.output.with_suffix(".meta.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {len(rows)} model-seeded records to {args.output}")
    print(f"Wrote model identity to {metadata_path}")


if __name__ == "__main__":
    main()
