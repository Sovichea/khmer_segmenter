"""Build local runtime dictionaries from user-obtained upstream data."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .data import DICTIONARY_SOURCE_CREDIT, DICTIONARY_SOURCE_URL, DataFiles
from .normalization import KhmerNormalizer


REFERENCE_NAME = "Khmer Dictionary 2022"
REFERENCE_AUTHORITY = "National Council of Khmer Language, Royal Academy of Cambodia"
DEFAULT_MAX_SUPPLEMENTAL_CLUSTERS = 4


@dataclass(frozen=True, slots=True)
class SupplementalDecision:
    """Auditable result produced while decomposing a supplemental entry."""

    source: str
    chunk: str
    accepted: bool
    reason: str


def _is_lexical_khmer(text: str) -> bool:
    return bool(text) and all(
        "\u1780" <= character <= "\u17d3" or character == "\u17dd"
        for character in text
    )


def _cluster_count(text: str) -> int:
    count = 0
    previous = ""
    for character in text:
        if "\u1780" <= character <= "\u17b3" and previous != "\u17d2":
            count += 1
        previous = character
    return count


def _is_safe_supplemental_chunk(text: str) -> bool:
    """Reject orphan signs and legacy Sanskrit letters from noisy sources."""

    return (
        _is_lexical_khmer(text)
        and "\u1780" <= text[0] <= "\u17b3"
        and not any(character in {"\u179d", "\u179e"} for character in text)
    )


def _curated_trie(words: set[str]) -> dict:
    root: dict = {}
    for word in words:
        node = root
        for character in word:
            node = node.setdefault(character, {})
        node[None] = word
    return root


def _longest_curated_at(text: str, start: int, trie: dict) -> str | None:
    node = trie
    longest = None
    for character in text[start:]:
        node = node.get(character)
        if node is None:
            break
        if None in node:
            longest = node[None]
    return longest


def _is_fully_curated(text: str, trie: dict) -> bool:
    index = 0
    while index < len(text):
        word = _longest_curated_at(text, index, trie)
        if not word:
            return False
        index += len(word)
    return True


def decompose_supplemental_words(
    entries: set[str],
    curated_words: set[str],
    *,
    reviewed_typos: set[str] | None = None,
    max_clusters: int = DEFAULT_MAX_SUPPLEMENTAL_CLUSTERS,
) -> tuple[set[str], list[SupplementalDecision]]:
    """Reduce phrase-like supplemental entries to conservative lexical chunks.

    Longest curated matches act as immutable boundaries and are never copied to
    the supplemental output. Unknown runs are retained only when they look like
    small Khmer lexical units. Reviewed typo surfaces are retained whole so the
    segmenter can preserve their diagnostic span without accepting their
    spelling.
    """

    if max_clusters < 2:
        raise ValueError("max_clusters must be at least 2")
    reviewed_typos = reviewed_typos or set()
    trie = _curated_trie(curated_words)
    accepted: set[str] = set()
    decisions: list[SupplementalDecision] = []

    for source in sorted(entries | reviewed_typos):
        if source in curated_words:
            decisions.append(SupplementalDecision(source, source, False, "curated"))
            continue
        if source in reviewed_typos:
            accepted.add(source)
            decisions.append(SupplementalDecision(source, source, True, "reviewed_typo"))
            continue
        source_clusters = _cluster_count(source)
        if (
            2 <= source_clusters <= max_clusters
            and _is_safe_supplemental_chunk(source)
            and not _is_fully_curated(source, trie)
        ):
            accepted.add(source)
            decisions.append(
                SupplementalDecision(source, source, True, "short_supplemental_entry")
            )
            continue

        index = 0
        unknown_start = None

        def finish_unknown(end: int) -> None:
            nonlocal unknown_start
            if unknown_start is None:
                return
            chunk = source[unknown_start:end]
            clusters = _cluster_count(chunk)
            if not _is_safe_supplemental_chunk(chunk):
                reason = "nonlexical"
            elif clusters < 2:
                reason = "single_cluster_fragment"
            elif clusters > max_clusters:
                reason = "long_unresolved_span"
            elif chunk.startswith("\u17d2"):
                reason = "invalid_initial_coeng"
            else:
                reason = "short_supplemental_chunk"
                accepted.add(chunk)
                decisions.append(SupplementalDecision(source, chunk, True, reason))
                unknown_start = None
                return
            decisions.append(SupplementalDecision(source, chunk, False, reason))
            unknown_start = None

        while index < len(source):
            curated = _longest_curated_at(source, index, trie)
            if curated:
                finish_unknown(index)
                decisions.append(SupplementalDecision(source, curated, False, "curated_chunk"))
                index += len(curated)
                continue
            if not _is_lexical_khmer(source[index]):
                finish_unknown(index)
                decisions.append(
                    SupplementalDecision(source, source[index], False, "boundary")
                )
                index += 1
                continue
            if unknown_start is None:
                unknown_start = index
            index += 1
        finish_unknown(len(source))

    return accepted - curated_words, decisions


def read_words(path: Path, tsv: bool = False) -> tuple[list[str], int]:
    """Read and normalize one-word records from a text or TSV file."""

    if not path.is_file():
        return [], 0
    normalizer = KhmerNormalizer()
    words: list[str] = []
    rejected = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            raw = line.rstrip("\r\n")
            if tsv:
                raw = raw.split("\t", 1)[0]
            word = normalizer.normalize(raw.strip())
            if not word or any(char.isspace() for char in word):
                rejected += 1
                continue
            words.append(word)
    return words, rejected


def write_words(path: Path, words: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")


def prepare_dictionary(
    source_tsv: str | Path,
    output_dir: str | Path,
    *,
    port_dictionary: str | Path | None = None,
) -> dict[str, object]:
    """Normalize an upstream TSV into ignored local runtime word lists."""

    source_tsv = Path(source_tsv)
    if not source_tsv.is_file():
        raise FileNotFoundError(f"dictionary source TSV not found: {source_tsv}")
    files = DataFiles(Path(output_dir).expanduser().resolve())
    reference_rows, reference_rejected = read_words(source_tsv, tsv=True)
    existing_source = (
        files.supplemental_words
        if files.supplemental_words.is_file()
        else files.dictionary
    )
    existing_rows, existing_rejected = read_words(existing_source)
    official = set(reference_rows)
    supplemental_candidates = set(existing_rows) - official
    reviewed_typos: set[str] = set()
    if files.typo_corrections.is_file():
        from .spelling import load_approved_typo_corrections

        reviewed_typos = set(load_approved_typo_corrections(files.typo_corrections))
    supplemental, supplemental_audit = decompose_supplemental_words(
        supplemental_candidates,
        official,
        reviewed_typos=reviewed_typos,
    )
    runtime = official | supplemental

    write_words(files.official_words, official)
    write_words(files.supplemental_words, supplemental)
    write_words(files.dictionary, runtime)
    if port_dictionary is not None:
        port_path = Path(port_dictionary)
        port_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files.dictionary, port_path)

    report: dict[str, object] = {
        "reference": {
            "name": REFERENCE_NAME,
            "authority": REFERENCE_AUTHORITY,
            "source": DICTIONARY_SOURCE_URL,
            "source_credit": DICTIONARY_SOURCE_CREDIT,
            "terms_note": "Research purpose only; review the upstream dataset card",
            "redistributed": False,
            "source_rows": len(reference_rows) + reference_rejected,
            "accepted_unique_headwords": len(official),
            "rejected_rows": reference_rejected,
        },
        "counts": {
            "official_headwords": len(official),
            "supplemental_retained": len(supplemental),
            "supplemental_candidates": len(supplemental_candidates),
            "runtime_union": len(runtime),
            "supplemental_rejected": existing_rejected,
        },
    }
    provenance = files.root / "khmer_dictionary_provenance.json"
    provenance.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    audit_path = files.root / "khmer_dictionary_supplemental_audit.tsv"
    audit_lines = ["source\tchunk\taccepted\treason"]
    audit_lines.extend(
        "\t".join(
            (
                decision.source,
                decision.chunk,
                str(decision.accepted).lower(),
                decision.reason,
            )
        )
        for decision in supplemental_audit
    )
    audit_path.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    return report
