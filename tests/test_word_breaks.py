import json
from pathlib import Path

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.cli import main

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "khmer_segmenter" / "dictionary_data"


def test_word_breaks_use_original_source_offsets():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    text = "ខ្មែរស្រឡាញ់ខ្មែរ"

    assert segmenter.segment(text) == ["ខ្មែរ", "ស្រឡាញ់", "ខ្មែរ"]
    assert segmenter.word_break_opportunities(text) == (5, 12)
    assert segmenter.insert_word_breaks(text) == "ខ្មែរ\u200bស្រឡាញ់\u200bខ្មែរ"


def test_word_breaks_skip_existing_breaks_whitespace_punctuation_and_unknowns():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.insert_word_breaks("ខ្មែរ\u200bស្រឡាញ់") == "ខ្មែរ\u200bស្រឡាញ់"
    assert segmenter.insert_word_breaks("ខ្មែរ ស្រឡាញ់។") == "ខ្មែរ ស្រឡាញ់។"
    assert segmenter.insert_word_breaks("ខ្មែរabcស្រឡាញ់") == "ខ្មែរabcស្រឡាញ់"
    assert segmenter.insert_word_breaks("ខ្មែរ១២ស្រឡាញ់") == "ខ្មែរ១២ស្រឡាញ់"


def test_composition_breaks_are_offered_inside_compositions():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    # Whole frequency does not exceed the frequency of the parts, so these are
    # compositions and may wrap even though they are single dictionary words.
    assert segmenter.insert_word_breaks("ត្រូវការ") == "ត្រូវ\u200bការ"
    assert segmenter.insert_word_breaks("ខូចខាត") == "ខូច\u200bខាត"
    assert segmenter.insert_word_breaks("របាយការណ៍") == "របាយ\u200bការណ៍"
    assert segmenter.word_break_opportunities("របាយការណ៍") == (4,)


def test_composition_breaks_reject_letter_and_syllable_splits():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    # No break may isolate a bare letter or a single-cluster syllable.
    for word in ("កសាង", "សាលា", "កំសាក", "សរសេរ"):
        assert segmenter.segment(word, disable_post_processing=True) == [word]
        assert segmenter.word_break_opportunities(word) == ()
        assert segmenter.insert_word_breaks(word) == word


def test_single_consonant_token_never_creates_a_break(tmp_path: Path):
    (tmp_path / "khmer_dictionary_words.txt").write_text("ក\nសាង\n", encoding="utf-8")
    (tmp_path / "khmer_spellcheck_words.txt").write_text("ក\nសាង\n", encoding="utf-8")
    segmenter = KhmerSegmenter(data_dir=tmp_path)

    assert segmenter.segment("កសាង", disable_post_processing=True) == ["ក", "សាង"]
    assert segmenter.word_break_opportunities("កសាង") == ()
    assert segmenter.insert_word_breaks("កសាង") == "កសាង"


def test_composition_breaks_do_not_duplicate_existing_breaks():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.insert_word_breaks("របាយ\u200bការណ៍") == "របាយ\u200bការណ៍"
    once = segmenter.insert_word_breaks("របាយការណ៍ត្រូវការ")
    assert once == "របាយ\u200bការណ៍\u200bត្រូវ\u200bការ"
    assert segmenter.insert_word_breaks(once) == once


def test_composition_breaks_are_optional():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    text = "របាយការណ៍"

    assert segmenter.insert_word_breaks(text) == "របាយ\u200bការណ៍"
    assert segmenter.insert_word_breaks(text, allow_composition_breaks=False) == text
    assert segmenter.word_break_opportunities(
        text, allow_composition_breaks=False
    ) == ()


def test_word_breaks_cli_plain_and_json(capsys):
    text = "ខ្មែរស្រឡាញ់ខ្មែរ"
    assert main(["--data-dir", str(DATA_DIR), "word-breaks", text]) == 0
    assert capsys.readouterr().out.strip() == "ខ្មែរ\u200bស្រឡាញ់\u200bខ្មែរ"

    assert (
        main(
            [
                "--data-dir",
                str(DATA_DIR),
                "word-breaks",
                text,
                "--format",
                "json",
            ]
        )
        == 0
    )
    records = json.loads(capsys.readouterr().out)
    assert records == [
        {
            "text": text,
            "break_offsets": [5, 12],
            "output": "ខ្មែរ\u200bស្រឡាញ់\u200bខ្មែរ",
        }
    ]
