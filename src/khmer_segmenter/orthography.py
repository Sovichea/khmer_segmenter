"""Small, deterministic Khmer orthographic equivalence helpers.

These helpers deliberately do not normalize text.  They are used where an
application explicitly chooses to accept the two legacy COENG DA/TA encodings
as visually equivalent.
"""

from __future__ import annotations

COENG_DA = "\u17d2\u178a"
COENG_TA = "\u17d2\u178f"


def coeng_da_ta_variants(word: str, *, include_original: bool = False) -> frozenset[str]:
    """Return all deterministic COENG DA/TA variants of *word*.

    The forms are lexical aliases for segmentation; the caller decides whether
    they are also acceptable for spelling.  Branching each occurrence, rather
    than replacing every occurrence at once, also handles the rare mixed form.
    """

    variants = {word}
    index = 0
    while index < len(word) - 1:
        pair = word[index : index + 2]
        if pair in {COENG_DA, COENG_TA}:
            replacement = COENG_TA if pair == COENG_DA else COENG_DA
            variants.update(
                candidate[:index] + replacement + candidate[index + 2 :]
                for candidate in tuple(variants)
            )
            index += 2
        else:
            index += 1
    if not include_original:
        variants.discard(word)
    return frozenset(variants)
