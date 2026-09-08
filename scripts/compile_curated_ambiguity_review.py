"""Apply contextual review decisions and compile the curated benchmark."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("benchmarks/curated")
    parser.add_argument("--sentences", type=Path, default=root / "automatic_rac_segments.tsv")
    parser.add_argument("--ambiguities", type=Path, default=root / "ambiguous_rac_review.tsv")
    parser.add_argument("--unresolved", type=Path, default=root / "unresolved_spans.tsv")
    parser.add_argument("--output", type=Path, default=root / "benchmark.draft.jsonl")
    parser.add_argument("--primary-reviewer", default="unassigned")
    parser.add_argument("--secondary-reviewer")
    parser.add_argument("--require-approved", action="store_true")
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def initial_boundaries(segmented_text: str) -> set[int]:
    boundaries: set[int] = set()
    offset = 0
    tokens = segmented_text.split()
    for token in tokens[:-1]:
        offset += len(token)
        boundaries.add(offset)
    return boundaries


def apply_span_tokens(
    boundaries: set[int], start: int, end: int, segmented_text: str
) -> None:
    tokens = segmented_text.split()
    if not tokens or "".join(tokens) == "":
        raise ValueError("reviewed segmented text must not be empty")
    boundaries.difference_update(boundary for boundary in boundaries if start < boundary < end)
    offset = start
    for token in tokens[:-1]:
        offset += len(token)
        if offset >= end:
            raise ValueError("reviewed token boundaries escape their source span")
        boundaries.add(offset)


def tokens_from_boundaries(text: str, boundaries: set[int]) -> list[str]:
    points = [0, *sorted(boundary for boundary in boundaries if 0 < boundary < len(text)), len(text)]
    return [text[start:end] for start, end in zip(points, points[1:])]


def selected_ambiguity(row: dict[str, str], require_approved: bool) -> str:
    if require_approved and row["review_status"] != "approved":
        raise ValueError(f"{row['case_id']}: contextual decision is not approved")
    choice = row["reviewer_choice"]
    if choice == "model" or (not require_approved and choice in {"", "pending"}):
        return row["model_choice"]
    if choice == "uncertain":
        if require_approved:
            raise ValueError(f"{row['case_id']}: contextual decision remains uncertain")
        return row["model_choice"]
    if choice in {"alternative_1", "alternative_2", "alternative_3"}:
        selected = row.get(choice, "none")
        if selected in {"", "none"}:
            raise ValueError(f"{row['case_id']}: selected unavailable {choice}")
        return selected
    raise ValueError(f"{row['case_id']}: invalid reviewer_choice {choice!r}")


def main() -> None:
    args = parse_args()
    sentences = read_tsv(args.sentences)
    ambiguities = read_tsv(args.ambiguities)
    unresolved = read_tsv(args.unresolved)
    if len(sentences) != 300:
        raise ValueError(f"Expected 300 sentence summaries, found {len(sentences)}")
    if args.require_approved and args.primary_reviewer == "unassigned":
        raise ValueError("Set --primary-reviewer for an approved benchmark")

    ambiguities_by_sentence: dict[str, list[dict[str, str]]] = defaultdict(list)
    unresolved_by_sentence: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ambiguities:
        ambiguities_by_sentence[row["sentence_id"]].append(row)
    for row in unresolved:
        unresolved_by_sentence[row["sentence_id"]].append(row)

    records: list[dict[str, object]] = []
    for sentence in sentences:
        sentence_id = sentence["sentence_id"]
        text = sentence["source_text"]
        boundaries = initial_boundaries(sentence["model_segmented_text"])
        all_approved = sentence["sentence_review_status"] == "approved"
        if args.require_approved and not all_approved:
            raise ValueError(f"{sentence_id}: sentence naturalness is not approved")

        spans: list[tuple[int, int, str]] = []
        for row in ambiguities_by_sentence[sentence_id]:
            start, end = int(row["span_start"]), int(row["span_end"])
            selected = selected_ambiguity(row, args.require_approved)
            if "".join(selected.split()) != text[start:end]:
                raise ValueError(f"{row['case_id']}: choice does not reconstruct its span")
            spans.append((start, end, row["case_id"]))
            apply_span_tokens(boundaries, start, end, selected)
            all_approved &= row["review_status"] == "approved" and row[
                "reviewer_choice"
            ] != "uncertain"

        for row in unresolved_by_sentence[sentence_id]:
            start, end = int(row["span_start"]), int(row["span_end"])
            reviewed = row["reviewed_segmented_text"]
            if "".join(reviewed.split()) != text[start:end]:
                raise ValueError(f"{row['case_id']}: reviewed text does not reconstruct span")
            classification = row["reviewer_classification"]
            if args.require_approved:
                if row["review_status"] != "approved":
                    raise ValueError(f"{row['case_id']}: unresolved classification is not approved")
                if classification not in {"name", "valid_missing_term"}:
                    raise ValueError(
                        f"{row['case_id']}: replace typo/noise sentences before release"
                    )
            spans.append((start, end, row["case_id"]))
            apply_span_tokens(boundaries, start, end, reviewed)
            all_approved &= row["review_status"] == "approved" and classification in {
                "name",
                "valid_missing_term",
            }

        for index, (start, end, case_id) in enumerate(sorted(spans)):
            for other_start, other_end, other_id in sorted(spans)[index + 1 :]:
                if other_start >= end:
                    break
                if start < other_end and other_start < end:
                    raise ValueError(f"Overlapping review cases: {case_id} and {other_id}")

        tokens = tokens_from_boundaries(text, boundaries)
        if "".join(tokens) != text:
            raise ValueError(f"{sentence_id}: compiled tokens do not reconstruct text")
        notes = sentence["sentence_reviewer_notes"]
        records.append(
            {
                "id": sentence_id,
                "split": sentence["split"],
                "text": text,
                "tokens": tokens,
                "category": sentence["category"],
                "source": {
                    "title": "Project-authored Khmer segmentation benchmark sentences",
                    "url": "project-authored",
                    "license": "CC0-1.0",
                    "attribution": "Khmer Segmenter contributors",
                },
                "review": {
                    "status": "approved" if all_approved else "draft",
                    "primary": args.primary_reviewer,
                    "secondary": args.secondary_reviewer,
                    "adjudication_notes": notes,
                },
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    print(f"Wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
