import tempfile
import unittest
from pathlib import Path

from scripts.sync_rac_dictionary import read_words
from scripts.sync_typo_corrections import (
    DEFAULT_RUST_DESTINATION,
    DEFAULT_SOURCE,
    validate,
)


class DictionarySyncTests(unittest.TestCase):
    def test_typo_correction_data_is_valid_and_synchronized(self):
        self.assertEqual(validate(DEFAULT_SOURCE), {
            "approved": 167,
            "pending": 8,
            "rejected": 0,
        })
        self.assertEqual(
            DEFAULT_SOURCE.read_text(encoding="utf-8").splitlines(),
            DEFAULT_RUST_DESTINATION.read_text(encoding="utf-8").splitlines(),
        )

    def test_curated_spellcheck_vocabulary_is_synchronized_with_rust(self):
        root = Path(__file__).resolve().parents[1]
        python_words = (
            root
            / "src"
            / "khmer_segmenter"
            / "dictionary_data"
            / "khmer_spellcheck_words.txt"
        )
        rust_words = root / "port" / "rust" / "data" / "khmer_spellcheck_words.txt"
        self.assertEqual(
            python_words.read_text(encoding="utf-8").splitlines(),
            rust_words.read_text(encoding="utf-8").splitlines(),
        )

    def test_reads_first_tsv_column_and_normalizes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.tsv"
            source.write_text(
                "កករចិត្ត\tក-ក-ចិត\nខ្មែរ\tខ្មែ\n", encoding="utf-8"
            )
            words, rejected = read_words(source, tsv=True)
        self.assertEqual(words, ["កករចិត្ត", "ខ្មែរ"])
        self.assertNotIn("ក-ក-ចិត", words)
        self.assertEqual(rejected, 0)

    def test_rejects_phrase_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.tsv"
            source.write_text("ពាក្យ ពីរ\tdefinition\n", encoding="utf-8")
            words, rejected = read_words(source, tsv=True)
        self.assertEqual(words, [])
        self.assertEqual(rejected, 1)


if __name__ == "__main__":
    unittest.main()
