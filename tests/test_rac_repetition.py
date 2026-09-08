import csv
from pathlib import Path

from khmer_segmenter import KhmerSegmenter

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "khmer_segmenter" / "dictionary_data"


def test_target_repetition_segmentations():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    cases = {
        "នីមួយ": ["នីមួយ"],
        "នីមួយៗ": ["នីមួយៗ"],
        "មួយ": ["មួយ"],
        "មួយៗ": ["មួយៗ"],
        "ម្នាក់": ["ម្នាក់"],
        "ម្នាក់ៗ": ["ម្នាក់ៗ"],
        "មនុស្សម្នាក់ៗ": ["មនុស្ស", "ម្នាក់ៗ"],
        "មនុស្សជាតិនីមួយៗ": ["មនុស្សជាតិ", "នីមួយៗ"],
        "ពាក្យផ្សេងៗគ្នា": ["ពាក្យ", "ផ្សេងៗ", "គ្នា"],
    }
    for text, expected in cases.items():
        assert segmenter.segment(text, disable_post_processing=True) == expected


def test_every_trusted_repetition_form_is_one_token():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    words = sorted(
        word
        for word in (DATA_DIR / "khmer_dictionary_words.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if "ៗ" in word
    )
    assert len(words) == 716
    assert all(segmenter.segment(word, disable_post_processing=True) == [word] for word in words)


def test_spellcheck_lexicon_is_separate_from_segmentation_lexicon():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    assert segmenter.is_spelling_valid("មួយៗ")
    assert segmenter.is_spelling_valid("ម្នាក់ៗ")
    spellcheck_only = segmenter.spellcheck_words - segmenter.words
    assert len(spellcheck_only) >= 725
    assert segmenter.rac_phrase_exclusions <= spellcheck_only
    assert all(segmenter.is_spelling_valid(word, normalize=False) for word in spellcheck_only)


def test_supplemental_runtime_dictionary_is_segmentation_only():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)
    supplemental = segmenter.supplemental_words
    assert supplemental
    assert supplemental <= segmenter.words
    segmentation_only = supplemental - (
        segmenter.author_curated_words
        | segmenter.rac_derived_words
        | segmenter.rac_usage_words
    )
    assert all(not segmenter.is_spelling_valid(word) for word in segmentation_only)
    assert supplemental & segmenter.author_curated_words == {"រ៉ុក្កែត"}


def test_reviewed_rac_phrase_components_are_valid_but_phrases_segment():
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert segmenter.segment("សាកល្បង", disable_post_processing=True) == ["សាកល្បង"]
    assert segmenter.is_spelling_valid("សាកល្បង")
    assert segmenter.segment("ប្រឡងសាកល្បង", disable_post_processing=True) == [
        "ប្រឡង",
        "សាកល្បង",
    ]
    # The original RAC expression remains accepted as correctly spelled even
    # though it is no longer forced into one segmentation token.
    assert segmenter.is_spelling_valid("ប្រឡងសាកល្បង")

    assert segmenter.rac_derived_words <= segmenter.words
    assert all(segmenter.is_spelling_valid(word) for word in segmenter.rac_derived_words)
    assert not (segmenter.rac_phrase_exclusions & segmenter.words)


def test_rac_derived_word_list_matches_definition_review():
    review_path = DATA_DIR / "khmer_dictionary_rac_derived_review.tsv"
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    approved = {row["word"] for row in rows if row["status"] == "approved"}
    rejected = {row["word"] for row in rows if row["status"] == "rejected"}
    promoted = set(
        (DATA_DIR / "khmer_dictionary_rac_derived_words.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert len(rows) == 32
    assert len(approved) == 21
    assert len(rejected) == 11
    assert promoted == approved
    assert not promoted & rejected
    assert all(row["rac_evidence"] and row["definition_check"] for row in rows)


def test_rac_definition_and_example_words_match_review():
    review_path = DATA_DIR / "khmer_dictionary_rac_usage_review.tsv"
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    approved = {row["word"] for row in rows if row["status"] == "approved"}
    rejected = {row["word"] for row in rows if row["status"] == "rejected"}
    promoted = set(
        (DATA_DIR / "khmer_dictionary_rac_usage_words.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    segmenter = KhmerSegmenter(data_dir=DATA_DIR)

    assert len(approved) == 32
    assert promoted == approved
    assert not promoted & rejected
    assert promoted <= segmenter.rac_usage_words <= segmenter.words
    assert all(segmenter.is_spelling_valid(word) for word in promoted)
    assert all(
        segmenter.segment(word, disable_post_processing=True) == [word]
        for word in promoted
    )
    assert {"មេរៀន", "ញូតុន", "អេឡិចត្រូត"} <= promoted
    assert "ទូរស័ព្ទ" in rejected
    assert "ទូរស័ព្ទ" not in promoted
    assert segmenter.is_spelling_valid("ទូរសព្ទ")
    assert all(row["rac_evidence"] and row["review_note"] for row in rows)


def test_spellcheck_cli(capsys):
    from khmer_segmenter.cli import main

    assert main(["--data-dir", str(DATA_DIR), "spellcheck", "មួយៗ"]) == 0
    assert capsys.readouterr().out.strip() == "valid\tមួយៗ"
