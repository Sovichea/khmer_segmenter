"""Local, deterministic typo recovery for Khmer text."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Iterable

from .models import EditOperation, SpellingDiagnostic, SpellingSuggestion, Token


_SHORT_FRAGMENT_FREQUENCY_LIMIT = 500
_COMMON_ENDING_FREQUENCY_MINIMUM = 10
_COENG = "\u17d2"
_RO = "\u179a"
_CA = "\u1785"
_CO = "\u1787"
_REAHMUK = "\u17c7"  # ះ
_YUUKALEAPINTU = "\u17c8"  # ៈ
_COMMON_VISUAL_CONFUSIONS = (
    (_REAHMUK, _YUUKALEAPINTU),
    (_YUUKALEAPINTU, _REAHMUK),
    ("\u17bc", "\u17bd"),  # ូ -> ួ
    ("\u17bd", "\u17bc"),  # ួ -> ូ
    ("\u17cf", "\u17cd"),  # ៏ -> ៍
    ("\u17cd", "\u17cf"),  # ៍ -> ៏
)

# Human-reviewed, high-frequency misspellings that otherwise segment entirely
# into valid dictionary fragments. Exact matching keeps these safe for live
# typing without enabling a broad fuzzy scan over every valid word sequence.
def load_approved_typo_corrections(path) -> dict[str, str]:
    """Load only maintainer-approved exact correction pairs from TSV."""

    if not path or not path.is_file():
        return {}
    approved: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("status") != "approved":
                continue
            typed = row.get("typed", "").strip()
            correction = row.get("correction", "").strip()
            if not typed or not correction or typed == correction:
                continue
            if typed in approved and approved[typed] != correction:
                raise ValueError(f"conflicting approved typo correction for {typed!r}")
            approved[typed] = correction
    return approved


def _is_base(char: str) -> bool:
    return "\u1780" <= char <= "\u17b3"


def _is_dependent_vowel(char: str) -> bool:
    return "\u17b6" <= char <= "\u17c5"


def _is_register_or_sign(char: str) -> bool:
    return "\u17c6" <= char <= "\u17d1" or char in {"\u17d3", "\u17dd"}


def _is_lexical_khmer(text: str) -> bool:
    if not text or "\u17d7" in text:
        return False
    return all("\u1780" <= char <= "\u17d3" or char == "\u17dd" for char in text)


def _base_skeleton(text: str) -> tuple[str, ...]:
    skeleton: list[str] = []
    previous = ""
    for char in text:
        if _is_base(char):
            # RAC data contains both subscript DA and TA encodings. They are
            # segmentation aliases and should also share a fuzzy-search key.
            if previous == "\u17d2" and char in {"\u178a", "\u178f"}:
                skeleton.append("\u178f")
            else:
                skeleton.append(char)
        previous = char
    return tuple(skeleton)


def _orthographic_cluster_count(text: str) -> int:
    count = 0
    previous = ""
    for char in text:
        if _is_base(char) and previous != "\u17d2":
            count += 1
        previous = char
    return count


def _edit_weight(char: str) -> float:
    if _is_dependent_vowel(char):
        return 0.25
    if _is_register_or_sign(char):
        return 0.35
    if char == "\u17d2":
        return 0.60
    return 1.0


def _substitution_weight(
    source: str,
    target: str,
    *,
    source_previous: str = "",
    target_previous: str = "",
) -> float:
    if source == target:
        return 0.0
    # U and OO are closely related vowel signs and a frequent informal
    # omission confuses them (for example សុម -> សូម). Keep this narrower than
    # discounting all dependent-vowel substitutions.
    if source == "\u17bb" and target == "\u17bc":
        return 0.25
    if _is_dependent_vowel(source) and _is_dependent_vowel(target):
        return 0.35
    if _is_register_or_sign(source) and _is_register_or_sign(target):
        return 0.40
    if (
        source_previous == "\u17d2"
        and target_previous == "\u17d2"
        and {source, target} == {"\u178a", "\u178f"}
    ):
        return 0.10
    return min(1.0, _edit_weight(source) + _edit_weight(target))


@dataclass(frozen=True, slots=True)
class _LocalEdit:
    kind: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class _Proposal:
    diagnostic: SpellingDiagnostic
    start_token: int
    end_token: int

    @property
    def score(self) -> float:
        """Reward a coherent span while still accounting for edit distance."""

        token_count = self.end_token - self.start_token + 1
        return token_count - 0.5 * self.diagnostic.suggestions[0].edit_cost - 0.25


def weighted_edits(source: str, target: str) -> tuple[float, tuple[_LocalEdit, ...]]:
    """Return a Khmer-aware edit cost and a code-point edit script."""

    rows = len(source) + 1
    columns = len(target) + 1
    table: list[list[tuple[float, tuple[_LocalEdit, ...]]]] = [
        [(float("inf"), ()) for _ in range(columns)] for _ in range(rows)
    ]
    table[0][0] = (0.0, ())

    for i in range(1, rows):
        previous_cost, previous_edits = table[i - 1][0]
        table[i][0] = (
            previous_cost + _edit_weight(source[i - 1]),
            previous_edits + (_LocalEdit("delete", i - 1, i, ""),),
        )
    for j in range(1, columns):
        previous_cost, previous_edits = table[0][j - 1]
        table[0][j] = (
            previous_cost + _edit_weight(target[j - 1]),
            previous_edits + (_LocalEdit("insert", 0, 0, target[j - 1]),),
        )

    for i in range(1, rows):
        for j in range(1, columns):
            choices: list[tuple[float, int, tuple[_LocalEdit, ...]]] = []

            diagonal_cost, diagonal_edits = table[i - 1][j - 1]
            if source[i - 1] == target[j - 1]:
                choices.append((diagonal_cost, 0, diagonal_edits))
            else:
                choices.append(
                    (
                        diagonal_cost
                        + _substitution_weight(
                            source[i - 1],
                            target[j - 1],
                            source_previous=source[i - 2] if i >= 2 else "",
                            target_previous=target[j - 2] if j >= 2 else "",
                        ),
                        1,
                        diagonal_edits
                        + (_LocalEdit("replace", i - 1, i, target[j - 1]),),
                    )
                )

            delete_cost, delete_edits = table[i - 1][j]
            choices.append(
                (
                    delete_cost + _edit_weight(source[i - 1]),
                    2,
                    delete_edits + (_LocalEdit("delete", i - 1, i, ""),),
                )
            )

            insert_cost, insert_edits = table[i][j - 1]
            choices.append(
                (
                    insert_cost + _edit_weight(target[j - 1]),
                    3,
                    insert_edits + (_LocalEdit("insert", i, i, target[j - 1]),),
                )
            )

            # A common Khmer typo writes MA + COENG where the intended form
            # uses NIKAHIT on the preceding cluster (ជម្រុញ -> ជំរុញ).
            if i >= 2 and source[i - 2 : i] == "\u1798\u17d2" and target[j - 1] == "\u17c6":
                previous_cost, previous_edits = table[i - 2][j - 1]
                choices.append(
                    (
                        previous_cost + 0.35,
                        1,
                        previous_edits + (_LocalEdit("replace", i - 2, i, "\u17c6"),),
                    )
                )
            if i >= 1 and j >= 2 and source[i - 1] == "\u17c6" and target[j - 2 : j] == "\u1798\u17d2":
                previous_cost, previous_edits = table[i - 1][j - 2]
                choices.append(
                    (
                        previous_cost + 0.35,
                        1,
                        previous_edits
                        + (_LocalEdit("replace", i - 1, i, "\u1798\u17d2"),),
                    )
                )

            # A malformed U + I sequence is seen in informal typing where the
            # intended cluster uses TRIISAP + II (for example សុិ -> ស៊ី).
            # Treat this as one sign-sequence replacement rather than two
            # unrelated edits. The rule is orthographic and is not tied to a
            # particular dictionary word.
            if (
                i >= 2
                and j >= 2
                and source[i - 2 : i] == "\u17bb\u17b7"
                and target[j - 2 : j] == "\u17ca\u17b8"
            ):
                previous_cost, previous_edits = table[i - 2][j - 2]
                choices.append(
                    (
                        previous_cost + 0.25,
                        1,
                        previous_edits
                        + (_LocalEdit("replace", i - 2, i, "\u17ca\u17b8"),),
                    )
                )

            # A repeated consonant can result from omitting medial RO, as in
            # សសេរ -> សរសេរ. Keep this narrower than a general base insertion.
            if (
                i >= 2
                and j >= 3
                and source[i - 2] == source[i - 1]
                and target[j - 3] == source[i - 2]
                and target[j - 2] == "\u179a"
                and target[j - 1] == source[i - 1]
            ):
                previous_cost, previous_edits = table[i - 2][j - 3]
                choices.append(
                    (
                        previous_cost + 0.25,
                        1,
                        previous_edits + (_LocalEdit("insert", i - 1, i - 1, "\u179a"),),
                    )
                )

            # Prefer a diagonal operation when costs tie, which produces clearer
            # editor replacements than a delete followed by an insertion.
            best_cost, _, best_edits = min(choices, key=lambda item: (item[0], item[1]))
            table[i][j] = (best_cost, best_edits)

    return table[-1][-1]


class TypoDetector:
    """Find probable dictionary-word typos near suspicious segmentation tokens."""

    def __init__(
        self,
        words: Iterable[str],
        frequencies: dict[str, int | float] | None = None,
        reviewed_typos: dict[str, str] | None = None,
    ):
        self.words = frozenset(word for word in words if _is_lexical_khmer(word))
        self.frequencies = frequencies or {}
        # Some Khmer signs are difficult to distinguish on small screens.
        # Derive one-character exact aliases from the lexicon, but never treat
        # another valid dictionary word or an ambiguous alias as a typo.
        generated_candidates: dict[str, set[str]] = defaultdict(set)
        for word in self.words:
            for index, character in enumerate(word):
                for typed, intended in _COMMON_VISUAL_CONFUSIONS:
                    if character != intended:
                        continue
                    alias = word[:index] + typed + word[index + 1 :]
                    if alias not in self.words:
                        generated_candidates[alias].add(word)
                if index > 0 and word[index - 1] == _COENG and character in (_CA, _CO):
                    typed = _CO if character == _CA else _CA
                    alias = word[:index] + typed + word[index + 1 :]
                    if alias not in self.words:
                        generated_candidates[alias].add(word)
            if (
                _is_dependent_vowel(word[-1])
                and float(self.frequencies.get(word, 0)) >= _COMMON_ENDING_FREQUENCY_MINIMUM
            ):
                alias = word + _RO
                if alias not in self.words:
                    generated_candidates[alias].add(word)
        generated_confusions = {
            alias: next(iter(candidates))
            for alias, candidates in generated_candidates.items()
            if len(candidates) == 1
        }
        generated_confusions.update(reviewed_typos or {})
        self.reviewed_typos = generated_confusions
        self._max_exact_typo_length = max(map(len, self.reviewed_typos), default=0)
        self._exact_skeleton: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self._deletion_skeleton: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for word in sorted(self.words):
            skeleton = _base_skeleton(word)
            self._exact_skeleton[skeleton].append(word)
            for index in range(len(skeleton)):
                signature = skeleton[:index] + skeleton[index + 1 :]
                self._deletion_skeleton[signature].append(word)

    def complete_prefix(self, prefix: str, *, limit: int) -> tuple[SpellingSuggestion, ...]:
        """Return curated words beginning with *prefix*, with an exact match first."""

        if not prefix or limit <= 0:
            return ()
        matches = (word for word in self.words if word.startswith(prefix))
        ranked = sorted(
            matches,
            key=lambda word: (
                word != prefix,
                -self.frequencies.get(word, 0),
                len(word),
                word,
            ),
        )
        return tuple(
            SpellingSuggestion(
                text=word,
                edit_cost=0.0,
                edits=(),
                frequency=self.frequencies.get(word),
            )
            for word in ranked[:limit]
        )

    def _candidate_words(self, text: str, max_edit_cost: float) -> set[str]:
        skeleton = _base_skeleton(text)
        candidates = set(self._exact_skeleton.get(skeleton, ()))

        # MA + COENG is sometimes typed where a NIKAHIT belongs (and vice
        # versa). Since this rewrite has a low edit cost, add its candidates
        # even during the conservative search that excludes general base edits.
        rewritten = {
            text.replace("\u1798\u17d2", "\u17c6"),
            text.replace("\u17c6", "\u1798\u17d2"),
        }
        for variant in rewritten - {text}:
            candidates.update(self._exact_skeleton.get(_base_skeleton(variant), ()))

        # Index the inverse of the omitted-medial-RO rule above even when the
        # conservative threshold excludes general base-character candidates.
        for index in range(len(skeleton) - 1):
            if skeleton[index] == skeleton[index + 1]:
                with_medial_ro = (
                    skeleton[: index + 1]
                    + ("\u179a",)
                    + skeleton[index + 1 :]
                )
                candidates.update(self._exact_skeleton.get(with_medial_ro, ()))

        # Base-character edits cost 1.0, so conservative searches can avoid
        # their substantially broader candidate pools altogether.
        if max_edit_cost >= 1.0:
            # A target may contain one missing base character.
            candidates.update(self._deletion_skeleton.get(skeleton, ()))

            # Removing one source base supports an extra base in the input,
            # while shared deletion signatures support one base substitution.
            for index in range(len(skeleton)):
                signature = skeleton[:index] + skeleton[index + 1 :]
                candidates.update(self._exact_skeleton.get(signature, ()))
                # For a one-base query the empty signature is shared by every
                # one-base word and does not provide a useful prefilter.
                if signature:
                    candidates.update(self._deletion_skeleton.get(signature, ()))

        return {
            word
            for word in candidates
            if word != text
            and len(word) > 1
            and abs(len(word) - len(text)) <= 1
        }

    @lru_cache(maxsize=4096)
    def _ranked_suggestions(
        self, text: str, max_edit_cost: float
    ) -> tuple[tuple[float, float, str, tuple[_LocalEdit, ...]], ...]:
        ranked: list[tuple[float, float, str, tuple[_LocalEdit, ...]]] = []
        for word in self._candidate_words(text, max_edit_cost):
            cost, edits = weighted_edits(text, word)
            if cost <= max_edit_cost:
                frequency = float(self.frequencies.get(word, 0))
                ranked.append((cost, -frequency, word, edits))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return tuple(ranked)

    def suggestions(
        self,
        text: str,
        *,
        span_start: int,
        max_edit_cost: float,
        limit: int,
    ) -> tuple[SpellingSuggestion, ...]:
        ranked = self._ranked_suggestions(text, max_edit_cost)
        suggestions = [
            SpellingSuggestion(
                text=word,
                edit_cost=round(cost, 3),
                edits=tuple(
                    EditOperation(
                        kind=edit.kind,
                        start=span_start + edit.start,
                        end=span_start + edit.end,
                        text=edit.text,
                    )
                    for edit in edits
                ),
                frequency=self.frequencies.get(word),
            )
            for cost, _, word, edits in ranked
            if word != self.reviewed_typos.get(text)
        ]
        reviewed_text = self.reviewed_typos.get(text)
        if reviewed_text is not None:
            cost, edits = weighted_edits(text, reviewed_text)
            suggestions.insert(
                0,
                SpellingSuggestion(
                    text=reviewed_text,
                    edit_cost=round(cost, 3),
                    edits=tuple(
                        EditOperation(
                            kind=edit.kind,
                            start=span_start + edit.start,
                            end=span_start + edit.end,
                            text=edit.text,
                        )
                        for edit in edits
                    ),
                    frequency=self.frequencies.get(reviewed_text),
                ),
            )
        return tuple(suggestions[:limit])

    def suggest_word(
        self,
        text: str,
        *,
        span_start: int = 0,
        max_edit_cost: float = 1.5,
        limit: int = 5,
    ) -> tuple[SpellingSuggestion, ...]:
        """Suggest corrections while treating *text* as one complete word."""

        if not math.isfinite(max_edit_cost) or max_edit_cost <= 0:
            raise ValueError("max_edit_cost must be finite and greater than zero")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if not _is_lexical_khmer(text) or (
            text in self.words and text not in self.reviewed_typos
        ):
            return ()
        return self.suggestions(
            text,
            span_start=span_start,
            max_edit_cost=max_edit_cost,
            limit=limit,
        )

    @staticmethod
    def _kind(suggestion: SpellingSuggestion) -> str:
        edits = suggestion.edits
        if edits and all(edit.kind == "insert" and _is_dependent_vowel(edit.text) for edit in edits):
            return "missing_dependent_vowel"
        if edits and all(edit.kind == "delete" for edit in edits):
            return "extra_character"
        return "probable_typo"

    @staticmethod
    def _confidence(suggestions: tuple[SpellingSuggestion, ...], max_edit_cost: float) -> float:
        best = suggestions[0].edit_cost
        confidence = 1.0 - 0.45 * (best / max(max_edit_cost, 0.001))
        if len(suggestions) > 1:
            margin = suggestions[1].edit_cost - best
            confidence += min(0.15, max(0.0, margin) * 0.2)
        return round(max(0.05, min(0.99, confidence)), 3)

    def detect(
        self,
        normalized_text: str,
        tokens: list[Token],
        *,
        max_edit_cost: float = 0.75,
        max_suggestions: int = 3,
        context_tokens: int = 1,
        include_valid_fragments: bool = False,
    ) -> list[SpellingDiagnostic]:
        if not math.isfinite(max_edit_cost) or max_edit_cost <= 0:
            raise ValueError("max_edit_cost must be finite and greater than zero")
        if max_suggestions <= 0:
            raise ValueError("max_suggestions must be greater than zero")
        if context_tokens < 0:
            raise ValueError("context_tokens cannot be negative")

        lexical = [_is_lexical_khmer(token.text) for token in tokens]
        cluster_counts = [
            _orthographic_cluster_count(token.text) if lexical[index] else 0
            for index, token in enumerate(tokens)
        ]
        invalid_indices = {
            index
            for index, token in enumerate(tokens)
            if lexical[index] and not token.spelling_valid
        }
        fragmentation_indices: set[int] = set()
        for index in range(len(tokens) - 1):
            adjacent_lexical = lexical[index] and lexical[index + 1]
            conservative_fragment = (
                adjacent_lexical
                and cluster_counts[index] == 1
                and cluster_counts[index + 1] == 1
                and (len(tokens[index].text) == 1 or len(tokens[index + 1].text) == 1)
                and min(tokens[index].frequency or 0, tokens[index + 1].frequency or 0)
                <= _SHORT_FRAGMENT_FREQUENCY_LIMIT
            )
            if conservative_fragment or (include_valid_fragments and adjacent_lexical):
                fragmentation_indices.update((index, index + 1))
        suspicious = invalid_indices | fragmentation_indices
        proposals: dict[tuple[int, int], _Proposal] = {}

        # Recover exact whole-word errors even when every segmented fragment is
        # valid. Matching remains token-aligned and bounded by the longest
        # exact alias, so long dictionary-derived forms are supported without
        # opening the precision profile to general fuzzy scans.
        for start_index in range(len(tokens)):
            candidate_text = ""
            for end_index in range(start_index, len(tokens)):
                if not lexical[end_index]:
                    break
                if end_index > start_index and tokens[end_index - 1].end != tokens[end_index].start:
                    break
                candidate_text += tokens[end_index].text
                if len(candidate_text) > self._max_exact_typo_length:
                    break
                intended = self.reviewed_typos.get(candidate_text)
                # Approved corrections are human-reviewed and may intentionally
                # be multiword expressions that are not single lexicon entries.
                if intended is None:
                    continue
                span_start = tokens[start_index].start
                span_end = tokens[end_index].end
                cost, local_edits = weighted_edits(candidate_text, intended)
                reviewed = SpellingSuggestion(
                    text=intended,
                    edit_cost=round(cost, 3),
                    edits=tuple(
                        EditOperation(
                            kind=edit.kind,
                            start=span_start + edit.start,
                            end=span_start + edit.end,
                            text=edit.text,
                        )
                        for edit in local_edits
                    ),
                    frequency=self.frequencies.get(intended),
                )
                alternatives = list(
                    self.suggestions(
                        candidate_text,
                        span_start=span_start,
                        max_edit_cost=1.5,
                        limit=max(5, max_suggestions),
                    )
                )
                ranked = (reviewed,) + tuple(
                    item for item in alternatives if item.text != intended
                )[: max_suggestions - 1]
                diagnostic = SpellingDiagnostic(
                    text=normalized_text[span_start:span_end],
                    start=span_start,
                    end=span_end,
                    kind=self._kind(ranked[0]),
                    confidence=0.99,
                    suggestions=ranked,
                )
                proposals[(span_start, span_end)] = _Proposal(
                    diagnostic, start_index, end_index
                )

        for index in sorted(suspicious):
            run_start = index
            while run_start > 0 and lexical[run_start - 1]:
                run_start -= 1
            run_end = index
            while run_end + 1 < len(tokens) and lexical[run_end + 1]:
                run_end += 1

            left = max(run_start, index - context_tokens)
            right = min(run_end, index + context_tokens)
            for start_index in range(left, index + 1):
                for end_index in range(index, right + 1):
                    span_tokens = tokens[start_index : end_index + 1]
                    candidate_text = "".join(token.text for token in span_tokens)
                    if candidate_text in self.words:
                        continue
                    span_start = span_tokens[0].start
                    span_end = span_tokens[-1].end
                    suggestions = self.suggestions(
                        candidate_text,
                        span_start=span_start,
                        max_edit_cost=max_edit_cost,
                        limit=max_suggestions,
                    )
                    if not suggestions:
                        continue
                    confidence = self._confidence(suggestions, max_edit_cost)
                    if index not in invalid_indices:
                        confidence = round(confidence * 0.75, 3)
                    diagnostic = SpellingDiagnostic(
                        text=normalized_text[span_start:span_end],
                        start=span_start,
                        end=span_end,
                        kind=self._kind(suggestions[0]),
                        confidence=confidence,
                        suggestions=suggestions,
                    )
                    key = (span_start, span_end)
                    proposal = _Proposal(diagnostic, start_index, end_index)
                    previous = proposals.get(key)
                    if previous is None or (
                        suggestions[0].edit_cost,
                        -confidence,
                    ) < (
                        previous.diagnostic.suggestions[0].edit_cost,
                        -previous.diagnostic.confidence,
                    ):
                        proposals[key] = proposal

        # Weighted interval selection lets one coherent multi-token correction
        # beat several cheaper fragment corrections covering the same region.
        ordered = sorted(
            proposals.values(),
            key=lambda item: (
                item.diagnostic.end,
                item.diagnostic.start,
                -item.score,
            ),
        )
        best: list[tuple[float, tuple[_Proposal, ...]]] = [(0.0, ())]
        for position, proposal in enumerate(ordered, start=1):
            predecessor = 0
            for prior_position in range(position - 1, 0, -1):
                if ordered[prior_position - 1].diagnostic.end <= proposal.diagnostic.start:
                    predecessor = prior_position
                    break
            include_score = best[predecessor][0] + proposal.score
            include_items = best[predecessor][1] + (proposal,)
            exclude_score, exclude_items = best[position - 1]
            if (include_score, -len(include_items)) > (exclude_score, -len(exclude_items)):
                best.append((include_score, include_items))
            else:
                best.append((exclude_score, exclude_items))

        return [proposal.diagnostic for proposal in best[-1][1]]
