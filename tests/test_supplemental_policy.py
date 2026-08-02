import json
from pathlib import Path

from khmer_segmenter import KhmerSegmenter
from khmer_segmenter.preparation import decompose_supplemental_words


def test_phrase_like_supplemental_entries_are_reduced_to_unknown_chunks():
    curated = {"កម្ពុជា", "សាលា"}
    supplemental, decisions = decompose_supplemental_words(
        {
            "កម្ពុជាសាលា",
            "កម្ពុជាហ៊ូរសាលា",
            "ក",
            "កខគឃងច",
            "សសេរ",
        },
        curated,
        reviewed_typos={"សសេរ"},
    )

    assert supplemental == {"ហ៊ូរ", "សសេរ"}
    assert any(
        decision.chunk == "កម្ពុជាសាលា" and decision.reason == "curated_chunk"
        for decision in decisions
    ) is False
    assert any(decision.reason == "single_cluster_fragment" for decision in decisions)
    assert any(decision.reason == "long_unresolved_span" for decision in decisions)


def test_supplemental_word_segments_but_remains_a_spelling_error(tmp_path: Path):
    (tmp_path / "khmer_dictionary_words.txt").write_text("ជំរុញ\n", encoding="utf-8")
    (tmp_path / "khmer_dictionary_official_2022_words.txt").write_text(
        "ជំរុញ\n", encoding="utf-8"
    )
    (tmp_path / "khmer_dictionary_supplemental_words.txt").write_text(
        "ជម្រុញ\n", encoding="utf-8"
    )
    (tmp_path / "khmer_spellcheck_words.txt").write_text("ជំរុញ\n", encoding="utf-8")
    (tmp_path / "khmer_word_frequencies.json").write_text(
        json.dumps({"ជំរុញ": 100}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "khmer_typo_corrections.tsv").write_text(
        "id\tstatus\ttyped\tcorrection\texpectation\tsource_id\tnote\n"
        "test-001\tapproved\tជម្រុញ\tជំរុញ\texact\ttest\ttest\n",
        encoding="utf-8",
    )

    segmenter = KhmerSegmenter(data_dir=tmp_path)

    assert segmenter.segment("ជម្រុញ", disable_post_processing=True) == ["ជម្រុញ"]
    assert segmenter.is_spelling_valid("ជម្រុញ") is False
    assert segmenter.segment_with_metadata("ជម្រុញ")[0]["source"] == "supplemental"
    assert segmenter.detect_typos("ជម្រុញ")[0].suggestions[0].text == "ជំរុញ"


def test_completion_uses_only_curated_spellcheck_words(tmp_path: Path):
    (tmp_path / "khmer_dictionary_words.txt").write_text("កម្ពុជា\n", encoding="utf-8")
    (tmp_path / "khmer_dictionary_official_2022_words.txt").write_text(
        "កម្ពុជា\n", encoding="utf-8"
    )
    (tmp_path / "khmer_dictionary_supplemental_words.txt").write_text(
        "កម្ពុជាថ្មី\n", encoding="utf-8"
    )
    (tmp_path / "khmer_spellcheck_words.txt").write_text("កម្ពុជា\n", encoding="utf-8")

    segmenter = KhmerSegmenter(data_dir=tmp_path)

    assert [item.text for item in segmenter.complete_word("កម្ពុ")] == ["កម្ពុជា"]


def test_exact_curated_word_beats_supplemental_partition(tmp_path: Path):
    (tmp_path / "khmer_dictionary_words.txt").write_text("កខគឃ\n", encoding="utf-8")
    (tmp_path / "khmer_dictionary_official_2022_words.txt").write_text(
        "កខគឃ\n", encoding="utf-8"
    )
    (tmp_path / "khmer_dictionary_supplemental_words.txt").write_text(
        "កខ\nគឃ\n", encoding="utf-8"
    )
    (tmp_path / "khmer_spellcheck_words.txt").write_text("កខគឃ\n", encoding="utf-8")

    segmenter = KhmerSegmenter(data_dir=tmp_path)

    assert segmenter.get_word_cost("កខ") > segmenter.get_word_cost("កខគឃ")
    assert segmenter.segment("កខគឃ", disable_post_processing=True) == ["កខគឃ"]
