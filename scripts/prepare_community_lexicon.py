#!/usr/bin/env python3
"""Compile reviewed corpus candidates into a segmentation-only KLEX pack.

The corpus discovers forms and supplies frequency evidence.  It never grants
spelling validity: only explicit review decisions are emitted, and emitted
entries carry SEGMENT + SUPPLEMENTAL uses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from khmer_segmenter.kdict import KDict
from khmer_segmenter.normalization import KhmerNormalizer

DATASET_ID = "Panhapich/khmer-text-corpus"
DATASET_URL = "https://huggingface.co/datasets/Panhapich/khmer-text-corpus"
DATASET_REVISION = "e42e1dd0d77836f1874ad14e83f4e291e5bb0a01"
RAW_SHA256 = "95cca2f8542f40596c69e5b08f6ec579ff7f01caa4f713db2d15681884b4ddce"


def read_jsonl(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            word = record.get("word")
            if not isinstance(word, str) or not word:
                raise ValueError(f"{path}:{line_number}: candidate requires word")
            records[word] = record
    return records


def read_review(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list):
        raise TypeError("community review must be a JSON array")
    return value


def is_khmer_word(word: str) -> bool:
    return (
        bool(word)
        and not any(char.isspace() for char in word)
        and all("\u1780" <= char <= "\u17d3" or char == "\u17dd" for char in word)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile approved corpus discoveries as segmentation-only KLEX"
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--base-kdict", type=Path)
    parser.add_argument("--raw-corpus", type=Path)
    args = parser.parse_args()

    if args.raw_corpus and sha256(args.raw_corpus) != RAW_SHA256:
        raise ValueError("raw corpus SHA-256 does not match the pinned dataset revision")

    candidates = read_jsonl(args.candidates)
    review = read_review(args.review)
    known = set(KDict.load(args.base_kdict).words) if args.base_kdict else set()
    normalizer = KhmerNormalizer()
    approved: dict[str, dict] = {}
    seen: set[str] = set()
    status_counts: dict[str, int] = {}

    for index, decision in enumerate(review, 1):
        if not isinstance(decision, dict):
            raise TypeError(f"review item {index} must be an object")
        original = decision.get("candidate")
        status = decision.get("status")
        word = normalizer.normalize(str(decision.get("word") or original or ""))
        if not isinstance(original, str) or original not in candidates:
            raise ValueError(f"review item {index} references an unknown candidate")
        if status not in {"approved", "rejected", "pending"}:
            raise ValueError(f"review item {index} has invalid status {status!r}")
        if original in seen:
            raise ValueError(f"duplicate review candidate {original!r}")
        seen.add(original)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "approved":
            continue
        if not is_khmer_word(word):
            raise ValueError(f"approved community word is not lexical Khmer: {word!r}")
        if word in known:
            raise ValueError(f"approved community word already exists in base: {word!r}")
        evidence = candidates[original]
        frequency = max(
            int(evidence.get("external_boundary_count", 0)),
            int(evidence.get("segmenter_unknown_count", 0)),
            1,
        )
        previous = approved.get(word)
        record = {
            "word": word,
            "uses": ["segmentation", "supplemental"],
            "frequency": frequency,
            "provenance": [
                {
                    "source": "panhapich-khmer-text-corpus",
                    "candidate": original,
                    "category": decision.get("category", "community_word"),
                    "review": "approved_ai_assisted_contextual_curation",
                    "occurrences": frequency,
                }
            ],
        }
        if previous is None or frequency > previous["frequency"]:
            approved[word] = record

    output = {
        "version": 1,
        "pack": {
            "id": "panhapich-community-v1",
            "kind": "community_evidence",
            "maturity": "pilot",
            "release": "0.2",
            "policy": "segmentation_only",
            "curation": "AI-assisted conservative contextual review of corpus candidates",
            "reviewed_entries": len(approved),
        },
        "sources": [
            {
                "id": "panhapich-khmer-text-corpus",
                "title": "Khmer Text Corpus",
                "publisher": "Panhapich",
                "dataset": DATASET_ID,
                "url": DATASET_URL,
                "revision": DATASET_REVISION,
                "raw_sha256": RAW_SHA256,
                "license": "other (inherited source licenses require verification)",
            }
        ],
        "entries": sorted(approved.values(), key=lambda item: item["word"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        by_category: dict[str, list[str]] = {}
        for decision in review:
            if decision.get("status") == "approved":
                category = str(decision.get("category", "community_word"))
                word = normalizer.normalize(
                    str(decision.get("word") or decision.get("candidate") or "")
                )
                by_category.setdefault(category, []).append(word)
        category_sections = "\n".join(
            f"## {category.replace('_', ' ').title()}\n\n"
            + ", ".join(f"`{word}`" for word in sorted(words))
            + "\n"
            for category, words in sorted(by_category.items())
        )
        args.report.write_text(
            "# Community corpus curation\n\n"
            f"- Dataset revision: `{DATASET_REVISION}`\n"
            f"- Candidate records: {len(candidates):,}\n"
            f"- Reviewed decisions: {len(review):,}\n"
            f"- Approved segmentation-only words: {len(approved):,}\n"
            f"- Rejected: {status_counts.get('rejected', 0):,}\n"
            f"- Pending: {status_counts.get('pending', 0):,}\n\n"
            "Corpus frequency affects segmentation ranking only. It does not "
            "make an entry valid for spellcheck or autocomplete.\n\n" + category_sections,
            encoding="utf-8",
        )
    print(f"candidates={len(candidates)} reviewed={len(review)} approved={len(approved)}")


if __name__ == "__main__":
    main()
