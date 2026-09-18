import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from khmer_segmenter.kdict import AUTOCOMPLETE, SEGMENT, SPELLCHECK, KDict  # noqa: E402
from prepare_data import step_compile_kdict  # noqa: E402


def _flags(record) -> set[str]:
    names = set()
    if record.flags & SEGMENT:
        names.add("segment")
    if record.flags & SPELLCHECK:
        names.add("spell")
    if record.flags & AUTOCOMPLETE:
        names.add("complete")
    return names


def test_kdict_compile_bakes_composition_and_completion_policy(tmp_path: Path):
    (tmp_path / "dict.txt").write_text("វាក្យ\nសព្ទ\nកម្ពុជា\n", encoding="utf-8")
    (tmp_path / "spell.txt").write_text(
        "វាក្យ\nសព្ទ\nវាក្យសព្ទ\nកម្ពុជា\n"
        "សញ្ញាបត្រ\nសញ្ញាបត្រមធ្យមសិក្សាបឋមភូមិ\n",
        encoding="utf-8",
    )
    (tmp_path / "freq.json").write_text(
        json.dumps(
            {
                "វាក្យ": 10,
                "សព្ទ": 10,
                "វាក្យសព្ទ": 1,
                "កម្ពុជា": 100,
                "សញ្ញាបត្រ": 20,
                "សញ្ញាបត្រមធ្យមសិក្សាបឋមភូមិ": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "keep.txt").write_text("", encoding="utf-8")

    output = tmp_path / "out.kdict"
    step_compile_kdict(
        str(tmp_path / "dict.txt"),
        str(tmp_path / "freq.json"),
        str(output),
        spellcheck_path=str(tmp_path / "spell.txt"),
        composition_keep_path=str(tmp_path / "keep.txt"),
    )

    words = KDict.load(output).words
    # Cheap composition: segmentation cleared, spelling retained, short enough
    # to remain a completion candidate.
    assert _flags(words["វាក្យសព្ទ"]) == {"spell", "complete"}
    # Long curated form: spelling retained, completion removed.
    assert _flags(words["សញ្ញាបត្រមធ្យមសិក្សាបឋមភូមិ"]) == {"spell"}
    # Ordinary word: unchanged.
    assert _flags(words["កម្ពុជា"]) == {"segment", "spell", "complete"}
