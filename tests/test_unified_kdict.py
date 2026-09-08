import json
from pathlib import Path
import struct

import pytest

from khmer_segmenter import KhmerSegmenter, compile_klex
from khmer_segmenter.cli import main as cli_main
from khmer_segmenter.kdict import (
    AUTOCOMPLETE,
    SEGMENT,
    SPELLCHECK,
    TYPO_SURFACE,
    KDict,
)


def test_coeng_da_ta_aliases_segment_but_visual_spelling_is_opt_in(tmp_path: Path):
    lexicon = tmp_path / "coeng.klex.json"
    output = tmp_path / "coeng.kdict"
    canonical = "\u179f\u17d2\u178a\u17b6\u1794\u17cb"
    visual_alias = "\u179f\u17d2\u178f\u17b6\u1794\u17cb"
    lexicon.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "word": canonical,
                        "uses": ["segmentation", "spelling", "autocomplete"],
                        "frequency": 10,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compile_klex(lexicon, output)
    pack = KDict.load(output)
    assert pack.words[visual_alias].flags == SEGMENT

    segmenter = KhmerSegmenter.from_kdict(output)
    assert segmenter.segment(visual_alias) == [visual_alias]
    assert segmenter.is_spelling_valid(canonical)
    assert not segmenter.is_spelling_valid(visual_alias)
    assert segmenter.is_spelling_valid(visual_alias, accuracy="visual")
    assert segmenter.suggest_spelling(visual_alias, accuracy="visual") == ()
    assert [item.text for item in segmenter.complete_word(visual_alias[:3])] == []


