"""Conservative dictionary-backed spelling diagnostics for Khmer text."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .models import Diagnostic, Edit, Token


@dataclass(frozen=True, slots=True)
class MissingMarkCandidate:
    """A dictionary word reconstructed by inserting one Khmer mark."""

    word: str
    inserted_char: str
    inserted_offset: int
    lexical_cost: float


def is_recoverable_mark(char: str) -> bool:
    """Return whether omission of ``char`` is a supported typo operation."""

    codepoint = ord(char)
    return (0x17B6 <= codepoint <= 0x17D1) or codepoint in {0x17D3, 0x17DD}


class MissingMarkIndex:
    """Lookup dictionary words after deletion of one Khmer vowel or sign."""

    def __init__(
        self,
        words: Iterable[str],
        word_cost: Callable[[str], float],
    ) -> None:
        word_set = set(words)
        mutable: dict[str, set[str]] = {}
        for word in word_set:
            if len(word) < 2:
                continue
            for offset, char in enumerate(word):
                if not is_recoverable_mark(char):
                    continue
                key = word[:offset] + word[offset + 1 :]
                # A valid dictionary surface is not considered misspelled.
                if not key or key in word_set:
                    continue
                mutable.setdefault(key, set()).add(word)

        self._entries = {
            key: tuple(sorted(values, key=lambda word: (word_cost(word), word)))
            for key, values in mutable.items()
        }
        self._word_cost = word_cost

    def lookup(self, surface: str) -> tuple[MissingMarkCandidate, ...]:
        candidates = []
        for word in self._entries.get(surface, ()):
            for offset, char in enumerate(word):
                if is_recoverable_mark(char) and word[:offset] + word[offset + 1 :] == surface:
                    candidates.append(
                        MissingMarkCandidate(
                            word=word,
                            inserted_char=char,
                            inserted_offset=offset,
                            lexical_cost=self._word_cost(word),
                        )
                    )
                    break
        return tuple(candidates)

    def __len__(self) -> int:
        return len(self._entries)


def _is_single_cluster(
    token: Token,
    cluster_length: Callable[[str, int], int],
    is_khmer_char: Callable[[str], bool],
) -> bool:
    return bool(
        token.text
        and is_khmer_char(token.text[0])
        and cluster_length(token.text, 0) == len(token.text)
    )


def _candidate_confidence(improvement: float) -> float:
    """Map a positive cost margin to a conservative 0..1 confidence."""

    return round(1.0 - math.exp(-improvement / 8.0), 6)


def find_missing_mark_diagnostics(
    tokens: Sequence[Token],
    index: MissingMarkIndex,
    *,
    word_cost: Callable[[str], float],
    unknown_cost: float,
    cluster_length: Callable[[str, int], int],
    is_khmer_char: Callable[[str], bool],
    max_neighbors: int = 2,
    minimum_improvement: float = 1.0,
    minimum_confidence: float = 0.75,
) -> tuple[Diagnostic, ...]:
    """Find whole-span diagnostics around baseline unknown Khmer tokens."""

    proposals: dict[tuple[int, int], tuple[float, float, Diagnostic]] = {}
    for unknown_index, token in enumerate(tokens):
        if token.type != "unknown" or not token.text:
            continue
        if not any(is_khmer_char(char) for char in token.text):
            continue

        left_limit = unknown_index
        for probe in range(unknown_index - 1, max(-1, unknown_index - max_neighbors - 1), -1):
            if not _is_single_cluster(tokens[probe], cluster_length, is_khmer_char):
                break
            left_limit = probe

        right_limit = unknown_index
        for probe in range(unknown_index + 1, min(len(tokens), unknown_index + max_neighbors + 1)):
            if not _is_single_cluster(tokens[probe], cluster_length, is_khmer_char):
                break
            right_limit = probe

        for left in range(left_limit, unknown_index + 1):
            for right in range(unknown_index, right_limit + 1):
                window = tokens[left : right + 1]
                surface = "".join(item.text for item in window)
                candidates = index.lookup(surface)
                if not candidates:
                    continue

                baseline_cost = sum(
                    word_cost(item.text) if item.known else unknown_cost
                    for item in window
                )
                ranked = []
                for candidate in candidates:
                    edit_cost = (
                        0.25
                        if 0x17B6 <= ord(candidate.inserted_char) <= 0x17C5
                        else 0.35
                    )
                    candidate_cost = candidate.lexical_cost + edit_cost
                    improvement = baseline_cost - candidate_cost
                    if improvement >= minimum_improvement:
                        ranked.append((candidate_cost, candidate, improvement))
                if not ranked:
                    continue
                ranked.sort(key=lambda item: (item[0], item[1].word, item[1].inserted_offset))
                candidate_cost, best, improvement = ranked[0]
                confidence = _candidate_confidence(improvement)
                if confidence < minimum_confidence:
                    continue
                start = window[0].start
                end = window[-1].end
                insertion = start + best.inserted_offset
                kind = (
                    "missing_dependent_vowel"
                    if 0x17B6 <= ord(best.inserted_char) <= 0x17C5
                    else "missing_khmer_sign"
                )
                alternatives = tuple(
                    dict.fromkeys(
                        item.word
                        for _, item, _ in ranked[1:]
                        if item.word != best.word
                    )
                )
                alternatives = alternatives[:4]
                diagnostic = Diagnostic(
                    kind=kind,
                    start=start,
                    end=end,
                    surface=surface,
                    candidate=best.word,
                    confidence=confidence,
                    edits=(
                        Edit(
                            operation="insert",
                            start=insertion,
                            end=insertion,
                            text=best.inserted_char,
                        ),
                    ),
                    alternatives=alternatives,
                )
                key = (start, end)
                score = (improvement, -candidate_cost)
                previous = proposals.get(key)
                if previous is None or score > previous[:2]:
                    proposals[key] = (score[0], score[1], diagnostic)

    # Prefer high-confidence, wider spans and suppress overlapping diagnostics.
    ordered = sorted(
        (item[2] for item in proposals.values()),
        key=lambda item: (-item.confidence, -(item.end - item.start), item.start),
    )
    selected: list[Diagnostic] = []
    for diagnostic in ordered:
        if any(
            diagnostic.start < existing.end and diagnostic.end > existing.start
            for existing in selected
        ):
            continue
        selected.append(diagnostic)
    return tuple(sorted(selected, key=lambda item: (item.start, item.end)))
