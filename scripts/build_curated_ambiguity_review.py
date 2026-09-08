"""Build contextual RAC ambiguity and unresolved-span review worksheets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from khmer_segmenter import KhmerSegmenter, __version__


@dataclass(frozen=True)
class Candidate:
    cost: float
    tokens: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("benchmarks/curated/review_300.model.tsv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks/curated"),
    )
    parser.add_argument(
        "--max-cost-delta",
        type=float,
        default=3.5,
        help="Include an RAC alternative this far above the model path",
    )
    parser.add_argument("--max-alternatives", type=int, default=3)
    parser.add_argument("--max-merge-tokens", type=int, default=4)
    return parser.parse_args()


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def k_best_rac_paths(
    text: str,
    segmenter: KhmerSegmenter,
    rac_words: set[str],
    *,
    limit: int,
) -> list[Candidate]:
    """Return low-cost exact RAC paths for one normalized continuous span."""

    paths: list[list[Candidate]] = [[] for _ in range(len(text) + 1)]
    paths[0] = [Candidate(0.0, ())]
    for start in range(len(text)):
        if not paths[start]:
            continue
        end_limit = min(len(text), start + segmenter.max_word_length)
        for end in range(start + 1, end_limit + 1):
            word = text[start:end]
            if word not in rac_words:
                continue
            word_cost = segmenter.get_word_cost(word)
            paths[end].extend(
                Candidate(candidate.cost + word_cost, candidate.tokens + (word,))
                for candidate in paths[start]
            )
            unique = {candidate.tokens: candidate for candidate in paths[end]}
            paths[end] = sorted(
                unique.values(),
                key=lambda candidate: (
                    candidate.cost,
                    len(candidate.tokens),
                    candidate.tokens,
                ),
            )[:limit]
    return paths[-1]


def path_cost(tokens: tuple[str, ...], segmenter: KhmerSegmenter) -> float:
    return sum(segmenter.get_word_cost(token) for token in tokens)


def evidence(tokens: tuple[str, ...], exact_words: set[str]) -> list[dict[str, str]]:
    return [
        {
            "word": token,
            "rac_status": (
                "exact_headword" if token in exact_words else "generated_visual_alias"
            ),
        }
        for token in tokens
    ]


def priority(delta: float) -> str:
    if delta <= 1.0:
        return "high"
    if delta <= 2.0:
        return "medium"
    return "contextual"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()
    if args.max_cost_delta < 0:
        raise ValueError("--max-cost-delta must not be negative")
    if args.max_alternatives < 1:
        raise ValueError("--max-alternatives must be positive")
    if args.max_alternatives > 3:
        raise ValueError("--max-alternatives cannot exceed the three review columns")

    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 300:
        raise ValueError(f"Expected 300 input sentences, found {len(rows)}")

    segmenter = KhmerSegmenter()
    rac_words = set(segmenter._curated_runtime_words)
    exact_words = set(segmenter.official_words)
    ambiguity_rows: list[dict[str, object]] = []
    unresolved_rows: list[dict[str, object]] = []
    sentence_rows: list[dict[str, object]] = []

    for row in rows:
        source_text = row["source_text"]
        normalized = segmenter.normalizer.normalize(source_text)
        if normalized != source_text:
            raise ValueError(
                f"{row['id']}: source_text must be normalized before ambiguity review"
            )
        analyzed = list(segmenter.analyze(source_text))
        model_text = " ".join(token.text for token in analyzed)
        ambiguity_ids: list[str] = []
        unresolved_ids: list[str] = []
        seen_spans: set[tuple[int, int]] = set()

        def add_ambiguity(
            start: int,
            end: int,
            model_tokens: tuple[str, ...],
            alternatives: list[Candidate],
        ) -> None:
            span_key = (start, end)
            if span_key in seen_spans:
                return
            seen_spans.add(span_key)
            model_cost = path_cost(model_tokens, segmenter)
            alternatives = [
                candidate
                for candidate in alternatives
                if candidate.tokens != model_tokens
                and candidate.cost <= model_cost + args.max_cost_delta
            ][: args.max_alternatives]
            if not alternatives:
                return
            case_id = f"amb-{len(ambiguity_rows) + 1:04d}"
            ambiguity_ids.append(case_id)
            best_delta = alternatives[0].cost - model_cost
            all_paths = (Candidate(model_cost, model_tokens), *alternatives)
            alternative_labels = [
                " ".join(candidate.tokens) for candidate in alternatives
            ]
            alternative_labels.extend(
                ["none"] * (args.max_alternatives - len(alternative_labels))
            )
            ambiguity_rows.append(
                {
                    "case_id": case_id,
                    "sentence_id": row["id"],
                    "split": row["split"],
                    "category": row["category"],
                    "source_text": source_text,
                    "model_segmented_text": model_text,
                    "span_start": start,
                    "span_end": end,
                    "span_text": source_text[start:end],
                    "model_choice": " ".join(model_tokens),
                    **{
                        f"alternative_{index + 1}": label
                        for index, label in enumerate(alternative_labels)
                    },
                    "rac_alternatives": compact_json(
                        [list(candidate.tokens) for candidate in alternatives]
                    ),
                    "path_costs": compact_json(
                        [
                            {
                                "tokens": list(candidate.tokens),
                                "cost": round(candidate.cost, 6),
                            }
                            for candidate in all_paths
                        ]
                    ),
                    "rac_evidence": compact_json(
                        [evidence(candidate.tokens, exact_words) for candidate in all_paths]
                    ),
                    "cost_delta": round(best_delta, 6),
                    "priority": priority(best_delta),
                    "reviewer_choice": "pending",
                    "review_status": "draft",
                    "reviewer_notes": "Choose model, alternative_1..3, or uncertain.",
                }
            )

        # Under-segmentation candidates: one RAC model token also has a
        # reasonably competitive path made from two or more RAC entries.
        for token in analyzed:
            if token.source != "rac_2022":
                continue
            model_tokens = (token.text,)
            candidates = k_best_rac_paths(
                token.text,
                segmenter,
                rac_words,
                limit=max(args.max_alternatives * 8, 24),
            )
            alternatives = [
                candidate
                for candidate in candidates
                if len(candidate.tokens) > 1
                # Isolated one-code-point dictionary fragments create large
                # numbers of technically valid but unusable alternatives.
                and all(len(part) > 1 for part in candidate.tokens)
            ]
            add_ambiguity(
                token.start,
                token.end,
                model_tokens,
                alternatives,
            )

        # Over-segmentation candidates: adjacent RAC model tokens concatenate
        # to another RAC entry. This is currently rare but must remain visible.
        for start_index in range(len(analyzed)):
            for size in range(2, args.max_merge_tokens + 1):
                window = analyzed[start_index : start_index + size]
                if len(window) != size or any(
                    token.source != "rac_2022" for token in window
                ):
                    continue
                if any(
                    left.end != right.start for left, right in zip(window, window[1:])
                ):
                    continue
                whole = "".join(token.text for token in window)
                if whole not in rac_words:
                    continue
                model_tokens = tuple(token.text for token in window)
                add_ambiguity(
                    window[0].start,
                    window[-1].end,
                    model_tokens,
                    [Candidate(segmenter.get_word_cost(whole), (whole,))],
                )

        for token in analyzed:
            if token.source not in {"supplemental", "unknown"}:
                continue
            if token.type == "separator" or not any(
                "\u1780" <= character <= "\u17ff" for character in token.text
            ):
                continue
            case_id = f"unres-{len(unresolved_rows) + 1:04d}"
            unresolved_ids.append(case_id)
            unresolved_rows.append(
                {
                    "case_id": case_id,
                    "sentence_id": row["id"],
                    "split": row["split"],
                    "category": row["category"],
                    "source_text": source_text,
                    "model_segmented_text": model_text,
                    "span_start": token.start,
                    "span_end": token.end,
                    "span_text": token.text,
                    "model_source": token.source,
                    "spelling_valid": str(token.spelling_valid).lower(),
                    "reviewed_segmented_text": token.text,
                    "reviewer_classification": "pending",
                    "suggested_rac_entry": "pending",
                    "review_status": "draft",
                    "reviewer_notes": "Classify as name, valid missing term, typo, or noise.",
                }
            )

        if unresolved_ids:
            automatic_status = "has_unresolved_spans"
        elif ambiguity_ids:
            automatic_status = "needs_context_review"
        else:
            automatic_status = "automatically_resolved"
        sentence_rows.append(
            {
                "sentence_id": row["id"],
                "split": row["split"],
                "category": row["category"],
                "source_text": source_text,
                "model_segmented_text": model_text,
                "ambiguity_case_ids": ",".join(ambiguity_ids) or "none",
                "unresolved_case_ids": ",".join(unresolved_ids) or "none",
                "automatic_status": automatic_status,
                "sentence_review_status": "draft",
                "sentence_reviewer_notes": "Confirm naturalness and spelling.",
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    automatic_path = args.output_dir / "automatic_rac_segments.tsv"
    ambiguity_path = args.output_dir / "ambiguous_rac_review.tsv"
    unresolved_path = args.output_dir / "unresolved_spans.tsv"
    write_tsv(automatic_path, sentence_rows, list(sentence_rows[0]))
    write_tsv(ambiguity_path, ambiguity_rows, list(ambiguity_rows[0]))
    write_tsv(unresolved_path, unresolved_rows, list(unresolved_rows[0]))

    manifest_path = segmenter.data_files.model_manifest
    metadata = {
        "segmenter_version": __version__,
        "model_id": segmenter.data_manifest.get("model_id"),
        "model_manifest_sha256": sha256(manifest_path),
        "input": str(args.input),
        "sentences": len(rows),
        "ambiguity_cases": len(ambiguity_rows),
        "unresolved_cases": len(unresolved_rows),
        "max_cost_delta": args.max_cost_delta,
        "max_alternatives": args.max_alternatives,
        "max_merge_tokens": args.max_merge_tokens,
        "single_codepoint_alternatives_excluded": True,
    }
    metadata_path = args.output_dir / "ambiguity_review.meta.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {len(sentence_rows)} sentence summaries to {automatic_path}")
    print(f"Wrote {len(ambiguity_rows)} contextual decisions to {ambiguity_path}")
    print(f"Wrote {len(unresolved_rows)} unresolved spans to {unresolved_path}")


if __name__ == "__main__":
    main()
