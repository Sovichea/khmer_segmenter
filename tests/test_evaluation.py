import json
import unittest

from khmer_segmenter.evaluation import (
    boundary_offsets,
    derived_split,
    parse_khmer_alt_lines,
    parse_khpos_lines,
    parse_curated_jsonl,
)


class EvaluationTests(unittest.TestCase):
    def test_boundary_offsets(self):
        self.assertEqual(boundary_offsets(["ខ្ញុំ", "ចូលចិត្ត", "ភាសាខ្មែរ"]), {5, 13})

    def test_khpos_markers_are_not_surface_characters(self):
        record = next(parse_khpos_lines(["ក្រៅ_ពី/IN លោក~ស្រី/PRO តម្លា^ភាព/NN ./KAN\n"], split="all"))
        self.assertEqual(record["tokens"], ["ក្រៅពី", "លោកស្រី", "តម្លាភាព", "."])
        self.assertEqual(record["text"], "ក្រៅពីលោកស្រីតម្លាភាព.")
        self.assertEqual(record["metadata"]["pos_tags"], ["IN", "PRO", "NN", "KAN"])

    def test_derived_split_is_stable(self):
        self.assertEqual(derived_split("khpos", "42"), derived_split("khpos", "42"))
        self.assertIn(derived_split("khpos", "42"), {"train", "dev", "test"})

    def test_khmer_alt_id_and_tokens(self):
        record = next(parse_khmer_alt_lines(["SNT.1\tខ្ញុំ ចូលចិត្ត ភាសាខ្មែរ ។\n"], split="all"))
        self.assertEqual(record["tokens"], ["ខ្ញុំ", "ចូលចិត្ត", "ភាសាខ្មែរ", "។"])
        self.assertEqual(record["text"], "ខ្ញុំចូលចិត្តភាសាខ្មែរ។")
        self.assertEqual(record["metadata"]["source_id"], "SNT.1")

    def test_curated_loader_requires_approved_reconstructable_records(self):
        record = {
            "id": "curated-dev-001",
            "split": "dev",
            "text": "ភាសាខ្មែរ",
            "tokens": ["ភាសា", "ខ្មែរ"],
            "category": "education",
            "source": {
                "title": "Project-authored",
                "url": "project-authored",
                "license": "CC0-1.0",
                "attribution": "Khmer Segmenter contributors",
            },
            "review": {
                "status": "approved",
                "primary": "reviewer-1",
                "secondary": "reviewer-2",
                "adjudication_notes": "",
            },
        }
        parsed = list(parse_curated_jsonl([json.dumps(record, ensure_ascii=False)]))
        self.assertEqual(parsed[0]["dataset"], "khmer_segmenter_curated")
        self.assertEqual(parsed[0]["metadata"]["category"], "education")

        record["text"] = "ខុស"
        with self.assertRaisesRegex(ValueError, "do not reconstruct"):
            list(parse_curated_jsonl([json.dumps(record, ensure_ascii=False)]))


if __name__ == "__main__":
    unittest.main()
