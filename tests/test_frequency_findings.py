import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "khmer_segmenter" / "dictionary_data"


def test_focus_frequencies():
    frequencies = json.loads((DATA_DIR / "khmer_word_frequencies.json").read_text(encoding="utf-8"))
    assert {
        word: frequencies.get(word) for word in ("នីមួយ", "នីមួយៗ", "មួយ", "មួយៗ", "ម្នាក់", "ម្នាក់ៗ")
    } == {
        "នីមួយ": 42,
        "នីមួយៗ": 142,
        "មួយ": 6223,
        "មួយៗ": 115,
        "ម្នាក់": 511,
        "ម្នាក់ៗ": 74,
    }


def test_runtime_data_counts():
    def lines(name):
        return sum(1 for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines() if line)

    assert lines("khmer_dictionary_words.txt") == 37341
    assert lines("khmer_spellcheck_words.txt") == 38066
    frequencies = json.loads((DATA_DIR / "khmer_word_frequencies.json").read_text(encoding="utf-8"))
    assert len(frequencies) == 25401
