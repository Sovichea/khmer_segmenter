#!/usr/bin/env python3
"""Export the canonical Rust KLEX source and compile its KDIC runtime pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


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
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_model_manifest.json"
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


def export_klex(pack: KDict, manifest: dict, output: Path) -> None:
    source = manifest["source"]
    supplemental = manifest.get("supplemental_source", {})
    entries = []
    correction_targets = set(pack.typo_corrections.values())
    for word, record in sorted(pack.words.items()):
        uses = _uses(record.flags)
        if word in correction_targets and not record.flags & SPELLCHECK:
            if "correction_target" not in uses:
                uses.append("correction_target")
        entry: dict[str, object] = {
            "word": word,
            "uses": uses,
            "cost": record.cost,
        }
        correction = pack.typo_corrections.get(word)
        if correction is not None:
            entry["correction"] = correction
            entry["status"] = "approved"
        evidence = pack.word_provenance.get(word)
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
                "license_notice": supplemental.get(
                    "license_notice", source["license_notice"]
                ),
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
    args = parser.parse_args()

    pack = KDict.load(args.input)
    if pack.version != 2:
        parser.error("the canonical Rust language pack must use KDIC v2")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    export_klex(pack, manifest, args.output_klex)
    compile_klex(args.output_klex, args.output_kdict)
    print(f"Exported {len(pack.words)} entries to {args.output_klex}")
    print(f"Compiled Rust runtime pack to {args.output_kdict}")


if __name__ == "__main__":
    main()
