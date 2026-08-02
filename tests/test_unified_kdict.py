import json
from pathlib import Path

from khmer_segmenter import KhmerSegmenter, compile_klex
from khmer_segmenter.cli import main as cli_main
from khmer_segmenter.kdict import (
    AUTOCOMPLETE,
    SEGMENT,
    SPELLCHECK,
    TYPO_SURFACE,
    KDict,
)


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
