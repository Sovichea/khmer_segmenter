#!/usr/bin/env python3
"""Build an experimental inclusive KDIC with blended corpus frequencies."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from khmer_segmenter.kdict import (
    AUTOCOMPLETE,
    SEGMENT,
    SPELLCHECK,
    SUPPLEMENTAL,
    TYPO_SURFACE,
    KDict,
    compile_klex,
)

USES = (
    (SEGMENT, "segmentation"),
    (SPELLCHECK, "spelling"),
    (AUTOCOMPLETE, "autocomplete"),
    (TYPO_SURFACE, "typo"),
    (SUPPLEMENTAL, "supplemental"),
)


def merge_sources(*packs: KDict) -> list[dict]:
    by_id: dict[str, dict] = {}
    for pack in packs:
        for source in pack.sources:
            source_id = source.get("id")
            if source_id in by_id and by_id[source_id] != source:
                raise ValueError(f"conflicting source metadata for {source_id!r}")
            by_id[source_id] = source
    return [by_id[key] for key in sorted(by_id)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interpolate curated KDIC costs with community corpus frequencies"
    )
    parser.add_argument("--base-kdict", type=Path, required=True)
    parser.add_argument("--community-kdict", type=Path, required=True)
    parser.add_argument("--corpus-frequencies", type=Path, required=True)
    parser.add_argument("--output-klex", type=Path, required=True)
    parser.add_argument("--output-kdict", type=Path, required=True)
    parser.add_argument("--corpus-weight", type=float, default=0.2)
    args = parser.parse_args()
    if not 0.0 < args.corpus_weight < 1.0:
        raise ValueError("--corpus-weight must be between zero and one")

    base = KDict.load(args.base_kdict)
    community = KDict.load(args.community_kdict)
    observed_value = json.loads(args.corpus_frequencies.read_text(encoding="utf-8"))
    observed = {
        word: float(count)
        for word, count in observed_value.items()
        if isinstance(word, str) and isinstance(count, (int, float)) and count > 0
    }

    # A standalone KLEX compilation uses a frequency floor of one. Recover the
    # community evidence counts from its costs so the binary pack remains the
    # single input used by applications.
    community_total = 10.0**community.default_cost
    for word, record in community.words.items():
        if record.flags & SEGMENT:
            observed[word] = max(observed.get(word, 0.0), community_total * 10**-record.cost)

    prior_weights = {
        word: 10.0**-record.cost for word, record in base.words.items() if record.flags & SEGMENT
    }
    for word, record in community.words.items():
        if record.flags & SEGMENT and word not in prior_weights:
            effective_cost = max(
                0.0,
                base.default_cost + 1.5 + (record.cost - community.default_cost),
            )
            prior_weights[word] = 10.0**-effective_cost
    base_total = sum(prior_weights.values())
    corpus_total = sum(observed.values())
    if not base_total or not corpus_total:
        raise ValueError("base and corpus frequency models must not be empty")

    words = set(base.words) | set(community.words)
    alpha = args.corpus_weight
    # Keep the curated model's absolute cost scale. Re-normalizing its weights
    # to one would add a constant to every token, which is not neutral in a
    # Viterbi path: it changes the preference between one long token and two
    # short tokens even when their relative lexical evidence is unchanged.
    blended_weights = {
        word: (1.0 - alpha) * prior_weights.get(word, 0.0)
        + alpha * base_total * observed.get(word, 0.0) / corpus_total
        for word in words
    }
    default_cost = base.default_cost
    unknown_cost = base.unknown_cost

    corrections = dict(base.typo_corrections)
    corrections.update(community.typo_corrections)
    correction_targets = set(corrections.values())
    entries = []
    provenance = {
        **base.word_provenance,
        **community.word_provenance,
    }
    for word in sorted(words | set(corrections.values())):
        base_record = base.words.get(word)
        community_record = community.words.get(word)
        flags = (base_record.flags if base_record else 0) | (
            community_record.flags if community_record else 0
        )
        uses = [name for bit, name in USES if flags & bit]
        if word in correction_targets and not flags & SPELLCHECK:
            uses.append("correction_target")
        if not uses:
            uses.append("correction_target")
        record = {
            "word": word,
            "uses": uses,
            "cost": (
                -math.log10(blended_weights[word])
                if blended_weights.get(word, 0.0) > 0
                else default_cost
            ),
        }
        if word in corrections:
            record["correction"] = corrections[word]
        if word in provenance:
            record["provenance"] = provenance[word]
        entries.append(record)

    source = {
        "version": 1,
        "pack": {
            "id": "inclusive-corpus-blend-v1",
            "kind": "experimental_inclusive_model",
            "corpus_weight": alpha,
            "spelling_policy": "flags_preserved_from_source_packs",
        },
        "sources": merge_sources(base, community),
        "cost_model": {
            "default_cost": default_cost,
            "unknown_cost": unknown_cost,
            "generate_aliases": False,
        },
        "entries": entries,
    }
    args.output_klex.parent.mkdir(parents=True, exist_ok=True)
    args.output_klex.write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    compile_klex(args.output_klex, args.output_kdict)
    print(
        f"words={len(entries)} observed={len(observed)} corpus_weight={alpha} "
        f"default_cost={default_cost:.4f}"
    )


if __name__ == "__main__":
    main()
