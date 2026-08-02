import json

import pytest

from khmer_segmenter import (
    EditOperation,
    KhmerSegmenter,
    SpellcheckConfig,
    SpellcheckProfile,
    SpellingDiagnostic,
    SpellingSuggestion,
)
from khmer_segmenter.spelling import load_approved_typo_corrections


MISSPELLED = "\u179f\u1798\u17d2\u1794\u178f\u17d2\u178f"
CORRECT = MISSPELLED + "\u17b7"
LEGACY_GIVE = "\u17b2\u17d2\u1799"
RAC_GIVE = "\u17b1\u17d2\u1799"
MISSPELLED_WHICH = "\u178a\u179b"
CORRECT_WHICH = "\u178a\u17c2\u179b"
TYPO_CASES = [
    (
        "\u179f\u17bd\u179a\u179f\u17d2\u178f\u17b8",
        "\u179f\u17bd\u179f\u17d2\u178a\u17b8",
    ),
    ("\u1787\u1798\u17d2\u179a\u17bb\u1789", "\u1787\u17c6\u179a\u17bb\u1789"),
    (
        "\u1794\u17d2\u179a\u17a0\u17c1\u179f",
        "\u1794\u17d2\u179a\u17a0\u17c2\u179f",
    ),
    ("\u179f\u179f\u17c1\u179a", "\u179f\u179a\u179f\u17c1\u179a"),
    (
        "\u179a\u179f\u17cb\u1787\u17b6\u178f\u17b7",
        "\u179a\u179f\u1787\u17b6\u178f\u17b7",
    ),
]


@pytest.fixture(scope="module")
def segmenter():
    return KhmerSegmenter()


def test_detects_whole_typo_span_across_fragmented_tokens(segmenter):
    tokens = segmenter.analyze(MISSPELLED)
    assert [token.text for token in tokens] == [MISSPELLED[0], MISSPELLED[1:]]

    diagnostics = segmenter.detect_typos(MISSPELLED)

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert isinstance(diagnostic, SpellingDiagnostic)
    assert (diagnostic.text, diagnostic.start, diagnostic.end) == (MISSPELLED, 0, 7)
    assert diagnostic.kind == "missing_dependent_vowel"
    assert diagnostic.suggestions[0].text == CORRECT


def test_typo_edit_uses_absolute_normalized_offsets(segmenter):
    text = "\u17d4" + MISSPELLED + "\u17d4"
    diagnostic = segmenter.detect_typos(text)[0]
    suggestion = diagnostic.suggestions[0]
    edit = suggestion.edits[0]

    assert isinstance(suggestion, SpellingSuggestion)
    assert isinstance(edit, EditOperation)
    assert (diagnostic.start, diagnostic.end) == (1, 8)
    assert (edit.kind, edit.start, edit.end, edit.text) == ("insert", 8, 8, "\u17b7")


def test_valid_word_has_no_typo_diagnostic(segmenter):
    assert segmenter.detect_typos(CORRECT) == []


def test_base_substitution_requires_expanded_threshold(segmenter):
    assert segmenter.detect_typos(LEGACY_GIVE) == []
    diagnostics = segmenter.detect_typos(LEGACY_GIVE, max_edit_cost=1.0)
    assert diagnostics[0].suggestions[0].text == RAC_GIVE


def test_detects_missing_vowel_when_all_fragments_are_known(segmenter):
    assert all(token.spelling_valid for token in segmenter.analyze(MISSPELLED_WHICH))
    assert segmenter.check_text(MISSPELLED_WHICH, profile="typing") == []
    diagnostic = segmenter.check_text(MISSPELLED_WHICH, profile="high-recall")[0]
    assert (diagnostic.start, diagnostic.end) == (0, len(MISSPELLED_WHICH))
    assert diagnostic.suggestions[0].text == CORRECT_WHICH


