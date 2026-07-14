#!/usr/bin/env python3
"""Fail when a Python distribution contains local linguistic data."""

from __future__ import annotations

import argparse
import glob
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


PROHIBITED_NAMES = {
    "khmer_dictionary_words.txt",
    "khmer_dictionary_official_2022_words.txt",
    "khmer_dictionary_supplemental_words.txt",
    "khmer_dictionary_hyphenation_pairs.txt",
    "khmer_word_frequencies.json",
    "khmer_word_frequencies.backup.json",
    "khmer_word_frequencies_corpus.json",
    "khmer_word_pos.json",
    "unknown_word_frequencies.json",
    "khmer_frequencies.bin",
    "khmer_dictionary.kdict",
    "khmer_hyphenation.kdict",
}


def archive_members(path: Path) -> list[str]:
    if path.suffix == ".whl" or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            return archive.getnames()
    raise ValueError(f"unsupported distribution archive: {path}")


def prohibited_reason(member: str) -> str | None:
    normalized = member.replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = set(path.parts)
    if "dataset" in parts or "dictionary_data" in parts:
        return "local data directory"
    if "port" in parts and "common" in parts:
        return "native data directory"
    if path.name in PROHIBITED_NAMES:
        return "known linguistic artifact"
    if path.suffix.lower() in {".kdict", ".bin"}:
        return "native binary data"
    if path.name.endswith("_provenance.json"):
        return "local derived-data provenance payload"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+")
    args = parser.parse_args()
    archives: list[Path] = []
    for value in args.archives:
        matches = [Path(match) for match in glob.glob(value)]
        if not matches:
            parser.error(f"distribution archive not found: {value}")
        archives.extend(matches)
    failures: list[tuple[Path, str, str]] = []
    for archive in archives:
        members = archive_members(archive)
        for member in members:
            reason = prohibited_reason(member)
            if reason:
                failures.append((archive, member, reason))
        print(f"checked {archive} ({len(members)} members)")
    if failures:
        for archive, member, reason in failures:
            print(f"ERROR {archive}: {member} ({reason})")
        return 1
    print("distribution audit passed: no local linguistic data found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
