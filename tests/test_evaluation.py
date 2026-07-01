import unittest

from khmer_segmenter.evaluation import (
    boundary_offsets,
    derived_split,
    parse_khmer_alt_lines,
    parse_khpos_lines,
)


class EvaluationTests(unittest.TestCase):
    def test_boundary_offsets(self):
        self.assertEqual(boundary_offsets(["ខ្ញុំ", "ចូលចិត្ត", "ភាសាខ្មែរ"]), {5, 13})

    def test_khpos_markers_are_not_surface_characters(self):
        record = next(parse_khpos_lines(
            ["ក្រៅ_ពី/IN លោក~ស្រី/PRO តម្លា^ភាព/NN ./KAN\n"], split="all"
        ))
        self.assertEqual(record["tokens"], ["ក្រៅពី", "លោកស្រី", "តម្លាភាព", "."])
        self.assertEqual(record["text"], "ក្រៅពីលោកស្រីតម្លាភាព.")
        self.assertEqual(record["metadata"]["pos_tags"], ["IN", "PRO", "NN", "KAN"])

    def test_derived_split_is_stable(self):
        self.assertEqual(derived_split("khpos", "42"), derived_split("khpos", "42"))
        self.assertIn(derived_split("khpos", "42"), {"train", "dev", "test"})

    def test_khmer_alt_id_and_tokens(self):
        record = next(parse_khmer_alt_lines(
            ["SNT.1\tខ្ញុំ ចូលចិត្ត ភាសាខ្មែរ ។\n"], split="all"
        ))
        self.assertEqual(record["tokens"], ["ខ្ញុំ", "ចូលចិត្ត", "ភាសាខ្មែរ", "។"])
        self.assertEqual(record["text"], "ខ្ញុំចូលចិត្តភាសាខ្មែរ។")
        self.assertEqual(record["metadata"]["source_id"], "SNT.1")


if __name__ == "__main__":
    unittest.main()
