"""Typed public result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


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
    kind: str
    confidence: float
    suggestions: tuple[SpellingSuggestion, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "confidence": self.confidence,
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
        }
