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
    assert len(spellcheck_only) == 725
    assert all(segmenter.is_spelling_valid(word, normalize=False) for word in spellcheck_only)


def test_supplemental_runtime_dictionary_is_empty():
    supplemental = DATA_DIR / "khmer_dictionary_supplemental_words.txt"
    assert supplemental.read_text(encoding="utf-8") == ""


def test_spellcheck_cli_and_hyphenation_data(capsys):
    from khmer_segmenter.cli import main
    from khmer_segmenter.hyphenation import KhmerHyphenator

    assert main(["--data-dir", str(DATA_DIR), "spellcheck", "មួយៗ"]) == 0
    assert capsys.readouterr().out.strip() == "valid\tមួយៗ"

    hyphenator = KhmerHyphenator.from_data_dir(DATA_DIR)
    assert hyphenator.hyphenate_word("កក់ក្ដៅ", separator="-") == "កក់-ក្ដៅ"
