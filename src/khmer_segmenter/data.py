"""Resolve bundled or user-supplied Khmer linguistic data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DATA_DIR_ENV = "KHMER_SEGMENTER_DATA_DIR"
DICTIONARY_SOURCE_URL = (
    "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k"
)
DICTIONARY_SOURCE_CREDIT = "Seanghay Hay (Hugging Face user seanghay)"
BUNDLED_DATA_DIR = Path(__file__).resolve().parent / "dictionary_data"


class DataNotFoundError(FileNotFoundError):
    """Raised when required local linguistic data cannot be located."""


@dataclass(frozen=True, slots=True)
class DataFiles:
    """Conventional local paths used by the Python implementation."""

    root: Path

    @property
    def dictionary(self) -> Path:
        return self.root / "khmer_dictionary_words.txt"

    @property
    def frequencies(self) -> Path:
        return self.root / "khmer_word_frequencies.json"

    @property
    def lexical_pos(self) -> Path:
        return self.root / "khmer_word_pos.json"

    @property
    def official_words(self) -> Path:
        return self.root / "khmer_dictionary_official_2022_words.txt"

    @property
    def supplemental_words(self) -> Path:
        return self.root / "khmer_dictionary_supplemental_words.txt"

    @property
    def hyphenation_pairs(self) -> Path:
        return self.root / "khmer_dictionary_hyphenation_pairs.txt"

    def status(self) -> dict[str, bool]:
        return {
            "dictionary": self.dictionary.is_file(),
            "frequencies": self.frequencies.is_file(),
            "lexical_pos": self.lexical_pos.is_file(),
            "hyphenation_pairs": self.hyphenation_pairs.is_file(),
        }


def user_data_dir() -> Path:
    """Return a dependency-free, platform-appropriate user data directory."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "khmer_segmenter"
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Application Support" / "khmer_segmenter"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "khmer_segmenter"


def sys_platform() -> str:
    # Kept in a tiny function so path behavior is straightforward to test.
    import sys

    return sys.platform


def candidate_data_dirs(explicit: str | os.PathLike[str] | None = None) -> list[Path]:
    """Return data locations in resolution order, without requiring existence."""

    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    else:
        env_path = os.environ.get(DATA_DIR_ENV)
        if env_path:
            candidates.append(Path(env_path).expanduser())
        candidates.extend(
            [
                user_data_dir(),
                BUNDLED_DATA_DIR,
                Path.cwd() / "khmer_segmenter" / "dictionary_data",
                Path.cwd() / "dictionary_data",
            ]
        )
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def resolve_data_files(
    data_dir: str | os.PathLike[str] | None = None,
    *,
    require_dictionary: bool = True,
) -> DataFiles:
    """Resolve local data, raising an actionable error when it is unavailable."""

    candidates = candidate_data_dirs(data_dir)
    for candidate in candidates:
        files = DataFiles(candidate)
        if not require_dictionary or files.dictionary.is_file():
            return files
    searched = "\n  - ".join(str(path) for path in candidates)
    raise DataNotFoundError(
        "Khmer dictionary data could not be found.\n"
        f"Searched:\n  - {searched}\n"
        f"Set {DATA_DIR_ENV}, pass data_dir=..., or prepare the dictionary from:\n"
        f"  {DICTIONARY_SOURCE_URL}"
    )
