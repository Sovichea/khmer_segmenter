from pathlib import Path

from khmer_segmenter import KhmerSegmenter, SpellingAuthority

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "khmer_segmenter" / "dictionary_data"


def test_official_authority_keeps_community_variants_invalid():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.is_spelling_valid("ឱ្យ")
    assert not segmenter.is_spelling_valid("អោយ")
    assert not segmenter.is_spelling_valid("ឲ្យ")


def test_community_authority_accepts_reviewed_variants():
    segmenter = KhmerSegmenter(
        data_dir=DATA_DIR, spelling_authority=SpellingAuthority.COMMUNITY
    )

    for word in ("ឱ្យ", "អោយ", "ឲ្យ"):
        assert segmenter.is_spelling_valid(word)
    assert "អោយ" in segmenter.autocomplete_words
    assert "ឲ្យ" in segmenter.autocomplete_words
    assert segmenter.segment("អោយ", disable_post_processing=True) == ["អោយ"]
    assert segmenter.segment("ឲ្យ", disable_post_processing=True) == ["ឲ្យ"]


def test_community_authority_accepts_a_string_value():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR, spelling_authority="community")

    assert segmenter.is_spelling_valid("ឲ្យ")


def test_community_variants_are_offered_as_completions():
    official = KhmerSegmenter(data_dir=DATA_DIR)
    community = KhmerSegmenter(
        data_dir=DATA_DIR, spelling_authority=SpellingAuthority.COMMUNITY
    )

    assert "ឲ្យ" not in {item.text for item in official.complete_word("ឲ")}
    assert "ឲ្យ" in {item.text for item in community.complete_word("ឲ")}
