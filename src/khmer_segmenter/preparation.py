"""Build local runtime dictionaries from user-obtained upstream data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .data import DICTIONARY_SOURCE_CREDIT, DICTIONARY_SOURCE_URL, DataFiles
from .normalization import KhmerNormalizer


REFERENCE_NAME = "Khmer Dictionary 2022"
REFERENCE_AUTHORITY = "National Council of Khmer Language, Royal Academy of Cambodia"


def read_words(path: Path, tsv: bool = False) -> tuple[list[str], int]:
    """Read and normalize one-word records from a text or TSV file."""

    if not path.is_file():
        return [], 0
    normalizer = KhmerNormalizer()
    words: list[str] = []
    rejected = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            raw = line.rstrip("\r\n")
            if tsv:
                raw = raw.split("\t", 1)[0]
            word = normalizer.normalize(raw.strip())
            if not word or any(char.isspace() for char in word):
                rejected += 1
                continue
            words.append(word)
    return words, rejected


def write_words(path: Path, words: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")


def prepare_dictionary(
    source_tsv: str | Path,
    output_dir: str | Path,
    *,
    port_dictionary: str | Path | None = None,
) -> dict[str, object]:
    """Normalize an upstream TSV into ignored local runtime word lists."""

    source_tsv = Path(source_tsv)
    if not source_tsv.is_file():
        raise FileNotFoundError(f"dictionary source TSV not found: {source_tsv}")
    files = DataFiles(Path(output_dir).expanduser().resolve())
    reference_rows, reference_rejected = read_words(source_tsv, tsv=True)
    existing_source = (
        files.supplemental_words
        if files.supplemental_words.is_file()
        else files.dictionary
    )
    existing_rows, existing_rejected = read_words(existing_source)
    official = set(reference_rows)
    supplemental = set(existing_rows) - official
    runtime = official | supplemental

    write_words(files.official_words, official)
    write_words(files.supplemental_words, supplemental)
    write_words(files.dictionary, runtime)
    if port_dictionary is not None:
        port_path = Path(port_dictionary)
        port_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files.dictionary, port_path)

    report: dict[str, object] = {
        "reference": {
            "name": REFERENCE_NAME,
            "authority": REFERENCE_AUTHORITY,
            "source": DICTIONARY_SOURCE_URL,
            "source_credit": DICTIONARY_SOURCE_CREDIT,
            "terms_note": "Research purpose only; review the upstream dataset card",
            "redistributed": False,
            "source_rows": len(reference_rows) + reference_rejected,
            "accepted_unique_headwords": len(official),
            "rejected_rows": reference_rejected,
        },
        "counts": {
            "official_headwords": len(official),
            "supplemental_retained": len(supplemental),
            "runtime_union": len(runtime),
            "supplemental_rejected": existing_rejected,
        },
    }
    provenance = files.root / "khmer_dictionary_provenance.json"
    provenance.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
