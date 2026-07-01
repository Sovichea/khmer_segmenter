import json
import tempfile
import unittest
from pathlib import Path

from khmer_segmenter import KhmerSegmenter


class MetadataTests(unittest.TestCase):
    def make_segmenter(self, directory):
        root = Path(directory)
        (root / "words.txt").write_text("ខ្ញុំ\nសរសេរ\n", encoding="utf-8")
        (root / "freq.json").write_text(
            json.dumps({"ខ្ញុំ": 20, "សរសេរ": 10}), encoding="utf-8"
        )
        (root / "pos.json").write_text(
            json.dumps({"ខ្ញុំ": ["PRO"], "សរសេរ": ["NN", "VB"]}),
            encoding="utf-8",
        )
        return KhmerSegmenter(root / "words.txt", root / "freq.json", root / "pos.json")

    def test_returns_unambiguous_and_ambiguous_pos(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = self.make_segmenter(directory).segment_with_metadata("ខ្ញុំសរសេរ")
        self.assertEqual([item["text"] for item in metadata], ["ខ្ញុំ", "សរសេរ"])
        self.assertEqual(metadata[0]["pos"], "PRO")
        self.assertEqual(metadata[1]["pos"], None)
        self.assertEqual(metadata[1]["pos_candidates"], ["NN", "VB"])
        self.assertEqual((metadata[1]["start"], metadata[1]["end"]), (5, 10))

    def test_unknown_never_gets_a_pos(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = self.make_segmenter(directory).segment_with_metadata("ABC")
        self.assertFalse(metadata[0]["known"])
        self.assertEqual(metadata[0]["type"], "unknown")
        self.assertIsNone(metadata[0]["pos"])


if __name__ == "__main__":
    unittest.main()
