"""Unit checks for corpus experiment filters that do not require downloads."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "experiment_hf_corpora.py"
SPEC = importlib.util.spec_from_file_location("experiment_hf_corpora", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_compact_text_removes_invisible_joiners_and_limits_length():
    assert MODULE.compact_text(" ខ្មែរ\u200b  ល្អ \n\n ទេ ", 10) == "ខ្មែរ ល្អ\n"


def test_khmer_ratio_rejects_latin_only_text():
    assert MODULE.khmer_ratio("English only") == 0.0
    assert MODULE.khmer_ratio("ភាសាខ្មែរ") == 1.0


def test_chunks_preserve_the_input_text_except_boundary_whitespace():
    text = "ភាសាខ្មែរ។ អត្ថបទថ្មី!"
    assert "".join(MODULE.iter_chunks(text)).replace(" ", "") == text.replace(" ", "")


def test_digest_is_stable():
    assert MODULE.stable_digest("ខ្មែរ") == MODULE.stable_digest("ខ្មែរ")
    assert MODULE.stable_digest("ខ្មែរ") != MODULE.stable_digest("ភាសា")


def test_unknown_candidate_filter_excludes_khmer_numbers_and_punctuation():
    class SegmenterStub:
        words = {"ខ្មែរ"}

        @staticmethod
        def _is_digit(token):
            return token.isdigit()

        @staticmethod
        def _is_separator(token):
            return token in {"។", "៖"}

    segmenter = SegmenterStub()
    assert MODULE.is_unknown_lexical_token(segmenter, "ពាក្យថ្មី")
    assert not MODULE.is_unknown_lexical_token(segmenter, "ខ្មែរ")
    assert not MODULE.is_unknown_lexical_token(segmenter, "១២")
    assert not MODULE.is_unknown_lexical_token(segmenter, "។")
