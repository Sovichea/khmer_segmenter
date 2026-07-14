import json
import tempfile
import unittest
from pathlib import Path

from khmer_segmenter import KhmerHyphenator, KhmerSegmenter, Token, prepare_dictionary


class PublicApiTests(unittest.TestCase):
    def make_data(self, directory: str) -> Path:
        root = Path(directory)
        (root / "khmer_dictionary_words.txt").write_text(
            "កម្ពុជា\nស្រឡាញ់\n", encoding="utf-8"
        )
        (root / "khmer_word_frequencies.json").write_text(
            json.dumps({"កម្ពុជា": 20, "ស្រឡាញ់": 10}, ensure_ascii=False),
            encoding="utf-8",
        )
        (root / "khmer_word_pos.json").write_text(
            json.dumps({"កម្ពុជា": ["NNP"]}, ensure_ascii=False), encoding="utf-8"
        )
        (root / "khmer_dictionary_hyphenation_pairs.txt").write_text(
            "កម្ពុជា\tកម្ពុ-ជា\n", encoding="utf-8"
        )
        return root

    def test_from_data_dir_and_typed_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_data(directory)
            segmenter = KhmerSegmenter.from_data_dir(root)
            tokens = segmenter.segment("ស្រឡាញ់កម្ពុជា")
            analysis = segmenter.analyze("ស្រឡាញ់កម្ពុជា")
        self.assertEqual(tokens, ["ស្រឡាញ់", "កម្ពុជា"])
        self.assertTrue(all(isinstance(token, Token) for token in analysis))
        self.assertEqual(analysis[1].pos, "NNP")

    def test_hyphenation_uses_segmented_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_data(directory)
            segmenter = KhmerSegmenter.from_data_dir(root)
            hyphenator = KhmerHyphenator.from_data_dir(root)
            result = hyphenator.hyphenate(
                "ស្រឡាញ់កម្ពុជា", segmenter=segmenter, separator="-"
            )
        self.assertEqual(result, "ស្រឡាញ់កម្ពុ-ជា")

    def test_prepare_dictionary_from_user_obtained_tsv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pairs.tsv"
            output = root / "runtime"
            source.write_text("កម្ពុជា\tdefinition\nស្រឡាញ់\tdefinition\n", encoding="utf-8")
            report = prepare_dictionary(source, output)
            words = (output / "khmer_dictionary_words.txt").read_text(
                encoding="utf-8"
            )
        self.assertIn("កម្ពុជា", words)
        self.assertEqual(report["counts"]["official_headwords"], 2)


if __name__ == "__main__":
    unittest.main()
