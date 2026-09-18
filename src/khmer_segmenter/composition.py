"""Deterministic Khmer word-composition analysis.

The runtime uses this module to decide whether a curated word is a
composition of smaller accepted words. Compositions may be segmented into
their parts so long headword strings do not force a single token, while
lexicalized forms can be protected by a keep-list.
"""

from __future__ import annotations

from .spelling import _orthographic_cluster_count


def composition_parts(words, *, min_clusters: int = 2) -> frozenset[str]:
    """Return accepted words usable as composition parts.

    A part must have at least two orthographic clusters so a split can never
    isolate a bare letter or a single-cluster syllable.
    """

    return frozenset(
        word for word in words if word and _orthographic_cluster_count(word) >= min_clusters
    )


def max_part_length(parts: frozenset[str]) -> int:
    """Return the length of the longest composition part."""

    return max((len(part) for part in parts), default=0)


def is_composition(text: str, parts: frozenset[str], *, max_part_length: int) -> bool:
    """Return whether *text* splits into at least two accepted parts.

    The whole word as a single part never counts. All parts come from the
    accepted spelling vocabulary and already meet the cluster floor.
    """

    length = len(text)
    if length < 4 or max_part_length < 2:
        return False
    # suffix_ok[i] is True when text[i:] can be covered by one or more parts.
    suffix_ok = [False] * (length + 1)
    suffix_ok[length] = True
    for start in range(length - 1, -1, -1):
        limit = min(length, start + max_part_length)
        for end in range(start + 1, limit + 1):
            if text[start:end] in parts and suffix_ok[end]:
                suffix_ok[start] = True
                break
    # Force at least one split so the whole word cannot match itself.
    for split in range(1, length):
        if text[:split] in parts and suffix_ok[split]:
            return True
    return False
