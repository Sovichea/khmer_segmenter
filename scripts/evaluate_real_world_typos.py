"""Evaluate the reviewed real-world typo observations without training on them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from khmer_segmenter import KhmerSegmenter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "typos" / "real_world_review.jsonl"


def load_records(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            required = {"id", "typed", "intended", "context", "expectation", "source_id"}
            missing = required - record.keys()
            if missing:
                raise ValueError(f"{path}:{line_number}: missing fields {sorted(missing)}")
            records.append(record)
    return records


def evaluate(
    records: list[dict[str, str]],
    *,
    max_edit_cost: float = 2.0,
    max_suggestions: int = 10,
) -> dict[str, object]:
    segmenter = KhmerSegmenter()
    suggestion_cases = 0
    top_1 = 0
    top_k = 0
    normalization_cases = 0
    normalization_passed = 0
    context_required = 0
    failures: list[dict[str, object]] = []
    top_1_misses: list[dict[str, object]] = []

    for record in records:
        expectation = record["expectation"]
        if expectation == "context_required":
            context_required += 1
            continue
        if expectation == "normalization":
            normalization_cases += 1
            passed = segmenter.is_spelling_valid(record["typed"])
            normalization_passed += int(passed)
            if not passed:
                failures.append({"id": record["id"], "reason": "normalization_rejected"})
            continue

        suggestion_cases += 1
        suggestions = segmenter.suggest_spelling(
            record["typed"],
            max_edit_cost=max_edit_cost,
            max_suggestions=max_suggestions,
        )
        ranked = [suggestion.text for suggestion in suggestions]
        is_top_1 = bool(ranked) and ranked[0] == record["intended"]
        is_top_k = record["intended"] in ranked
        top_1 += int(is_top_1)
        top_k += int(is_top_k)
        if not is_top_1:
            top_1_misses.append(
                {
                    "id": record["id"],
                    "typed": record["typed"],
                    "intended": record["intended"],
                    "top_suggestion": ranked[0] if ranked else None,
                    "intended_rank": ranked.index(record["intended"]) + 1 if is_top_k else None,
                }
            )
        passed = is_top_1 if expectation == "top1" else is_top_k
        if not passed:
            failures.append(
                {
                    "id": record["id"],
                    "typed": record["typed"],
                    "intended": record["intended"],
                    "expectation": expectation,
                    "suggestions": ranked,
                }
            )

    return {
        "benchmark": "reviewed_real_world_typos",
        "warning": "Small diagnostic set; not a representative accuracy benchmark.",
        "records": len(records),
        "suggestion_cases": suggestion_cases,
        "top_1_accuracy": round(top_1 / suggestion_cases, 4) if suggestion_cases else 0.0,
        "top_k_recall": round(top_k / suggestion_cases, 4) if suggestion_cases else 0.0,
        "normalization_cases": normalization_cases,
        "normalization_accuracy": (
            round(normalization_passed / normalization_cases, 4)
            if normalization_cases
            else 0.0
        ),
        "context_required_cases": context_required,
        "top_1_misses": top_1_misses,
        "requirement_failures": failures,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--max-edit-cost", type=float, default=2.0)
    parser.add_argument("--max-suggestions", type=int, default=10)
    args = parser.parse_args()
    result = evaluate(
        load_records(args.dataset),
        max_edit_cost=args.max_edit_cost,
        max_suggestions=args.max_suggestions,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["requirement_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
