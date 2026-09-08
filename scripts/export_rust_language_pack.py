#!/usr/bin/env python3
"""Export the canonical Rust KLEX source and compile its KDIC runtime pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.kdict import (
    AUTOCOMPLETE,
    SEGMENT,
    SPELLCHECK,
    SUPPLEMENTAL,
    TYPO_SURFACE,
    KDict,
    compile_klex,
)

DEFAULT_INPUT = PROJECT_ROOT / "port" / "common" / "khmer_dictionary.kdict"
DEFAULT_KLEX = PROJECT_ROOT / "port" / "rust" / "data" / "khmer_dictionary.klex.json"
DEFAULT_KDICT = PROJECT_ROOT / "port" / "rust" / "data" / "khmer_dictionary.kdict"
DEFAULT_MANIFEST = (
    PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data" / "khmer_model_manifest.json"
)
DEFAULT_AUTHOR_CURATED = (
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_author_curated_words.txt"
)
DEFAULT_RAC_DERIVED = (
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_rac_derived_words.txt"
)
DEFAULT_RAC_USAGE = (
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_rac_usage_words.txt"
)
DEFAULT_RAC_PHRASE_EXCLUSIONS = (
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_rac_phrase_exclusions.txt"
)


def _uses(flags: int) -> list[str]:
    names = []
    for flag, name in (
        (SEGMENT, "segmentation"),
        (SPELLCHECK, "spelling"),
        (AUTOCOMPLETE, "autocomplete"),
        (TYPO_SURFACE, "typo"),
        (SUPPLEMENTAL, "supplemental"),
    ):
        if flags & flag:
            names.append(name)
    return names or ["correction_target"]


def export_klex(
    pack: KDict,
    manifest: dict,
    output: Path,
    author_curated_words: set[str] | None = None,
    rac_derived_words: set[str] | None = None,
    rac_usage_words: set[str] | None = None,
    rac_phrase_exclusions: set[str] | None = None,
) -> None:
    source = manifest["source"]
    supplemental = manifest.get("supplemental_source", {})
    author_curated_words = author_curated_words or set()
    rac_derived_words = rac_derived_words or set()
    rac_usage_words = rac_usage_words or set()
    rac_phrase_exclusions = rac_phrase_exclusions or set()
    promoted_words = author_curated_words | rac_derived_words | rac_usage_words
    entries = []
    correction_targets = set(pack.typo_corrections.values())
    for word in sorted(set(pack.words) | promoted_words):
        record = pack.words.get(word)
        is_author_curated = word in author_curated_words
        is_rac_derived = word in rac_derived_words
        is_rac_usage = word in rac_usage_words
        uses = (
            ["spelling"]
            if word in rac_phrase_exclusions
            else
            ["segmentation", "spelling", "autocomplete"]
            if is_author_curated or is_rac_derived or is_rac_usage
            else _uses(record.flags)
        )
        if (
            word in correction_targets
            and (record is None or not record.flags & SPELLCHECK)
            and "correction_target" not in uses
        ):
            uses.append("correction_target")
        entry: dict[str, object] = {
            "word": word,
            "uses": uses,
            "cost": record.cost if record is not None else pack.default_cost,
        }
        correction = pack.typo_corrections.get(word)
        if correction is not None:
            entry["correction"] = correction
            entry["status"] = "approved"
        evidence = list(pack.word_provenance.get(word, []))
        if is_author_curated:
            evidence.append(
                {
                    "source": "khmer-segmenter-author-curated",
                    "review_status": "approved",
                    "note": "Signature term or name selected by the project author",
                }
            )
        if is_rac_derived:
            evidence.append(
                {
                    "source": "rac-derived-component-review",
                    "review_status": "approved",
                    "note": "Reusable component reviewed from a RAC headword phrase",
                }
            )
        if is_rac_usage:
            evidence.append(
                {
                    "source": "rac-definition-example-review",
                    "review_status": "approved",
                    "note": "Standalone word mined from RAC definitions or examples",
                }
            )
        if evidence:
            entry["provenance"] = evidence
        entries.append(entry)

    payload = {
        "version": 1,
        "pack": {
            "id": manifest["model_id"],
            "kind": "bundled_runtime",
            "release": manifest["release"],
            "description": "Canonical Khmer Segmenter Rust language pack",
            "license_notice": source["license_notice"],
        },
        "sources": [
            {
                "id": "rac-khmer-dictionary-2022",
                "title": source["name"],
                "authority": source["authority"],
                "publisher": source["publisher"],
                "url": source["url"],
                "revision": source["revision"],
                "sha256": source["sha256"],
                "license_notice": source["license_notice"],
            },
            {
                "id": "legacy-project-segmentation-dictionary",
                "title": supplemental.get("name", "Supplemental segmentation vocabulary"),
                "policy": supplemental.get("policy", "segmentation only"),
                "spelling_authority": False,
                "license_notice": supplemental.get("license_notice", source["license_notice"]),
            },
            {
                "id": "khmer-segmenter-author-curated",
                "title": "Khmer Segmenter author-curated signature vocabulary",
                "authority": "Sovichea Tep",
                "policy": "segmentation, spelling, and autocomplete",
                "spelling_authority": True,
            },
            {
                "id": "rac-derived-component-review",
                "title": "Reviewed reusable components from RAC headword phrases",
                "authority": "Khmer Segmenter project review",
                "derived_from": "rac-khmer-dictionary-2022",
                "policy": "curated component promotion and phrase segmentation",
                "spelling_authority": True,
            },
            {
                "id": "rac-definition-example-review",
                "title": "Reviewed standalone vocabulary used by RAC in definitions and examples",
                "authority": "Khmer Segmenter project review",
                "derived_from": "rac-khmer-dictionary-2022",
                "policy": "segmentation, spelling, and autocomplete",
                "spelling_authority": True,
            },
        ],
        "cost_model": {
            "default_cost": pack.default_cost,
            "unknown_cost": pack.unknown_cost,
            "generate_aliases": False,
        },
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-klex", type=Path, default=DEFAULT_KLEX)
    parser.add_argument("--output-kdict", type=Path, default=DEFAULT_KDICT)
    parser.add_argument("--author-curated", type=Path, default=DEFAULT_AUTHOR_CURATED)
    parser.add_argument("--rac-derived", type=Path, default=DEFAULT_RAC_DERIVED)
    parser.add_argument("--rac-usage", type=Path, default=DEFAULT_RAC_USAGE)
    parser.add_argument(
        "--rac-phrase-exclusions",
        type=Path,
        default=DEFAULT_RAC_PHRASE_EXCLUSIONS,
    )
    args = parser.parse_args()

    pack = KDict.load(args.input)
    if pack.version != 2:
        parser.error("the canonical Rust language pack must use KDIC v2")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    author_curated_words = {
        line.strip()
        for line in args.author_curated.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }
    rac_derived_words = {
        line.strip()
        for line in args.rac_derived.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }
    rac_usage_words = {
        line.strip()
        for line in args.rac_usage.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }
    rac_phrase_exclusions = {
        line.strip()
        for line in args.rac_phrase_exclusions.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }
    export_klex(
        pack,
        manifest,
        args.output_klex,
        author_curated_words,
        rac_derived_words,
        rac_usage_words,
        rac_phrase_exclusions,
    )
    compile_klex(args.output_klex, args.output_kdict)
    print(f"Exported {len(pack.words)} entries to {args.output_klex}")
    print(f"Compiled Rust runtime pack to {args.output_kdict}")


if __name__ == "__main__":
    main()
