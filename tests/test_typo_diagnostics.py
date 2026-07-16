import json
import tempfile
import unittest
from pathlib import Path

from khmer_segmenter import Analysis, KhmerSegmenter


class TypoDiagnosticTests(unittest.TestCase):
    def make_segmenter(self, directory: str) -> KhmerSegmenter:
        root = Path(directory)
        words = ["ស", "ត្ត", "សម្បត្តិ", "ក", "កា"]
        (root / "khmer_dictionary_words.txt").write_text(
            "\n".join(words) + "\n",
            encoding="utf-8",
        )
        (root / "khmer_word_frequencies.json").write_text(
            json.dumps(
                {"ស": 50, "ត្ត": 10, "សម្បត្តិ": 100, "ក": 50, "កា": 100},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "khmer_word_pos.json").write_text("{}\n", encoding="utf-8")
        return KhmerSegmenter.from_data_dir(root)

    def test_missing_vowel_diagnostic_covers_complete_probable_word(self):
        typo = "សម្បត្ត"
        correct = "សម្បត្តិ"
        with tempfile.TemporaryDirectory() as directory:
            segmenter = self.make_segmenter(directory)
            baseline = segmenter.segment(typo)
            analysis = segmenter.analyze(
                typo,
                typo_recovery=True,
                typo_min_confidence=0.5,
            )

        self.assertIsInstance(analysis, Analysis)
        self.assertEqual([token.text for token in analysis], baseline)
        self.assertEqual(len(analysis.diagnostics), 1)
        diagnostic = analysis.diagnostics[0]
        self.assertEqual((diagnostic.start, diagnostic.end), (0, len(typo)))
        self.assertEqual(diagnostic.surface, typo)
        self.assertEqual(diagnostic.candidate, correct)
        self.assertEqual(diagnostic.kind, "missing_dependent_vowel")
        self.assertGreater(diagnostic.confidence, 0.5)
        self.assertEqual(len(diagnostic.edits), 1)
        self.assertEqual(diagnostic.edits[0].operation, "insert")
        self.assertEqual(
            (diagnostic.edits[0].start, diagnostic.edits[0].end),
            (len(typo), len(typo)),
        )
        self.assertEqual(diagnostic.edits[0].text, "ិ")

    def test_typo_index_is_lazy_and_segmentation_remains_stable(self):
        typo = "សម្បត្ត"
        with tempfile.TemporaryDirectory() as directory:
            segmenter = self.make_segmenter(directory)
            baseline = segmenter.segment(typo)
            ordinary_analysis = segmenter.analyze(typo)
            self.assertIsNone(segmenter._missing_mark_index)

            typo_analysis = segmenter.analyze(typo, typo_recovery=True)
            self.assertIsNotNone(segmenter._missing_mark_index)
            after = segmenter.segment(typo)

        self.assertEqual([token.text for token in ordinary_analysis], baseline)
        self.assertEqual([token.text for token in typo_analysis], baseline)
        self.assertEqual(after, baseline)

    def test_valid_dictionary_surface_is_not_reported_as_typo(self):
        with tempfile.TemporaryDirectory() as directory:
            segmenter = self.make_segmenter(directory)
            # ក could be obtained by deleting ា from កា, but it is itself valid.
            analysis = segmenter.analyze("ក", typo_recovery=True)

        self.assertEqual(analysis.diagnostics, ())

    def test_diagnostic_does_not_cross_punctuation(self):
        typo = "សម្បត្ត"
        text = typo + "។"
        with tempfile.TemporaryDirectory() as directory:
            segmenter = self.make_segmenter(directory)
            analysis = segmenter.analyze(
                text,
                typo_recovery=True,
                typo_min_confidence=0.5,
            )

        self.assertEqual(len(analysis.diagnostics), 1)
        self.assertEqual(
            (analysis.diagnostics[0].start, analysis.diagnostics[0].end),
            (0, len(typo)),
        )

    def test_invalid_confidence_threshold_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            segmenter = self.make_segmenter(directory)
            with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                segmenter.analyze(
                    "សម្បត្ត",
                    typo_recovery=True,
                    typo_min_confidence=1.1,
                )

    def test_bundled_dictionary_detects_target_at_default_threshold(self):
        typo = "សម្បត្ត"
        segmenter = KhmerSegmenter()
        analysis = segmenter.analyze(typo, typo_recovery=True)

        self.assertEqual(len(analysis.diagnostics), 1)
        self.assertEqual(analysis.diagnostics[0].candidate, "សម្បត្តិ")


if __name__ == "__main__":
    unittest.main()
