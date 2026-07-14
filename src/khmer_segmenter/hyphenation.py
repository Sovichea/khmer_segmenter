"""Optional Khmer hyphenation backed by locally generated pairs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .data import DataNotFoundError, resolve_data_files


class KhmerHyphenator:
    """Apply locally generated safe break opportunities to segmented words."""

    def __init__(self, pairs_path: str | os.PathLike[str]):
        self.pairs_path = Path(pairs_path)
        if not self.pairs_path.is_file():
            raise DataNotFoundError(f"Hyphenation pairs not found: {self.pairs_path}")
        self._pairs: dict[str, str] = {}
        with self.pairs_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    word, hyphenated = line.split("\t", 1)
                except ValueError as error:
                    raise ValueError(
                        f"Invalid hyphenation pair at {self.pairs_path}:{line_number}"
                    ) from error
                self._pairs[word] = hyphenated.replace("-", "\u200b")

    @classmethod
    def from_data_dir(
        cls, data_dir: str | os.PathLike[str] | None = None
    ) -> "KhmerHyphenator":
        return cls(resolve_data_files(data_dir).hyphenation_pairs)

    def hyphenate_word(self, word: str, *, separator: str = "\u200b") -> str:
        return self._pairs.get(word, word).replace("\u200b", separator)

    def hyphenate_tokens(
        self, tokens: Iterable[str], *, separator: str = "\u200b"
    ) -> str:
        return "".join(self.hyphenate_word(token, separator=separator) for token in tokens)

    def hyphenate(
        self,
        text: str,
        *,
        segmenter: object,
        separator: str = "\u200b",
    ) -> str:
        tokens = segmenter.segment(text)  # type: ignore[attr-defined]
        return self.hyphenate_tokens(tokens, separator=separator)
