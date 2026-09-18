from pathlib import Path

from khmer_segmenter import KhmerSegmenter

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "khmer_segmenter" / "dictionary_data"


def test_runtime_policy_splits_long_compositions():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.segment("វាក្យសព្ទ", disable_post_processing=True) == [
        "វាក្យ",
        "សព្ទ",
    ]
    long_phrase = "ក្រុមហ៊ុនមហាជនទទួលខុសត្រូវមានកម្រិត"
    assert len(segmenter.segment(long_phrase, disable_post_processing=True)) > 1


def test_runtime_policy_keeps_lexicalized_compounds():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    for word in ("ត្រឹមត្រូវ", "បុរាណកាល", "មាតាបិតា", "ហ្វឹកហាត់"):
        assert segmenter.segment(word, disable_post_processing=True) == [word]


def test_runtime_policy_protects_headwords_and_curated_layers():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    keep = segmenter._composition_keep

    assert "ហ្វឹកហាត់" in keep
    assert "កង្កែបអាចម៍គោ" in keep
    assert segmenter.segment("កង្កែបអាចម៍គោ", disable_post_processing=True) == [
        "កង្កែបអាចម៍គោ"
    ]


def test_runtime_policy_can_be_disabled():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR, composition=False)

    assert segmenter.segment("វាក្យសព្ទ", disable_post_processing=True) == ["វាក្យសព្ទ"]


def test_autocomplete_cluster_cap_removes_long_phrases():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    capped = segmenter.complete_word("សញ្ញាបត្រ", max_suggestions=10, max_clusters=5)
    assert [item.text for item in capped] == ["សញ្ញាបត្រ"]

    uncapped = segmenter.complete_word("សញ្ញាបត្រ", max_suggestions=10, max_clusters=None)
    assert len(uncapped) > len(capped)


def test_composition_spellcheck_accepts_a_whole_span():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.is_valid_composition("បុរាណកាល")
    assert segmenter.is_valid_composition("វាក្យសព្ទ")
    assert segmenter.is_valid_composition("xyz") is False
    # Exact spelling is unchanged; composition is additive.
    assert segmenter.is_spelling_valid("វាក្យសព្ទ")
