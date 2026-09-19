#!/usr/bin/env python3
"""Derive word frequencies from the Chuon Nath Dictionary definitions.

Each Chuon Nath definition is pre-tokenized with ``<"id">`` annotations that
reference the dictionary's own entry ids, so word counts can be read directly
without re-segmenting the text. This gives a second frequency source that can be
blended with the RAC-derived model.

Requires the pinned source; run ``python scripts/fetch_sources.py`` first.

Example:
    python scripts/build_chuon_frequencies.py
    python scripts/build_chuon_frequencies.py \
        --rac-frequencies src/khmer_segmenter/dictionary_data/khmer_word_frequencies.json \
        --weight 0.3 --blended build/khmer_word_frequencies_chuon.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.normalization import KhmerNormalizer  # noqa: E402

DEFAULT_SOURCE = PROJECT_ROOT / "dataset" / "khmer-dict-spice" / "kh_dictionary.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "chuon_frequencies.json"
_ANNOTATION = re.compile(r'<"(\d+)">')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rac-frequencies", type=Path)
    parser.add_argument("--weight", type=float, default=0.3)
    parser.add_argument("--blended", type=Path)
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error(
            f"Chuon Nath dictionary not found: {args.source}\n"
            "Run 'python scripts/fetch_sources.py' to download the pinned source."
        )

    normalizer = KhmerNormalizer()
    ids: dict[int, str] = {}
    counts: Counter[str] = Counter()
    with args.source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    for row in rows:
        raw_id = (row.get("_id") or "").strip()
        word = normalizer.normalize((row.get("word") or "").strip())
        if raw_id.isdigit() and word:
            ids[int(raw_id)] = word
    for row in rows:
        definition = row.get("definition") or ""
        for match in _ANNOTATION.finditer(definition):
            word = ids.get(int(match.group(1)))
            if word:
                counts[word] += 1

    ordered = dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.output}\n"
        f"  definitions: {len(rows):,}\n"
        f"  annotated tokens: {sum(counts.values()):,}\n"
        f"  distinct words: {len(counts):,}"
    )

    if args.blended is not None:
        if args.rac_frequencies is None or not args.rac_frequencies.is_file():
            parser.error("--blended requires --rac-frequencies pointing to a JSON file")
        rac = json.loads(args.rac_frequencies.read_text(encoding="utf-8"))
        blended: dict[str, int] = {}
        for word in set(rac) | set(counts):
            value = float(rac.get(word, 0)) + args.weight * float(counts.get(word, 0))
            if value > 0:
                blended[word] = max(1, int(round(value)))
        ordered_blended = dict(
            sorted(blended.items(), key=lambda item: (-item[1], item[0]))
        )
        args.blended.parent.mkdir(parents=True, exist_ok=True)
        args.blended.write_text(
            json.dumps(ordered_blended, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.blended} (weight {args.weight})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
