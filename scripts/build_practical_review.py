#!/usr/bin/env python3
"""Build a review table of practical spelling variants.

Each candidate from the Chuon Nath / SBBIC lists is matched to the closest RAC
form by base skeleton and edit cost. A reviewer fills the ``decision`` column:

- ``standard``      : accept the variant itself as a practical spelling
- a Khmer word      : the variant is a typo of that standard form
- blank            : leave it out for now (not a rejection)

The reviewed table is later compiled by the practical-spellings build step.

Requires the pinned sources; run ``python scripts/fetch_sources.py`` first, then
``python scripts/extract_legacy_variants.py``.

Example:
    python scripts/build_practical_review.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.normalization import KhmerNormalizer  # noqa: E402
from khmer_segmenter.orthography import coeng_da_ta_variants  # noqa: E402
from khmer_segmenter.spelling import (  # noqa: E402
    _base_skeleton,
    _orthographic_cluster_count,
    weighted_edits,
)

DATA_DIR = PROJECT_ROOT / "src" / "khmer_segmenter" / "dictionary_data"
LEXICON_DIR = PROJECT_ROOT / "dataset" / "lexicon" / "generated"
BUILD_DIR = PROJECT_ROOT / "build"
DEFAULT_OUTPUT = BUILD_DIR / "practical_variant_review.tsv"


def _known_forms(normalizer: KhmerNormalizer) -> set[str]:
    """Every reviewed spelling form already covered by the model."""

    from extract_legacy_variants import KNOWN_WORD_FILES

    forms: set[str] = set()
    for name in KNOWN_WORD_FILES:
        path = DATA_DIR / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            word = normalizer.normalize(line.strip())
            if word:
                forms.add(word)
                forms.update(coeng_da_ta_variants(word))
    if LEXICON_DIR.is_dir():
        for path in sorted(LEXICON_DIR.glob("*.klex.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for entry in data.get("entries", ()):
                word = normalizer.normalize(str(entry.get("word", "")).strip())
                if word:
                    forms.add(word)
                    forms.update(coeng_da_ta_variants(word))
    return forms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates", type=Path, default=BUILD_DIR / "legacy_variants_candidates.txt"
    )
    parser.add_argument(
        "--frequencies",
        type=Path,
        default=DATA_DIR / "khmer_word_frequencies_chuon.json",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-edit-cost", type=float, default=2.0)
    args = parser.parse_args()

    if not args.candidates.is_file():
        parser.error(
            f"candidates not found: {args.candidates}\n"
            "Run 'python scripts/extract_legacy_variants.py' first."
        )

    normalizer = KhmerNormalizer()
    known = _known_forms(normalizer)
    by_skeleton: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for word in known:
        by_skeleton[_base_skeleton(word)].append(word)
    frequencies = (
        json.loads(args.frequencies.read_text(encoding="utf-8"))
        if args.frequencies.is_file()
        else {}
    )
    candidates = [
        line
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    rows = []
    for candidate in candidates:
        skeleton = _base_skeleton(candidate)
        best = None
        for word in by_skeleton.get(skeleton, ()):
            if abs(len(word) - len(candidate)) > 2:
                continue
            cost, _ = weighted_edits(candidate, word)
            if best is None or cost < best[1]:
                best = (word, cost)
        if best is None or best[1] > args.max_edit_cost:
            continue
        # A bare letter is never a meaningful standard form.
        if _orthographic_cluster_count(best[0]) < 2:
            continue
        rows.append(
            {
                "variant": candidate,
                "likely_standard": best[0],
                "edit_cost": f"{best[1]:.3f}",
                "chuon_freq": frequencies.get(candidate, 0),
                "decision": "",
            }
        )
    rows.sort(
        key=lambda row: (
            row["likely_standard"],
            float(row["edit_cost"]),
            row["variant"],
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["variant", "likely_standard", "edit_cost", "chuon_freq", "decision"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"wrote {args.output}\n"
        f"  rows: {len(rows):,}\n"
        "  decision: 'standard' | a correction word | blank (leave out for now)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
