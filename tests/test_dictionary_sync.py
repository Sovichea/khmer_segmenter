import tempfile
import unittest
from pathlib import Path

from scripts.sync_rac_dictionary import read_words


class DictionarySyncTests(unittest.TestCase):
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
