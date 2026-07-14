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
