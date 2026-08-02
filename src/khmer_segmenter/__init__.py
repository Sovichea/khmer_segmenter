"""Public API for Khmer Segmenter."""

from importlib.metadata import PackageNotFoundError, version

from .data import DataFiles, DataNotFoundError
from .hyphenation import KhmerHyphenator
from .kdict import KDict, KDictWord, compile_klex
from .models import (
    EditOperation,
    SpellcheckConfig,
    SpellcheckProfile,
    SpellingDiagnostic,
    SpellingSuggestion,
    Token,
)
from .preparation import prepare_dictionary
from .viterbi import KhmerSegmenter

try:
    __version__ = version("khmer-viterbi-segmenter")
except PackageNotFoundError:  # Running directly from a source checkout.
    __version__ = "0.2.0rc1"

__all__ = [
    "DataFiles",
    "DataNotFoundError",
    "KhmerHyphenator",
    "KhmerSegmenter",
    "KDict",
    "KDictWord",
    "compile_klex",
    "EditOperation",
    "SpellcheckConfig",
    "SpellcheckProfile",
    "SpellingDiagnostic",
    "SpellingSuggestion",
    "Token",
    "prepare_dictionary",
    "__version__",
]
