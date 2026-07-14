"""Public API for Khmer Segmenter."""

from importlib.metadata import PackageNotFoundError, version

from .data import DataFiles, DataNotFoundError
from .hyphenation import KhmerHyphenator
from .models import Token
from .preparation import prepare_dictionary
from .viterbi import KhmerSegmenter

try:
    __version__ = version("khmer-viterbi-segmenter")
except PackageNotFoundError:  # Running directly from a source checkout.
    __version__ = "0.1.0.dev0"

__all__ = [
    "DataFiles",
    "DataNotFoundError",
    "KhmerHyphenator",
    "KhmerSegmenter",
    "Token",
    "prepare_dictionary",
    "__version__",
]