def test_layered_loading_does_not_let_visual_alias_shadow_canonical_cost(
    tmp_path: Path,
):
    source = tmp_path / "coeng-costs.klex.json"
    output = tmp_path / "coeng-costs.kdict"
    canonical_da = "\u179f\u17d2\u178a\u17b6\u1794\u17cb"
    canonical_ta = "\u179f\u17d2\u178f\u17b6\u1794\u17cb"
    source.write_text(
        json.dumps(
            {
                "version": 1,
                "cost_model": {"default_cost": 5.0, "unknown_cost": 10.0},
                "entries": [
                    {
                        "word": canonical_da,
                        "uses": ["segmentation", "spelling"],
                        "cost": 4.0,
                    },
                    {
                        "word": canonical_ta,
                        "uses": ["segmentation"],
                        "cost": 2.0,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compile_klex(source, output)

    direct = KhmerSegmenter.from_kdict(output)
    layered = KhmerSegmenter.from_kdict_layers(output)

    assert direct.word_costs[canonical_ta] == pytest.approx(2.0)
    assert layered.word_costs[canonical_ta] == pytest.approx(2.0)
    assert layered.word_costs == direct.word_costs


def test_klex_overlay_preserves_base_and_adds_local_policy(tmp_path: Path):
    base_source = Path(__file__).parents[1] / "examples" / "custom.klex.json"
    base_output = tmp_path / "base.kdict"
    overlay_source = tmp_path / "overlay.klex.json"
    overlay_output = tmp_path / "overlay.kdict"
    compile_klex(base_source, base_output)
    base = KDict.load(base_output)

    overlay_source.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "word": "customword",
                        "uses": ["segmentation", "spelling", "autocomplete"],
                        "frequency": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    compile_klex(overlay_source, overlay_output, base_path=base_output)
    overlay = KDict.load(overlay_output)

    assert "customword" in overlay.words
    assert overlay.typo_corrections == base.typo_corrections
    first_base_word = next(iter(base.words))
    assert overlay.words[first_base_word].cost == base.words[first_base_word].cost


def test_klex_explicit_cost_model_preserves_ranking_and_phrase_corrections(
    tmp_path: Path,
):
    source = tmp_path / "explicit.klex.json"
    output = tmp_path / "explicit.kdict"
    source.write_text(
        json.dumps(
            {
                "version": 1,
                "cost_model": {"default_cost": 4.25, "unknown_cost": 9.25},
                "entries": [
                    {
                        "word": "រយះពេល",
                        "uses": ["segmentation", "typo"],
                        "cost": 3.5,
                        "correction": "រយៈពេល",
                    },
                    {
                        "word": "រយៈពេល",
                        "uses": ["correction_target"],
                        "cost": 4.25,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    compile_klex(source, output)
    pack = KDict.load(output)
    assert pack.default_cost == pytest.approx(4.25)
    assert pack.unknown_cost == pytest.approx(9.25)
    assert pack.words["រយះពេល"].cost == pytest.approx(3.5)
    assert pack.words["រយៈពេល"].flags == 0
    assert pack.typo_corrections["រយះពេល"] == "រយៈពេល"


def test_kdict_embeds_and_preserves_word_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    source = tmp_path / "provenance.klex.json"
    output = tmp_path / "provenance.kdict"
    source.write_text(
        json.dumps(
            {
                "version": 1,
                "pack": {"id": "science-v1", "kind": "official_lexicon"},
                "sources": [
                    {
                        "id": "science-book",
                        "title": "Science terminology",
                        "sha256": "abc123",
                    }
                ],
                "entries": [
                    {
                        "word": "កាដម្យូម",
                        "uses": ["segmentation", "spelling", "autocomplete"],
                        "provenance": [
                            {
                                "source": "science-book",
                                "page": 12,
                                "region": 32,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compile_klex(source, output)
    pack = KDict.load(output)

    assert pack.packs == [{"id": "science-v1", "kind": "official_lexicon"}]
    assert pack.sources[0]["id"] == "science-book"
    assert pack.word_provenance["កាដម្យូម"][0]["page"] == 12
    assert KhmerSegmenter.from_kdict(output).provenance_for("កាដម្យូម")[0]["page"] == 12

    assert cli_main(["data", "inspect", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["packs"][0]["id"] == "science-v1"
    assert report["sources"][0]["id"] == "science-book"
    assert report["provenance_words"] == 1


def test_layered_kdict_strict_mode_excludes_community(tmp_path: Path):
    def build(name: str, word: str) -> Path:
        source = tmp_path / f"{name}.klex.json"
        output = tmp_path / f"{name}.kdict"
        source.write_text(
            json.dumps(
                {
                    "version": 1,
                    "pack": {"id": name, "kind": name},
                    "entries": [
                        {
                            "word": word,
                            "uses": ["segmentation", "spelling", "autocomplete"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        compile_klex(source, output)
        return output

    rac = build("rac", "ដែល")
    lexicon = build("lexicon", "កាដម្យូម")
    community = build("community", "អោយ")
    user = build("user", "ឈ្មោះអ្នកប្រើ")

    strict = KhmerSegmenter.from_kdict_layers(
        rac,
        lexicon_paths=[lexicon],
        community_paths=[community],
        user_paths=[user],
        mode="strict",
    )
    assert strict.is_spelling_valid("ដែល")
    assert strict.is_spelling_valid("កាដម្យូម")
    assert strict.is_spelling_valid("ឈ្មោះអ្នកប្រើ")
    assert strict.provenance_for("កាដម្យូម") == ()
    assert "អោយ" not in strict.words

    inclusive = KhmerSegmenter.from_kdict_layers(
        rac,
        lexicon_paths=[lexicon],
        community_paths=[community],
        user_paths=[user],
        mode="inclusive",
    )
    assert inclusive.is_spelling_valid("អោយ")
    assert inclusive.segment("កាដម្យូម") == ["កាដម្យូម"]


def test_layered_kdict_rebases_and_preserves_community_frequency(tmp_path: Path):
    rac_source = tmp_path / "rac.klex.json"
    community_source = tmp_path / "community.klex.json"
    rac = tmp_path / "rac.kdict"
    community = tmp_path / "community.kdict"
    rac_source.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "word": "ពាក្យ",
                        "uses": ["segmentation", "spelling"],
                        "frequency": 10,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    community_source.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "word": "ហ្សែន",
                        "uses": ["segmentation", "supplemental"],
                        "frequency": 100,
                    },
                    {
                        "word": "ហាយវេ",
                        "uses": ["segmentation", "supplemental"],
                        "frequency": 1,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compile_klex(rac_source, rac)
    compile_klex(community_source, community)

    segmenter = KhmerSegmenter.from_kdict_layers(
        rac,
        community_paths=[community],
        mode="inclusive",
    )

    assert segmenter.word_costs["ហ្សែន"] < segmenter.word_costs["ហាយវេ"]
    assert segmenter.word_costs["ហាយវេ"] == pytest.approx(
        segmenter.default_cost + 1.5
    )
    assert not segmenter.is_spelling_valid("ហ្សែន")

    assert all(
        segmenter.get_word_cost(word) == cost
        for word, cost in segmenter.word_costs.items()
        if word in segmenter._supplemental_runtime_words
    )


def test_python_cli_compiles_overlay(tmp_path: Path):
    base_source = Path(__file__).parents[1] / "examples" / "custom.klex.json"
    base_output = tmp_path / "base.kdict"
    overlay_source = tmp_path / "overlay.klex.json"
    overlay_output = tmp_path / "overlay.kdict"
    compile_klex(base_source, base_output)
    overlay_source.write_text(
        '{"version":1,"entries":[{"word":"customword","uses":["segmentation"]}]}',
        encoding="utf-8",
    )

    assert (
        cli_main(
            [
                "data",
                "compile",
                str(overlay_source),
                "--base",
                str(base_output),
                "--output",
                str(overlay_output),
            ]
        )
        == 0
    )
    assert "customword" in KDict.load(overlay_output).words


def test_kdict_reader_rejects_malformed_table_and_metadata(tmp_path: Path):
    source = Path(__file__).parents[1] / "examples" / "custom.klex.json"
    output = tmp_path / "valid.kdict"
    compile_klex(source, output)
    valid = output.read_bytes()

    invalid_table = bytearray(valid)
    struct.pack_into("<I", invalid_table, 12, 3)
    with pytest.raises(ValueError, match="power of two"):
        KDict(bytes(invalid_table))

    with pytest.raises(ValueError, match="truncated"):
        KDict(valid[:-1])


def test_unified_kdict_drives_segmentation_spelling_completion_and_correction(tmp_path: Path):
    lexicon = tmp_path / "custom.klex.json"
    output = tmp_path / "custom.kdict"

    lexicon.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "word": "ដែល",
                        "uses": ["segmentation", "spelling", "autocomplete"],
                        "frequency": 100,
                    },
                    {"word": "ពាក្យ", "uses": ["segmentation"], "frequency": 20},
                    {
                        "word": "ដេល",
                        "uses": ["segmentation", "supplemental", "typo"],
                        "correction": "ដែល",
                    },
                    {
                        "word": "សាកល្បង",
                        "uses": ["spelling", "autocomplete"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compile_klex(lexicon, output)

    pack = KDict.load(output)
    assert pack.version == 2
    assert pack.words["ដេល"].flags & (SEGMENT | TYPO_SURFACE) == (
        SEGMENT | TYPO_SURFACE
    )
    assert not pack.words["ដេល"].flags & SPELLCHECK
    assert pack.words["សាកល្បង"].flags & (SPELLCHECK | AUTOCOMPLETE)
    assert pack.typo_corrections == {"ដេល": "ដែល"}

    segmenter = KhmerSegmenter.from_kdict(output)
    assert segmenter.segment("ដេល") == ["ដេល"]
    assert not segmenter.is_spelling_valid("ដេល")
    assert segmenter.suggest_spelling("ដេល")[0].text == "ដែល"
    assert [item.text for item in segmenter.complete_word("សាក")] == ["សាកល្បង"]


def test_python_cli_compiles_klex(tmp_path: Path):
    output = tmp_path / "cli.kdict"
    source = Path(__file__).parents[1] / "examples" / "custom.klex.json"

    assert cli_main(["data", "compile", str(source), "--output", str(output)]) == 0
    assert KDict.load(output).version == 2
    assert KhmerSegmenter.from_kdict(output).suggest_spelling("ដេល")[0].text == "ដែល"
