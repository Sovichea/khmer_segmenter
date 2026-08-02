#!/usr/bin/env python3
"""Rebuild the RAC model and verify the reported lexical/frequency findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from khmer_segmenter import KhmerSegmenter  # noqa: E402
from khmer_segmenter.rac_rebuild import MODEL_DATA_FILES, MODEL_ID, build_rac_model  # noqa: E402

LAYERED_MODEL_ID = "rac-2022-layered-v1"
EXPECTED_COUNTS = {
    "rac_rows": 44752,
    "explicit_spellcheck_words": 37727,
    "explicit_segmentation_words": 37002,
    "derived_repetition_promoted": 339,
    "spellcheck_words": 38066,
    "segmentation_words": 37341,
}
EXPECTED_FOCUS = {
    "នីមួយ": 42,
    "នីមួយៗ": 142,
    "មួយ": 6223,
    "មួយៗ": 115,
    "ម្នាក់": 511,
    "ម្នាក់ៗ": 74,
}
EXPECTED_CASES = {
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
RUNTIME_FILES = MODEL_DATA_FILES


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text_bytes(path: Path) -> bytes:
    """Return UTF-8 bytes with CRLF/CR normalized to LF for diagnostics."""

    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def validate_manifest(
    data_dir: Path,
    failures: list[str],
    *,
    expected_model_id: str,
) -> None:
    manifest_path = data_dir / "khmer_model_manifest.json"
    if not manifest_path.is_file():
        failures.append("missing khmer_model_manifest.json")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != expected_model_id:
        failures.append(f"unexpected model_id: {manifest.get('model_id')!r}")
    described = manifest.get("files", {})
    for filename in RUNTIME_FILES:
        expected = described.get(filename, {}).get("sha256")
        actual = sha256(data_dir / filename)
        if expected != actual:
            failures.append(f"manifest hash mismatch: {filename}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rac-csv",
        type=Path,
        default=ROOT / "dataset" / "RAC-Khmer-Dict-2022.csv",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--processes", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    parser.add_argument(
        "--bundled-only",
        action="store_true",
        help="skip rebuilding and validate only the bundled runtime model",
    )
    args = parser.parse_args()

    bundled = ROOT / "src" / "khmer_segmenter" / "dictionary_data"
    failures: list[str] = []
    generated_data = bundled
    generated_summary = None

    if not args.bundled_only:
        output_dir = args.output_dir
        temporary = None
        if output_dir is None:
            temporary = tempfile.TemporaryDirectory(prefix="khmer-rac-validation-")
            output_dir = Path(temporary.name)
        result = build_rac_model(
            args.rac_csv,
            output_dir,
            iterations=3,
            processes=args.processes,
        )
        generated_data = result.data_dir
        generated_summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        for key, expected in EXPECTED_COUNTS.items():
            actual = generated_summary["lexicon"].get(key)
            if actual != expected:
                failures.append(f"lexicon.{key}: expected {expected}, got {actual}")
        for word, expected in EXPECTED_FOCUS.items():
            actual = generated_summary["focus_frequencies"].get(word)
            if actual != expected:
                failures.append(f"frequency[{word}]: expected {expected}, got {actual}")
        repetition = generated_summary["repetition_evaluation"]
        if repetition["trusted_repetition_forms"] != 716:
            failures.append(
                "trusted repetition forms: expected 716, got "
                + str(repetition["trusted_repetition_forms"])
            )
        if repetition["weighted_single_token"] != repetition["trusted_repetition_forms"]:
            failures.append("not all weighted repetition forms remained single tokens")
        for filename in RUNTIME_FILES:
            generated_file = generated_data / filename
            bundled_file = bundled / filename
            if sha256(generated_file) != sha256(bundled_file):
                if normalized_text_bytes(generated_file) == normalized_text_bytes(bundled_file):
                    failures.append(f"rebuilt file differs only by line endings: {filename}")
                else:
                    failures.append(f"rebuilt file has different content: {filename}")

    segmenter = KhmerSegmenter(data_dir=generated_data)
    validate_manifest(
        generated_data,
        failures,
        expected_model_id=LAYERED_MODEL_ID if args.bundled_only else MODEL_ID,
    )
    for text, expected in EXPECTED_CASES.items():
        actual = segmenter.segment(text, disable_post_processing=True)
        if actual != expected:
            failures.append(f"segment({text!r}): expected {expected!r}, got {actual!r}")
    for word in ("នីមួយ", "នីមួយៗ", "មួយ", "មួយៗ", "ម្នាក់", "ម្នាក់ៗ"):
        if not segmenter.is_spelling_valid(word):
            failures.append(f"spellcheck rejected trusted form: {word}")

    repetition_words = sorted(
        word
        for word in (generated_data / "khmer_dictionary_words.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if "ៗ" in word
    )
    bad_repetition = [
        word
        for word in repetition_words
        if segmenter.segment(word, disable_post_processing=True) != [word]
    ]
    if bad_repetition:
        failures.append(f"{len(bad_repetition)} repetition forms split unexpectedly")

    report = {
        "status": "pass" if not failures else "fail",
        "rebuild_performed": not args.bundled_only,
        "data_dir": str(generated_data),
        "runtime_files_checked": len(RUNTIME_FILES),
        "trusted_repetition_forms_tested": len(repetition_words),
        "target_cases_tested": len(EXPECTED_CASES),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
