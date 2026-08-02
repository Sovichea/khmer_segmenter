"""Typed public result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class SpellcheckProfile(str, Enum):
    """Preset tuned for a spellcheck integration context."""

    TYPING = "typing"
    DOCUMENT = "document"
    HIGH_RECALL = "high-recall"

    @classmethod
    def coerce(cls, value: "SpellcheckProfile | str") -> "SpellcheckProfile":
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as error:
            choices = ", ".join(profile.value for profile in cls)
            raise ValueError(f"unknown spellcheck profile {value!r}; expected {choices}") from error


class DiagnosticKind(str, Enum):
    """Stable machine-readable spelling diagnostic categories."""

    MISSING_DEPENDENT_VOWEL = "missing_dependent_vowel"
    EXTRA_CHARACTER = "extra_character"
    PROBABLE_MISSPELLING = "probable_misspelling"


@dataclass(frozen=True, slots=True)
class SpellcheckConfig:
    """Resolved typo-detection settings shared by APIs and CLIs."""

    max_edit_cost: float
    max_suggestions: int
    context_tokens: int
    include_valid_fragments: bool
    min_confidence: float

    @classmethod
    def for_profile(cls, profile: SpellcheckProfile | str) -> "SpellcheckConfig":
        profile = SpellcheckProfile.coerce(profile)
        if profile is SpellcheckProfile.TYPING:
            return cls(0.75, 3, 1, False, 0.80)
        if profile is SpellcheckProfile.DOCUMENT:
            return cls(1.00, 5, 1, False, 0.75)
        return cls(1.50, 5, 1, True, 0.0)


@dataclass(frozen=True, slots=True)
class Token:
    """A segmented token with offsets and optional lexical metadata."""

    text: str
    start: int
    end: int
    known: bool
    type: str
    source: str
    frequency: int | float | None = None
    pos: str | None = None
    pos_candidates: tuple[str, ...] = ()
    spelling_valid: bool = False
    source_start: int | None = None
    source_end: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Token":
        return cls(
            text=value["text"],
            start=value["start"],
            end=value["end"],
            known=value["known"],
            type=value["type"],
            source=value["source"],
            frequency=value.get("frequency"),
            pos=value.get("pos"),
            pos_candidates=tuple(value.get("pos_candidates", ())),
            spelling_valid=bool(value.get("spelling_valid", value.get("known", False))),
            source_start=value.get("source_start"),
            source_end=value.get("source_end"),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["pos_candidates"] = list(self.pos_candidates)
        return result


@dataclass(frozen=True, slots=True)
class EditOperation:
    """One code-point edit using normalized-text offsets."""

    kind: str
    start: int
    end: int
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SpellingSuggestion:
    """A ranked replacement for a probable misspelling."""

    text: str
    edit_cost: float
    edits: tuple[EditOperation, ...] = ()
    frequency: int | float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "edit_cost": self.edit_cost,
            "edits": [edit.to_dict() for edit in self.edits],
            "frequency": self.frequency,
        }


@dataclass(frozen=True, slots=True)
class SpellingDiagnostic:
    """A whole input span that is probably a misspelled dictionary word."""

    text: str
    start: int
    end: int
    kind: DiagnosticKind
    confidence: float
    suggestions: tuple[SpellingSuggestion, ...] = ()
    source_start: int | None = None
    source_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
            "source_start": self.source_start,
            "source_end": self.source_end,
        }


@dataclass(frozen=True, slots=True)
class TextAnalysis:
    """One-pass segmentation and spelling result with mapped source offsets."""

    normalized: str
    tokens: tuple[Token, ...]
    diagnostics: tuple[SpellingDiagnostic, ...]