def test_spellcheck_profiles_have_stable_cross_port_settings(segmenter):
    assert SpellcheckConfig.for_profile(SpellcheckProfile.TYPING) == SpellcheckConfig(
        0.75, 3, 1, False, 0.80
    )
    assert SpellcheckConfig.for_profile("document") == SpellcheckConfig(
        1.00, 5, 1, False, 0.75
    )
    assert SpellcheckConfig.for_profile("high-recall") == SpellcheckConfig(
        1.50, 5, 1, True, 0.0
    )


def test_unknown_spellcheck_profile_is_rejected(segmenter):
    with pytest.raises(ValueError, match="unknown spellcheck profile"):
        segmenter.check_text(MISSPELLED, profile="aggressive")


def test_diagnose_cli_reports_selected_profile(capsys):
    from khmer_segmenter.cli import main

    assert main(["diagnose", MISSPELLED, "--profile", "typing"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["profile"] == "typing"
    assert payload[0]["diagnostics"][0]["suggestions"][0]["text"] == CORRECT


def test_diagnostic_serializes_to_json(segmenter):
    payload = segmenter.detect_typos(MISSPELLED)[0].to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert CORRECT in encoded
    assert payload["suggestions"][0]["edits"][0]["start"] == 7


def test_typo_detection_rejects_invalid_limits(segmenter):
    with pytest.raises(ValueError, match="max_edit_cost"):
        segmenter.detect_typos(MISSPELLED, max_edit_cost=0)
    with pytest.raises(ValueError, match="max_suggestions"):
        segmenter.detect_typos(MISSPELLED, max_suggestions=0)


@pytest.mark.parametrize(("typed", "intended"), TYPO_CASES)
def test_whole_word_suggestions_recover_common_typos(segmenter, typed, intended):
    suggestions = segmenter.suggest_spelling(typed)
    assert suggestions[0].text == intended


@pytest.mark.parametrize(("typed", "intended"), TYPO_CASES)
def test_typing_profile_recovers_reviewed_whole_word_typos(segmenter, typed, intended):
    diagnostics = segmenter.check_text(typed, profile="typing")
    assert [(item.text, item.suggestions[0].text) for item in diagnostics] == [
        (typed, intended)
    ]


def test_pending_typo_pairs_do_not_affect_runtime(segmenter):
    pairs = load_approved_typo_corrections(segmenter.data_files.typo_corrections)
    assert len(pairs) == 166
    assert "អោយ" not in pairs


@pytest.mark.parametrize(("typed", "intended"), [
    ("រយះពេល", "រយៈពេល"),
    ("រយះកម្ពស់", "រយៈកម្ពស់"),
    ("រយះបណ្តោយ", "រយៈបណ្តោយ"),
    ("រយះទទឹង", "រយៈទទឹង"),
])
def test_reviewed_correction_can_be_a_multiword_expression(segmenter, typed, intended):
    assert segmenter.suggest_spelling(typed)[0].text == intended
    diagnostics = segmenter.check_text(typed, profile="typing")
    assert [(item.text, item.suggestions[0].text) for item in diagnostics] == [
        (typed, intended)
    ]


@pytest.mark.parametrize(("typed", "intended"), [
    ("អាការះ", "អាការៈ"),
    ("ព្យញ្ជនះ", "ព្យញ្ជនៈ"),
    ("តាមរយះ", "តាមរយៈ"),
    ("សិល្បះ", "សិល្បៈ"),
    ("ទស្សនះ", "ទស្សនៈ"),
])
def test_dictionary_derived_reahmuk_confusion(segmenter, typed, intended):
    assert segmenter.suggest_spelling(typed)[0].text == intended
    diagnostics = segmenter.check_text(typed, profile="typing")
    assert diagnostics[0].suggestions[0].text == intended


def test_dictionary_derived_reahmuk_confusion_preserves_valid_collision(segmenter):
    assert segmenter.suggest_spelling("ស្រះ") == ()
    assert segmenter.check_text("ស្រះ", profile="typing") == []


@pytest.mark.parametrize(("typed", "intended"), [
    ("ជូយ", "ជួយ"),
    ("ស្ថានការណ៏", "ស្ថានការណ៍"),
    ("បញ្ជូល", "បញ្ចូល"),
    ("អញ្ចើញ", "អញ្ជើញ"),
])
def test_dictionary_derived_visual_confusions(segmenter, typed, intended):
    assert segmenter.suggest_spelling(typed)[0].text == intended
    diagnostics = segmenter.check_text(typed, profile="typing")
    assert diagnostics[0].confidence == 0.99
    assert diagnostics[0].suggestions[0].text == intended


@pytest.mark.parametrize("word", ["ជូរ", "ជួរ"])
def test_dictionary_derived_vowel_confusion_preserves_valid_words(segmenter, word):
    assert segmenter.suggest_spelling(word) == ()
    assert segmenter.check_text(word, profile="typing") == []


@pytest.mark.parametrize(("typed", "intended"), [
    ("ស្មើរ", "ស្មើ"),
    ("ថវិការ", "ថវិកា"),
    ("វិញ្ញាសារ", "វិញ្ញាសា"),
    ("សិក្សារ", "សិក្សា"),
    ("កីឡារ", "កីឡា"),
])
def test_dictionary_derived_extra_final_ro(segmenter, typed, intended):
    assert segmenter.suggest_spelling(typed)[0].text == intended
    diagnostics = segmenter.check_text(typed, profile="typing")
    assert diagnostics[0].confidence == 0.99
    assert diagnostics[0].suggestions[0].text == intended


@pytest.mark.parametrize("word", ["បញ្ជា", "បញ្ចា", "កា", "ការ"])
def test_contextual_confusion_rules_preserve_valid_words(segmenter, word):
    assert segmenter.suggest_spelling(word) == ()
    assert segmenter.check_text(word, profile="typing") == []


def test_whole_word_suggestions_skip_valid_words(segmenter):
    assert segmenter.suggest_spelling(CORRECT) == ()


def test_nikahit_rewrite_has_one_coherent_edit(segmenter):
    typed, intended = TYPO_CASES[1]
    suggestion = segmenter.suggest_spelling(typed)[0]
    assert suggestion.text == intended
    assert [(edit.kind, edit.start, edit.end, edit.text) for edit in suggestion.edits] == [
        ("replace", 1, 3, "\u17c6")
    ]


def test_informal_sign_sequence_rewrite_is_ranked_first(segmenter):
    typed = "\u179f\u17bb\u17b7"
    intended = "\u179f\u17ca\u17b8"

    suggestion = segmenter.suggest_spelling(typed)[0]

    assert suggestion.text == intended
    assert suggestion.edit_cost == 0.25
    assert [(edit.kind, edit.start, edit.end, edit.text) for edit in suggestion.edits] == [
        ("replace", 1, 3, "\u17ca\u17b8")
    ]


def test_vowel_substitution_beats_deleting_vowel_from_social_typo(segmenter):
    suggestions = segmenter.suggest_spelling("\u179f\u17bb\u1798")

    assert suggestions[0].text == "\u179f\u17bc\u1798"


def test_expanded_threshold_prefers_whole_greeting_span(segmenter):
    typed, intended = TYPO_CASES[0]
    diagnostics = segmenter.detect_typos(
        typed,
        max_edit_cost=1.5,
        include_valid_fragments=True,
    )
    assert [(item.text, item.suggestions[0].text) for item in diagnostics] == [
        (typed, intended)
    ]


@pytest.mark.parametrize(("typed", "intended"), TYPO_CASES[1:])
def test_aggressive_detection_recovers_valid_fragment_typos(segmenter, typed, intended):
    diagnostics = segmenter.detect_typos(
        typed,
        include_valid_fragments=True,
        max_suggestions=5,
    )
    assert diagnostics
    assert diagnostics[0].text == typed
    assert diagnostics[0].suggestions[0].text == intended


def test_aggressive_detection_does_not_cross_whitespace(segmenter):
    text = "\u179f\u17bd\u179a \u179f\u17d2\u178a\u17b8"
    assert all(diagnostic.text != text for diagnostic in segmenter.detect_typos(
        text,
        include_valid_fragments=True,
        max_edit_cost=1.5,
    ))
