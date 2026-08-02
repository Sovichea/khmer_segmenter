#!/usr/bin/env python3
"""Decompose a legacy supplemental dictionary into conservative chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from khmer_segmenter.preparation import (
    DEFAULT_MAX_SUPPLEMENTAL_CLUSTERS,
    decompose_supplemental_words,
    read_words,
    write_words,
)
from khmer_segmenter.spelling import load_approved_typo_corrections


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Break phrase-like legacy supplemental entries into short chunks "
            "while preserving the longest curated dictionary matches."
        )
    )
    parser.add_argument("input", type=Path, help="legacy UTF-8 dictionary, one entry per line")
    parser.add_argument(
        "--curated",
        type=Path,
        default=DATA_DIR / "khmer_dictionary_words.txt",
        help="authoritative segmentation dictionary",
    )
    parser.add_argument(
        "--corrections",
        type=Path,
        default=DATA_DIR / "khmer_typo_corrections.tsv",
        help="reviewed typo-pair TSV",
    )
    parser.add_argument(
        "--spellcheck",
        type=Path,
        default=DATA_DIR / "khmer_spellcheck_words.txt",
        help="additional authoritative forms used as boundaries but not emitted",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "khmer_dictionary_supplemental_words.txt",
    )
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DATA_DIR / "khmer_model_manifest.json",
        help="existing model manifest to update when present",
    )
    parser.add_argument(
        "--max-clusters",
        type=int,
        default=DEFAULT_MAX_SUPPLEMENTAL_CLUSTERS,
    )
    args = parser.parse_args()

    entries, rejected_input = read_words(args.input)
    curated, rejected_curated = read_words(args.curated)
    spellcheck, rejected_spellcheck = read_words(args.spellcheck)
    corrections = load_approved_typo_corrections(args.corrections)
    accepted, decisions = decompose_supplemental_words(
        set(entries),
        set(curated) | set(spellcheck),
        reviewed_typos=set(corrections),
        max_clusters=args.max_clusters,
    )

    write_words(args.output, accepted)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    lines = ["source\tchunk\taccepted\treason"]
    lines.extend(
        "\t".join(
            (
                decision.source,
                decision.chunk,
                str(decision.accepted).lower(),
                decision.reason,
            )
        )
        for decision in decisions
    )
    args.audit.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    if args.manifest.is_file():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        output_bytes = args.output.read_bytes()
        manifest["model_id"] = "rac-2022-layered-v1"
        manifest["supplemental_source"] = {
            "name": "legacy project segmentation dictionary",
            "policy": (
                "decomposed into non-curated Khmer entries of 2 to 4 "
                "orthographic clusters; reviewed typo surfaces retained"
            ),
            "spelling_authority": False,
            "license_notice": (
                "Noncommercial redistribution with attribution; see DATA_LICENSE.md"
            ),
        }
        manifest.setdefault("generation", {})["supplemental_penalty"] = 1.5
        manifest["generation"]["supplemental_frequency"] = (
            "ignored; every supplemental edge uses default_cost plus penalty"
        )
        manifest.setdefault("counts", {})["supplemental_segmentation_words"] = len(
            accepted
        )
        curated_count = manifest["counts"].get("segmentation_words", 0)
        manifest["counts"]["runtime_segmentation_words"] = curated_count + len(accepted)
        manifest.setdefault("files", {})[args.output.name] = {
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
            "bytes": len(output_bytes),
            "records": len(accepted),
        }
        args.manifest.write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            )
        )
    print(
        f"accepted={len(accepted)} decisions={len(decisions)} "
        f"rejected_input={rejected_input} rejected_curated={rejected_curated} "
        f"rejected_spellcheck={rejected_spellcheck}"
    )


if __name__ == "__main__":
    main()
