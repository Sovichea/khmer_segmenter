import json
import tempfile
import unittest
from pathlib import Path

from khmer_segmenter import KhmerHyphenator, KhmerSegmenter, Token, prepare_dictionary
from khmer_segmenter.data import resolve_data_files


class PublicApiTests(unittest.TestCase):
    def test_bundled_runtime_data_is_ready(self):
        files = resolve_data_files()
        self.assertTrue(files.dictionary.is_file())
        self.assertTrue(files.frequencies.is_file())
        self.assertTrue(files.lexical_pos.is_file())
        self.assertTrue(files.spellcheck_words.is_file())
        self.assertTrue(files.model_manifest.is_file())
        self.assertTrue(files.hyphenation_pairs.is_file())

        segmenter = KhmerSegmenter()
        hyphenator = KhmerHyphenator.from_data_dir()
        self.assertGreater(len(segmenter.words), 1_000)
        self.assertGreater(len(segmenter.word_frequencies), 1_000)
        self.assertGreater(len(segmenter.pos_tags), 100)
        self.assertEqual(segmenter.data_manifest["model_id"], "rac-2022-layered-v1")
        self.assertGreater(len(hyphenator._pairs), 1_000)

    def make_data(self, directory: str) -> Path:
        root = Path(directory)
        (root / "khmer_dictionary_words.txt").write_text("កម្ពុជា\nស្រឡាញ់\n", encoding="utf-8")
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
        self.assertTrue(all(token.spelling_valid for token in analysis))

    def test_old_custom_data_dir_uses_dictionary_for_spellcheck(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_data(directory)
            segmenter = KhmerSegmenter.from_data_dir(root)
            result = segmenter.check_spelling(["កម្ពុជា", "មិនមានក្នុងវចនានុក្រម"])
        self.assertEqual(
            result,
            [
                {"word": "កម្ពុជា", "valid": True},
                {"word": "មិនមានក្នុងវចនានុក្រម", "valid": False},
            ],
        )

    def test_hyphenation_uses_segmented_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_data(directory)
            segmenter = KhmerSegmenter.from_data_dir(root)
            hyphenator = KhmerHyphenator.from_data_dir(root)
            result = hyphenator.hyphenate("ស្រឡាញ់កម្ពុជា", segmenter=segmenter, separator="-")
        self.assertEqual(result, "ស្រឡាញ់កម្ពុ-ជា")

    def test_prepare_dictionary_from_user_obtained_tsv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pairs.tsv"
            output = root / "runtime"
            source.write_text("កម្ពុជា\tdefinition\nស្រឡាញ់\tdefinition\n", encoding="utf-8")
            report = prepare_dictionary(source, output)
            words = (output / "khmer_dictionary_words.txt").read_text(encoding="utf-8")
        self.assertIn("កម្ពុជា", words)
        self.assertEqual(report["counts"]["official_headwords"], 2)


if __name__ == "__main__":
    unittest.main()
