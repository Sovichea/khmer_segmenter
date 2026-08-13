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
