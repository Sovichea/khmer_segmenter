#!/usr/bin/env python3
"""Validate the canonical typo-pair TSV and synchronize the Rust copy."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT / "src" / "khmer_segmenter" / "dictionary_data" / "khmer_typo_corrections.tsv"
)
DEFAULT_RUST_DESTINATION = ROOT / "port" / "rust" / "data" / "khmer_typo_corrections.tsv"
REQUIRED_COLUMNS = {
    "id",
    "status",
    "typed",
    "correction",
    "expectation",
    "source_id",
    "note",
}
VALID_STATUSES = {"approved", "pending", "rejected"}


def validate(path: Path) -> dict[str, int]:
    ids: set[str] = set()
    approved_typed: dict[str, str] = {}
    counts = {status: 0 for status in VALID_STATUSES}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError(f"unexpected typo correction columns: {reader.fieldnames}")
        for line_number, row in enumerate(reader, start=2):
            identifier = row["id"].strip()
            status = row["status"].strip()
            typed = row["typed"].strip()
            correction = row["correction"].strip()
            if not identifier or identifier in ids:
                raise ValueError(f"duplicate or empty id at line {line_number}: {identifier!r}")
            if status not in VALID_STATUSES:
                raise ValueError(f"invalid status at line {line_number}: {status!r}")
            if not typed or not correction or typed == correction:
                raise ValueError(f"invalid correction pair at line {line_number}")
            if status == "approved":
                previous = approved_typed.get(typed)
                if previous is not None and previous != correction:
                    raise ValueError(f"conflicting approved correction for {typed!r}")
                approved_typed[typed] = correction
            ids.add(identifier)
            counts[status] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--rust-destination", type=Path, default=DEFAULT_RUST_DESTINATION)
    parser.add_argument("--check", action="store_true", help="validate and verify sync only")
    args = parser.parse_args()

    counts = validate(args.source)
    if args.check:
        if not args.rust_destination.is_file():
            raise FileNotFoundError(args.rust_destination)
        if args.source.read_bytes() != args.rust_destination.read_bytes():
            raise ValueError("Rust typo correction data is out of sync")
    else:
        args.rust_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source, args.rust_destination)
    print(" ".join(f"{status}={counts[status]}" for status in sorted(counts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
