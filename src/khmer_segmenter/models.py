"""Typed public result models."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Mapping, overload


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
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["pos_candidates"] = list(self.pos_candidates)
        return result


@dataclass(frozen=True, slots=True)
class Edit:
    """A text edit using offsets in the normalized input string."""

    operation: str
    start: int
    end: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["codepoints"] = [f"U+{ord(char):04X}" for char in self.text]
        return result


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A probable spelling issue covering a complete input span."""

    kind: str
    start: int
    end: int
    surface: str
    candidate: str
    confidence: float
    edits: tuple[Edit, ...]
    alternatives: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "surface": self.surface,
            "candidate": self.candidate,
            "confidence": self.confidence,
            "edits": [edit.to_dict() for edit in self.edits],
            "alternatives": list(self.alternatives),
        }


@dataclass(frozen=True, slots=True)
class Analysis(Sequence[Token]):
    """Segmentation tokens plus optional diagnostics for normalized text.

    ``Analysis`` behaves like a read-only token sequence so existing callers
    that iterate over or index the result of ``KhmerSegmenter.analyze`` keep
    working.
    """

    text: str
    tokens: tuple[Token, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    def __len__(self) -> int:
        return len(self.tokens)

    def __iter__(self) -> Iterator[Token]:
        return iter(self.tokens)

    @overload
    def __getitem__(self, index: int) -> Token: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Token, ...]: ...

    def __getitem__(self, index: int | slice) -> Token | tuple[Token, ...]:
        return self.tokens[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tokens": [token.to_dict() for token in self.tokens],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }
