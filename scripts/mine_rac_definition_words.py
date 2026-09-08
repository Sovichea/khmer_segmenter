#!/usr/bin/env python3
"""Mine possible standalone words used inside RAC definitions and examples.

RAC headwords remain the lexical authority. This script finds Khmer spans that
the RAC-only segmentation lexicon cannot explain, records where RAC itself uses
them, and optionally attaches independent counts from the community corpus
candidate cache. Its output is a review queue, never an automatically accepted
word list.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.normalization import KhmerNormalizer

KHMER_RUN = re.compile(r"[\u1780-\u17d3\u17dd]+")
KHMER_BASE = re.compile(r"[\u1780-\u17b3]")
DEFAULT_RAC = ROOT / "dataset" / "RAC-Khmer-Dict-2022.csv"
DEFAULT_DICTIONARY = (
    ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_official_2022_words.txt"
)
DEFAULT_COMMUNITY = (
    ROOT
    / "dataset"
    / "community"
    / "Panhapich-khmer-text-corpus"
    / "community_candidates.jsonl"
)


@dataclass
class Candidate:
    definition_occurrences: int = 0
    example_occurrences: int = 0
    isolated_occurrences: int = 0
    row_ids: set[str] = field(default_factory=set)
    contexts: list[dict[str, str]] = field(default_factory=list)
    community_unknown_count: int = 0
    community_boundary_count: int = 0
    discovery: set[str] = field(default_factory=set)
    field_rows: set[tuple[str, str]] = field(default_factory=set)

    @property
    def occurrences(self) -> int:
        return self.definition_occurrences + self.example_occurrences


def read_rac(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"t_id", "t_main", "t_subword", "t_pos", "t_exp", "t_exam"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"RAC CSV is missing columns: {sorted(missing)}")
        return list(reader)


def clean_explicit_forms(
    rows: list[dict[str, str]], normalizer: KhmerNormalizer
) -> set[str]:
    result: set[str] = set()
    for row in rows:
        for column in ("t_main", "t_subword"):
            word = normalizer.normalize((row.get(column) or "").strip())
            if (
                word
                and not any(character.isspace() for character in word)
                and all(
                    "\u1780" <= character <= "\u17d3" or character == "\u17dd"
                    for character in word
                )
                and KHMER_BASE.search(word)
            ):
                result.add(word)
            else:
                # RAC frequently stores interjection punctuation as part of a
                # headword (for example "ហឺយ!"). Treat a single Khmer run
                # wrapped only in punctuation as the same explicit form.
                runs = KHMER_RUN.findall(word)
                outside = KHMER_RUN.sub("", word)
                if (
                    len(runs) == 1
                    and runs[0]
                    and not any(character.isspace() for character in word)
                    and not any(
                        "\u1780" <= character <= "\u17d3" or character == "\u17dd"
                        for character in outside
                    )
                ):
                    result.add(runs[0])
    return result


def cluster_count(text: str) -> int:
    count = 0
    previous = ""
    for character in text:
        if KHMER_BASE.fullmatch(character) and previous != "\u17d2":
            count += 1
        previous = character
    return count


def plausible(word: str, max_clusters: int) -> bool:
    if not word or word == "ៗ" or not KHMER_BASE.search(word):
        return False
    if not all(
        "\u1780" <= character <= "\u17d3" or character == "\u17dd"
        for character in word
    ):
        return False
    if word[0] >= "\u17b4" or word.startswith("\u17d2"):
        return False
    clusters = cluster_count(word)
    return 1 <= clusters <= max_clusters and len(word) <= 48


def excerpt(text: str, word: str, radius: int = 42) -> str:
    start = text.find(word)
    if start < 0:
        return text[: radius * 2]
    left = max(0, start - radius)
    right = min(len(text), start + len(word) + radius)
    return f"{text[left:start]}[{word}]{text[start + len(word):right]}".strip()


def load_community_counts(path: Path | None) -> dict[str, tuple[int, int]]:
    if path is None or not path.is_file():
        return {}
    counts: dict[str, tuple[int, int]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            word = record.get("word")
            if word:
                counts[word] = (
                    int(record.get("segmenter_unknown_count", 0)),
                    int(record.get("external_boundary_count", 0)),
                )
    return counts


def build_trie(words: set[str]) -> dict:
    root: dict = {}
    for word in words:
        node = root
        for character in word:
            node = node.setdefault(character, {})
        node.setdefault("", []).append(word)
    return root


def trie_matches(text: str, trie: dict):
    for start in range(len(text)):
        node = trie
        for index in range(start, len(text)):
            node = node.get(text[index])
            if node is None:
                break
            for word in node.get("", ()):
                yield start, index + 1, word


def maximal_trie_matches(text: str, trie: dict):
    """Yield longest non-overlapping corpus candidates.

    Without maximal matching, every suffix and internal syllable of a long
    corpus token becomes apparent evidence. Explicit RAC forms are absent from
    the trie, so a missing component inside an RAC phrase can still surface.
    """

    matches = list(trie_matches(text, trie))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    cursor = 0
    index = 0
    while index < len(matches):
        start = matches[index][0]
        same_start = []
        while index < len(matches) and matches[index][0] == start:
            same_start.append(matches[index])
            index += 1
        if start < cursor:
            continue
        best = same_start[0]
        yield best
        cursor = best[1]


def mine_corpus_boundaries_in_rac(
    rows: list[dict[str, str]],
    candidates: dict[str, Candidate],
    community: dict[str, tuple[int, int]],
    explicit_forms: set[str],
    *,
    max_clusters: int,
    min_community_boundaries: int,
) -> None:
    """Find complete corpus-boundary candidates used verbatim by RAC."""

    eligible = {
        word
        for word, (unknown_count, boundary_count) in community.items()
        if word not in explicit_forms
        and plausible(word, max_clusters)
        and boundary_count >= min_community_boundaries
    }
    trie = build_trie(eligible)
    normalizer = KhmerNormalizer()
    seen_occurrences: set[tuple[str, str, str]] = set()
    for row in rows:
        row_id = (row.get("t_id") or "").strip()
        headword = normalizer.normalize(
            (row.get("t_subword") or row.get("t_main") or "").strip()
        )
        for field_name, column in (("definition", "t_exp"), ("example", "t_exam")):
            text = normalizer.normalize(row.get(column) or "").replace("\u200b", "")
            for _start, _end, word in maximal_trie_matches(text, trie):
                occurrence = (row_id, field_name, word)
                if occurrence in seen_occurrences:
                    continue
                seen_occurrences.add(occurrence)
                item = candidates[word]
                item.discovery.add("community_boundary_in_rac")
                field_row = (row_id, field_name)
                if field_row not in item.field_rows:
                    if field_name == "definition":
                        item.definition_occurrences += 1
                    else:
                        item.example_occurrences += 1
                    item.field_rows.add(field_row)
                item.row_ids.add(row_id)
                if len(item.contexts) < 5:
                    item.contexts.append(
                        {
                            "t_id": row_id,
                            "headword": headword,
                            "field": field_name,
                            "excerpt": excerpt(text, word),
                        }
                    )


def mine(
    rows: list[dict[str, str]],
    segmenter: KhmerSegmenter,
    explicit_forms: set[str],
    *,
    max_clusters: int,
) -> dict[str, Candidate]:
    normalizer = KhmerNormalizer()
    candidates: dict[str, Candidate] = defaultdict(Candidate)

    for row in rows:
        row_id = (row.get("t_id") or "").strip()
        headword = normalizer.normalize(
            (row.get("t_subword") or row.get("t_main") or "").strip()
        )
        seen: set[tuple[str, str]] = set()
        for field_name, column in (("definition", "t_exp"), ("example", "t_exam")):
            text = normalizer.normalize(row.get(column) or "").replace("\u200b", "")
            for match in KHMER_RUN.finditer(text):
                run = match.group()
                # Merging adjacent unknown clusters produces reviewable lexical
                # spans rather than one candidate for every Khmer cluster.
                tokens = segmenter.segment(
                    run, disable_post_processing=False, normalize=False
                )
                for token in tokens:
                    if (
                        token in explicit_forms
                        or token in segmenter.words
                        or not plausible(token, max_clusters)
                    ):
                        continue
                    item = candidates[token]
                    item.discovery.add("unknown_span")
                    field_row = (row_id, field_name)
                    if field_row not in item.field_rows:
                        if field_name == "definition":
                            item.definition_occurrences += 1
                        else:
                            item.example_occurrences += 1
                        item.field_rows.add(field_row)
                    if run == token:
                        item.isolated_occurrences += 1
                    item.row_ids.add(row_id)
                    key = (token, field_name)
                    if len(item.contexts) < 5 and key not in seen:
                        item.contexts.append(
                            {
                                "t_id": row_id,
                                "headword": headword,
                                "field": field_name,
                                "excerpt": excerpt(text, token),
                            }
                        )
                    seen.add(key)
    return candidates


def rank(item: tuple[str, Candidate]) -> tuple[int, int, int, int, str]:
    word, evidence = item
    return (
        -len(evidence.row_ids),
        -evidence.example_occurrences,
        -evidence.isolated_occurrences,
        -(evidence.community_unknown_count + evidence.community_boundary_count),
        word,
    )


def write_outputs(
    candidates: dict[str, Candidate],
    output_jsonl: Path,
    output_tsv: Path,
    *,
    min_records: int,
) -> int:
    selected = [
        item for item in candidates.items() if len(item[1].row_ids) >= min_records
    ]
    selected.sort(key=rank)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for word, item in selected:
            handle.write(
                json.dumps(
                    {
                        "word": word,
                        "record_count": len(item.row_ids),
                        "definition_occurrences": item.definition_occurrences,
                        "example_occurrences": item.example_occurrences,
                        "isolated_occurrences": item.isolated_occurrences,
                        "community_unknown_count": item.community_unknown_count,
                        "community_boundary_count": item.community_boundary_count,
                        "discovery": sorted(item.discovery),
                        "contexts": item.contexts,
                        "status": "candidate",
                        "approved_word": "",
                        "review_note": "",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    fields = [
        "word",
        "record_count",
        "definition_occurrences",
        "example_occurrences",
        "isolated_occurrences",
        "community_unknown_count",
        "community_boundary_count",
        "discovery",
        "first_headword",
        "first_field",
        "first_excerpt",
        "status",
    ]
    with output_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for word, item in selected:
            context = item.contexts[0] if item.contexts else {}
            writer.writerow(
                {
                    "word": word,
                    "record_count": len(item.row_ids),
                    "definition_occurrences": item.definition_occurrences,
                    "example_occurrences": item.example_occurrences,
                    "isolated_occurrences": item.isolated_occurrences,
                    "community_unknown_count": item.community_unknown_count,
                    "community_boundary_count": item.community_boundary_count,
                    "discovery": ",".join(sorted(item.discovery)),
                    "first_headword": context.get("headword", ""),
                    "first_field": context.get("field", ""),
                    "first_excerpt": context.get("excerpt", ""),
                    "status": "candidate",
                }
            )
    return len(selected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rac-csv", type=Path, default=DEFAULT_RAC)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--community-candidates", type=Path, default=DEFAULT_COMMUNITY)
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=ROOT / "build" / "rac_definition_review" / "candidates.jsonl",
    )
    parser.add_argument(
        "--output-tsv",
        type=Path,
        default=ROOT / "build" / "rac_definition_review" / "candidates.tsv",
    )
    parser.add_argument("--min-records", type=int, default=2)
    parser.add_argument("--min-community-boundaries", type=int, default=2)
    parser.add_argument("--max-clusters", type=int, default=10)
    args = parser.parse_args()

    normalizer = KhmerNormalizer()
    rows = read_rac(args.rac_csv)
    explicit_forms = clean_explicit_forms(rows, normalizer)
    segmenter = KhmerSegmenter(dictionary_path=args.dictionary)
    candidates = mine(
        rows,
        segmenter,
        explicit_forms,
        max_clusters=args.max_clusters,
    )
    community = load_community_counts(args.community_candidates)
    mine_corpus_boundaries_in_rac(
        rows,
        candidates,
        community,
        explicit_forms,
        max_clusters=args.max_clusters,
        min_community_boundaries=args.min_community_boundaries,
    )
    for word, item in candidates.items():
        item.community_unknown_count, item.community_boundary_count = community.get(
            word, (0, 0)
        )

    count = write_outputs(
        candidates,
        args.output_jsonl,
        args.output_tsv,
        min_records=args.min_records,
    )
    print(
        json.dumps(
            {
                "rac_rows": len(rows),
                "explicit_rac_forms": len(explicit_forms),
                "all_candidates": len(candidates),
                "selected_candidates": count,
                "min_records": args.min_records,
                "output_jsonl": str(args.output_jsonl),
                "output_tsv": str(args.output_tsv),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
