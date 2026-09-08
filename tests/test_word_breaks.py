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
