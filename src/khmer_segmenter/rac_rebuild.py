"""Rebuild the strict RAC-only lexicon and frequency model.

This module deliberately treats RAC headwords/subentries as lexical authority and
uses RAC definitions/examples only as frequency evidence. Uncurated corpora and
community supplemental words are not used to create accepted spellings.
"""

from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .normalization import KhmerNormalizer
from .viterbi import KhmerSegmenter

REPETITION_MARK = "ៗ"
DEFAULT_DEFINITION_WEIGHT = 1.0
DEFAULT_EXAMPLE_WEIGHT = 3.0
DEFAULT_SELF_HEADWORD_WEIGHT = 0.25
MODEL_ID = "rac-2022-strict-v1"
MODEL_RELEASE = "0.2.0rc1"
RAC_SOURCE_REVISION = "525c0171894465cba920a9181387a032c11610d3"
MODEL_DATA_FILES = (
    "khmer_dictionary_words.txt",
    "khmer_dictionary_official_2022_words.txt",
    "khmer_dictionary_supplemental_words.txt",
    "khmer_spellcheck_words.txt",
    "khmer_word_frequencies.json",
    "khmer_word_pos.json",
)


@dataclass(frozen=True, slots=True)
class RACBuildResult:
    output_dir: Path
    data_dir: Path
    audit_dir: Path
    summary_path: Path
    report_path: Path


@dataclass(frozen=True, slots=True)
class _FrequencyTask:
    records: tuple[tuple[str, tuple[str, ...], str, str], ...]


_WORKER_SEGMENTER: KhmerSegmenter | None = None
_WORKER_BASE_WORDS: set[str] | None = None
_WORKER_DEFINITION_WEIGHT = DEFAULT_DEFINITION_WEIGHT
_WORKER_EXAMPLE_WEIGHT = DEFAULT_EXAMPLE_WEIGHT
_WORKER_SELF_WEIGHT = DEFAULT_SELF_HEADWORD_WEIGHT


def read_words(path: str | os.PathLike[str]) -> set[str]:
    return {
        line.strip()
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }


def _write_text_lf(path: Path, text: str) -> None:
    """Write deterministic UTF-8 text with LF endings on every platform."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write_words(path: Path, words: Iterable[str]) -> None:
    _write_text_lf(path, "\n".join(sorted(set(words))) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".json":
        return len(json.loads(path.read_text(encoding="utf-8")))
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)


def _write_model_manifest(
    data_dir: Path,
    rac_csv: Path,
    lexicon_summary: dict,
    iteration_reports: list[dict],
) -> Path:
    files = {}
    for filename in MODEL_DATA_FILES:
        path = data_dir / filename
        files[filename] = {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "records": _record_count(path),
        }
    numeric_counts = {
        key: value
        for key, value in lexicon_summary.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    serialized_frequencies = json.loads(
        (data_dir / "khmer_word_frequencies.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "release": MODEL_RELEASE,
        "source": {
            "name": "Khmer Dictionary 2022",
            "authority": "National Council of Khmer Language, Royal Academy of Cambodia",
            "publisher": "Seanghay Hay (Hugging Face user seanghay)",
            "url": (
                "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/"
                f"{RAC_SOURCE_REVISION}/RAC-Khmer-Dict-2022.csv"
            ),
            "revision": RAC_SOURCE_REVISION,
            "sha256": _sha256(rac_csv),
            "license_notice": "Noncommercial redistribution with attribution; see DATA_LICENSE.md",
        },
        "generation": {
            "iterations": len(iteration_reports),
            "segmentation_forms": "clean t_main plus clean POS-supported t_subword",
            "spellcheck_forms": "all clean t_main and t_subword forms",
            "derived_repetition": "RAC-context forms accepted by the conservative repetition rule",
            "definition_weight": DEFAULT_DEFINITION_WEIGHT,
            "example_weight": DEFAULT_EXAMPLE_WEIGHT,
            "self_headword_weight": DEFAULT_SELF_HEADWORD_WEIGHT,
            "final_raw_weighted_total": iteration_reports[-1]["weighted_total"],
            "serialization": "round to nearest integer with minimum 1",
        },
        "counts": {
            **numeric_counts,
            "serialized_frequency_entries": files["khmer_word_frequencies.json"]["records"],
            "serialized_frequency_total": sum(serialized_frequencies.values()),
        },
        "files": files,
        "excluded_assets": {
            "khmer_dictionary_hyphenation_pairs.txt": (
                "Preserved experimental runtime asset; not generated from the RAC segmentation model"
            )
        },
    }
    path = data_dir / "khmer_model_manifest.json"
    _write_text_lf(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return path


def _clean_reasons(word: str) -> list[str]:
    reasons: list[str] = []
    if not word:
        reasons.append("empty")
    if any(char.isspace() for char in word):
        reasons.append("whitespace")
    if word.startswith("\u17d2"):
        reasons.append("leading_coeng")
    if word.endswith("\u17d2"):
        reasons.append("trailing_coeng")
    if word and not any(0x1780 <= ord(char) <= 0x17B3 for char in word):
        reasons.append("no_khmer_base")

    invalid: list[str] = []
    for char in word:
        codepoint = ord(char)
        if not ((0x1780 <= codepoint <= 0x17D3) or codepoint in {0x17D7, 0x17DD}):
            invalid.append(f"U+{codepoint:04X}")
    if invalid:
        reasons.append("nonlexical_codepoint:" + ",".join(sorted(set(invalid))))
    if "ឬ" in word and len(word) > 1:
        reasons.append("contains_or_phrase_marker")
    return reasons


def _read_rows(rac_csv: Path) -> list[dict[str, str]]:
    with rac_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"t_id", "t_main", "t_subword", "t_pos", "t_exp", "t_exam"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"RAC CSV is missing columns: {sorted(missing)}")
        return list(reader)


def build_lexicon(rac_csv: Path, lexicon_dir: Path) -> dict:
    """Build explicit RAC forms plus conservative RAC-derived repetition forms."""

    lexicon_dir.mkdir(parents=True, exist_ok=True)
    normalizer = KhmerNormalizer()
    rows = _read_rows(rac_csv)

    main_words: set[str] = set()
    subwords_all: set[str] = set()
    subwords_with_pos: set[str] = set()
    pos_by_word: dict[str, set[str]] = defaultdict(set)
    explicit_audit: list[dict[str, str]] = []
    explicit_forms_by_row: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        row_id = (row.get("t_id") or "").strip()
        pos = (row.get("t_pos") or "").strip()
        for kind, column in (("main", "t_main"), ("subword", "t_subword")):
            raw = (row.get(column) or "").strip()
            if not raw:
                continue
            word = normalizer.normalize(raw)
            reasons = _clean_reasons(word)
            spellcheck = not reasons
            segmentation = spellcheck and (kind == "main" or bool(pos))
            if spellcheck:
                explicit_forms_by_row[row_id].add(word)
                if kind == "main":
                    main_words.add(word)
                else:
                    subwords_all.add(word)
                    if pos:
                        subwords_with_pos.add(word)
                if pos:
                    pos_by_word[word].add(pos)
            explicit_audit.append(
                {
                    "t_id": row_id,
                    "t_ref": (row.get("t_ref") or "").strip(),
                    "kind": kind,
                    "raw_word": raw,
                    "normalized_word": word,
                    "pos": pos,
                    "spellcheck": str(spellcheck).lower(),
                    "segmentation": str(segmentation).lower(),
                    "reason": ";".join(reasons)
                    if reasons
                    else ("subword_without_pos" if kind == "subword" and not pos else ""),
                    "definition": normalizer.normalize(row.get("t_exp") or ""),
                    "example": normalizer.normalize(row.get("t_exam") or ""),
                }
            )

    explicit_spellcheck = main_words | subwords_all
    explicit_segmentation = main_words | subwords_with_pos
    explicit_repetition_forms = {word for word in explicit_spellcheck if REPETITION_MARK in word}

    seed_dictionary = lexicon_dir / "_explicit_segmentation_seed.txt"
    _write_words(seed_dictionary, explicit_segmentation)
    seed_segmenter = KhmerSegmenter(dictionary_path=seed_dictionary)

    occurrence_count: Counter[str] = Counter()
    definition_count: Counter[str] = Counter()
    example_count: Counter[str] = Counter()
    document_count: Counter[str] = Counter()
    synonym_evidence: set[str] = set()
    provenance: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        row_id = (row.get("t_id") or "").strip()
        row_forms = explicit_forms_by_row.get(row_id, set())
        is_repetition_entry = any(REPETITION_MARK in word for word in row_forms)
        seen_in_row: set[str] = set()

        for field_name, column in (("definition", "t_exp"), ("example", "t_exam")):
            text = normalizer.normalize(row.get(column) or "")
            if not text:
                continue
            tokens = seed_segmenter.segment(text, disable_post_processing=True, normalize=False)
            detected_forms = [token for token in tokens if token in explicit_repetition_forms]
            detected_forms.extend(
                left + REPETITION_MARK
                for left, right in zip(tokens, tokens[1:])
                if right == REPETITION_MARK and left in explicit_segmentation and len(left) > 1
            )
            for form in detected_forms:
                occurrence_count[form] += 1
                if field_name == "definition":
                    definition_count[form] += 1
                else:
                    example_count[form] += 1
                seen_in_row.add(form)
                if is_repetition_entry and field_name == "definition":
                    synonym_evidence.add(form)
                if len(provenance[form]) < 5:
                    provenance[form].append(
                        {
                            "t_id": row_id,
                            "t_main": normalizer.normalize(row.get("t_main") or ""),
                            "t_subword": normalizer.normalize(row.get("t_subword") or ""),
                            "field": field_name,
                        }
                    )
        for form in seen_in_row:
            document_count[form] += 1

    derived_promoted = {
        form
        for form in occurrence_count
        if form not in explicit_spellcheck
        and (document_count[form] >= 2 or form in synonym_evidence)
    }

    for form in derived_promoted:
        base = form[:-1]
        if pos_by_word.get(base):
            pos_by_word[form].update(pos_by_word[base])

    spellcheck_words = explicit_spellcheck | derived_promoted
    segmentation_words = explicit_segmentation | derived_promoted

    _write_words(lexicon_dir / "rac_spellcheck_words.txt", spellcheck_words)
    _write_words(lexicon_dir / "rac_segmentation_words.txt", segmentation_words)
    _write_words(lexicon_dir / "rac_main_words_clean.txt", main_words)
    _write_words(lexicon_dir / "rac_subwords_clean_all.txt", subwords_all)
    _write_words(lexicon_dir / "rac_subwords_with_pos.txt", subwords_with_pos)
    _write_words(lexicon_dir / "rac_derived_repetition_words.txt", derived_promoted)
    _write_text_lf(
        lexicon_dir / "rac_word_pos.json",
        json.dumps(
            {word: sorted(values) for word, values in sorted(pos_by_word.items())},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    with (lexicon_dir / "rac_lexicon_audit.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(explicit_audit[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(explicit_audit)

    repetition_rows: list[dict[str, object]] = []
    for form in sorted(set(occurrence_count) | explicit_repetition_forms):
        if form in explicit_repetition_forms:
            status = "explicit_rac"
        elif form in derived_promoted:
            status = "derived_promoted"
        else:
            status = "derived_not_promoted"
        repetition_rows.append(
            {
                "word": form,
                "base": form[:-1] if form.endswith(REPETITION_MARK) else "",
                "status": status,
                "occurrences": occurrence_count[form],
                "rac_records": document_count[form],
                "definition_occurrences": definition_count[form],
                "example_occurrences": example_count[form],
                "synonym_evidence": str(form in synonym_evidence).lower(),
                "provenance_json": json.dumps(provenance.get(form, []), ensure_ascii=False),
            }
        )
    with (lexicon_dir / "rac_repetition_audit.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(repetition_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(repetition_rows)

    summary = {
        "rac_rows": len(rows),
        "explicit_main_words": len(main_words),
        "explicit_subwords_all": len(subwords_all),
        "explicit_subwords_with_pos": len(subwords_with_pos),
        "explicit_spellcheck_words": len(explicit_spellcheck),
        "explicit_segmentation_words": len(explicit_segmentation),
        "explicit_repetition_forms": len(explicit_repetition_forms),
        "derived_repetition_candidates": len(occurrence_count),
        "derived_repetition_promoted": len(derived_promoted),
        "spellcheck_words": len(spellcheck_words),
        "segmentation_words": len(segmentation_words),
        "spellcheck_only_subword_forms": len(spellcheck_words - segmentation_words),
        "excluded_records": sum(row["spellcheck"] == "false" for row in explicit_audit),
        "examples": {
            word: {
                "explicit": word in explicit_spellcheck,
                "promoted": word in derived_promoted,
                "occurrences": occurrence_count[word],
                "rac_records": document_count[word],
                "synonym_evidence": word in synonym_evidence,
            }
            for word in ("នីមួយ", "នីមួយៗ", "មួយ", "មួយៗ", "ម្នាក់", "ម្នាក់ៗ")
        },
        "policy": {
            "explicit": "clean RAC t_main and t_subword; U+17D7 is allowed inside lexical forms",
            "derived_repetition": "known RAC base + ៗ, promoted after occurrence in at least two RAC records or as a definition synonym under an explicit repetition-form entry",
            "separator_fallback": "standalone ៗ remains a separator when no full lexical form matches",
        },
    }
    _write_text_lf(
        lexicon_dir / "summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    seed_dictionary.unlink(missing_ok=True)
    return summary


def _load_frequency_records(
    rac_csv: Path, normalizer: KhmerNormalizer
) -> list[tuple[str, tuple[str, ...], str, str]]:
    rows = _read_rows(rac_csv)
    forms_by_ref: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        ref = (row.get("t_ref") or row.get("t_id") or "").strip()
        for column in ("t_main", "t_subword"):
            word = normalizer.normalize((row.get(column) or "").strip())
            if word and not any(ch.isspace() for ch in word):
                forms_by_ref[ref].add(word)

    records = []
    for row in rows:
        ref = (row.get("t_ref") or row.get("t_id") or "").strip()
        explicit = set(forms_by_ref.get(ref, set()))
        for column in ("t_main", "t_subword"):
            word = normalizer.normalize((row.get(column) or "").strip())
            if word and not any(ch.isspace() for ch in word):
                explicit.add(word)
        records.append(
            (
                (row.get("t_id") or "").strip(),
                tuple(sorted(explicit)),
                normalizer.normalize(row.get("t_exp") or ""),
                normalizer.normalize(row.get("t_exam") or ""),
            )
        )
    return records


def _init_frequency_worker(
    dictionary_path: str,
    frequency_path: str | None,
    base_words_path: str,
    definition_weight: float,
    example_weight: float,
    self_weight: float,
) -> None:
    global _WORKER_SEGMENTER, _WORKER_BASE_WORDS
    global _WORKER_DEFINITION_WEIGHT, _WORKER_EXAMPLE_WEIGHT, _WORKER_SELF_WEIGHT
    _WORKER_SEGMENTER = KhmerSegmenter(
        dictionary_path=dictionary_path, frequency_path=frequency_path
    )
    _WORKER_BASE_WORDS = read_words(base_words_path)
    _WORKER_DEFINITION_WEIGHT = definition_weight
    _WORKER_EXAMPLE_WEIGHT = example_weight
    _WORKER_SELF_WEIGHT = self_weight


def _count_frequency_chunk(
    records: tuple[tuple[str, tuple[str, ...], str, str], ...],
) -> tuple[Counter[str], Counter[str]]:
    assert _WORKER_SEGMENTER is not None
    assert _WORKER_BASE_WORDS is not None
    segmenter = _WORKER_SEGMENTER
    counts: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    for _record_id, active_words, definition, example in records:
        active_set = set(active_words)
        for field_name, text, field_weight in (
            ("definition", definition, _WORKER_DEFINITION_WEIGHT),
            ("example", example, _WORKER_EXAMPLE_WEIGHT),
        ):
            if not text:
                continue
            stats[f"{field_name}_records"] += 1
            stats[f"{field_name}_chars"] += len(text)
            tokens = segmenter.segment(text, disable_post_processing=True, normalize=False)
            stats[f"{field_name}_tokens"] += len(tokens)
            for token in tokens:
                if (
                    token in segmenter.words
                    and not segmenter._is_separator(token)
                    and not segmenter._is_digit(token)
                ):
                    weight = field_weight * (_WORKER_SELF_WEIGHT if token in active_set else 1.0)
                    counts[token] += weight
                    stats["known_tokens"] += 1
                    stats["known_weight"] += weight
                    if token in _WORKER_BASE_WORDS:
                        stats["canonical_known_tokens"] += 1
                    else:
                        stats["variant_known_tokens"] += 1
                elif not segmenter._is_separator(token) and not segmenter._is_digit(token):
                    stats["unknown_tokens"] += 1
                    stats["unknown_chars"] += len(token)
    return counts, stats


def _chunked(items: list, size: int) -> list[tuple]:
    return [tuple(items[index : index + size]) for index in range(0, len(items), size)]


def _normalized_l1(a: dict[str, float], b: dict[str, float]) -> float:
    total_a = sum(a.values()) or 1.0
    total_b = sum(b.values()) or 1.0
    return sum(
        abs(a.get(key, 0.0) / total_a - b.get(key, 0.0) / total_b) for key in set(a) | set(b)
    )


def _write_frequency_json(counts: dict[str, float], path: Path) -> dict[str, int]:
    integer_counts = {
        word: max(1, int(round(value))) for word, value in counts.items() if value > 0
    }
    ordered = dict(sorted(integer_counts.items(), key=lambda item: (-item[1], item[0])))
    _write_text_lf(path, json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
    return ordered


def calculate_frequencies(
    rac_csv: Path,
    dictionary_path: Path,
    output_dir: Path,
    *,
    iterations: int = 3,
    processes: int | None = None,
    definition_weight: float = DEFAULT_DEFINITION_WEIGHT,
    example_weight: float = DEFAULT_EXAMPLE_WEIGHT,
    self_headword_weight: float = DEFAULT_SELF_HEADWORD_WEIGHT,
) -> tuple[Path, list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalizer = KhmerNormalizer()
    records = _load_frequency_records(rac_csv, normalizer)
    tasks = _chunked(records, 300)
    processes = processes or max(1, min(4, (os.cpu_count() or 2) - 1))

    previous_counts: dict[str, float] = {}
    previous_frequency_path: Path | None = None
    reports: list[dict] = []

    for iteration in range(1, iterations + 1):
        started = time.perf_counter()
        initargs = (
            str(dictionary_path),
            str(previous_frequency_path) if previous_frequency_path else None,
            str(dictionary_path),
            definition_weight,
            example_weight,
            self_headword_weight,
        )
        if processes == 1:
            _init_frequency_worker(*initargs)
            results = [_count_frequency_chunk(task) for task in tasks]
        else:
            context = mp.get_context("spawn" if os.name == "nt" else "fork")
            with context.Pool(
                processes=processes,
                initializer=_init_frequency_worker,
                initargs=initargs,
            ) as pool:
                results = pool.map(_count_frequency_chunk, tasks)

        counts: Counter[str] = Counter()
        stats: Counter[str] = Counter()
        for part_counts, part_stats in results:
            counts.update(part_counts)
            stats.update(part_stats)
        raw_counts = dict(counts)
        frequency_path = output_dir / f"rac_word_frequencies_iteration_{iteration}.json"
        integer_counts = _write_frequency_json(raw_counts, frequency_path)
        reports.append(
            {
                "iteration": iteration,
                "input_frequency": previous_frequency_path.name
                if previous_frequency_path
                else None,
                "output_frequency": frequency_path.name,
                "observed_forms": len(integer_counts),
                "weighted_total": sum(raw_counts.values()),
                "distribution_l1_from_previous": _normalized_l1(previous_counts, raw_counts)
                if previous_counts
                else None,
                "duration_seconds": time.perf_counter() - started,
                "stats": dict(stats),
                "top_words": list(integer_counts.items())[:50],
            }
        )
        previous_counts = raw_counts
        previous_frequency_path = frequency_path

    assert previous_frequency_path is not None
    final_path = output_dir / "khmer_word_frequencies.json"
    shutil.copyfile(previous_frequency_path, final_path)
    return final_path, reports


def _evaluate_repetition_forms(
    dictionary_path: Path, frequency_path: Path, output_path: Path
) -> dict:
    words = sorted(word for word in read_words(dictionary_path) if REPETITION_MARK in word)
    uniform = KhmerSegmenter(dictionary_path=dictionary_path)
    weighted = KhmerSegmenter(dictionary_path=dictionary_path, frequency_path=frequency_path)
    rows: list[dict[str, object]] = []
    uniform_single = 0
    weighted_single = 0
    for word in words:
        uniform_tokens = uniform.segment(word, disable_post_processing=True)
        weighted_tokens = weighted.segment(word, disable_post_processing=True)
        uniform_ok = uniform_tokens == [word]
        weighted_ok = weighted_tokens == [word]
        uniform_single += int(uniform_ok)
        weighted_single += int(weighted_ok)
        rows.append(
            {
                "word": word,
                "uniform": "\u200b".join(uniform_tokens),
                "weighted": "\u200b".join(weighted_tokens),
                "uniform_single": str(uniform_ok).lower(),
                "weighted_single": str(weighted_ok).lower(),
                "frequency": weighted.word_frequencies.get(word, ""),
            }
        )
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    total = len(words)
    return {
        "trusted_repetition_forms": total,
        "uniform_single_token": uniform_single,
        "uniform_single_token_rate": uniform_single / total if total else 1.0,
        "weighted_single_token": weighted_single,
        "weighted_single_token_rate": weighted_single / total if total else 1.0,
    }


def _evaluate_target_cases(
    dictionary_path: Path, frequency_path: Path, output_path: Path
) -> list[dict[str, str]]:
    segmenter = KhmerSegmenter(dictionary_path=dictionary_path, frequency_path=frequency_path)
    cases = [
        "នីមួយ",
        "នីមួយៗ",
        "មួយ",
        "មួយៗ",
        "ម្នាក់",
        "ម្នាក់ៗ",
        "មនុស្សម្នាក់ៗ",
        "មនុស្សជាតិនីមួយៗ",
        "ពាក្យផ្សេងៗគ្នា",
    ]
    rows = [
        {
            "text": text,
            "segmentation": "\u200b".join(segmenter.segment(text, disable_post_processing=True)),
        }
        for text in cases
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["text", "segmentation"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


def build_rac_model(
    rac_csv: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    iterations: int = 3,
    processes: int | None = None,
) -> RACBuildResult:
    """Build a complete runtime data directory and reproducibility report."""

    rac_csv = Path(rac_csv).resolve()
    output_dir = Path(output_dir).resolve()
    lexicon_dir = output_dir / "lexicon"
    frequency_dir = output_dir / "frequencies"
    audit_dir = output_dir / "audit"
    data_dir = output_dir / "data"
    for path in (lexicon_dir, frequency_dir, audit_dir, data_dir):
        path.mkdir(parents=True, exist_ok=True)

    lexicon_summary = build_lexicon(rac_csv, lexicon_dir)
    dictionary_path = lexicon_dir / "rac_segmentation_words.txt"
    spellcheck_path = lexicon_dir / "rac_spellcheck_words.txt"
    final_frequency, iteration_reports = calculate_frequencies(
        rac_csv,
        dictionary_path,
        frequency_dir,
        iterations=iterations,
        processes=processes,
    )

    shutil.copyfile(dictionary_path, data_dir / "khmer_dictionary_words.txt")
    shutil.copyfile(dictionary_path, data_dir / "khmer_dictionary_official_2022_words.txt")
    _write_text_lf(data_dir / "khmer_dictionary_supplemental_words.txt", "")
    shutil.copyfile(spellcheck_path, data_dir / "khmer_spellcheck_words.txt")
    shutil.copyfile(final_frequency, data_dir / "khmer_word_frequencies.json")
    shutil.copyfile(lexicon_dir / "rac_word_pos.json", data_dir / "khmer_word_pos.json")

    shutil.copyfile(lexicon_dir / "rac_lexicon_audit.tsv", audit_dir / "rac_lexicon_audit.tsv")
    shutil.copyfile(
        lexicon_dir / "rac_repetition_audit.tsv",
        audit_dir / "rac_repetition_audit.tsv",
    )
    repetition_report = _evaluate_repetition_forms(
        dictionary_path, final_frequency, audit_dir / "repetition_form_evaluation.tsv"
    )
    targets = _evaluate_target_cases(
        dictionary_path, final_frequency, audit_dir / "target_case_segmentations.tsv"
    )

    frequencies = json.loads(final_frequency.read_text(encoding="utf-8"))
    manifest_path = _write_model_manifest(data_dir, rac_csv, lexicon_summary, iteration_reports)
    focus = {word: frequencies.get(word) for word in ("នីមួយ", "នីមួយៗ", "មួយ", "មួយៗ", "ម្នាក់", "ម្នាក់ៗ")}
    summary = {
        "method": {
            "trusted_explicit_source": "RAC t_main and t_subword",
            "trusted_derived_source": "RAC-context repetition forms whose base is explicit RAC and which occur in >=2 RAC records or as a synonym in a repetition-entry definition",
            "frequency_source": "RAC t_exp and t_exam only",
            "definition_weight": DEFAULT_DEFINITION_WEIGHT,
            "example_weight": DEFAULT_EXAMPLE_WEIGHT,
            "self_headword_weight": DEFAULT_SELF_HEADWORD_WEIGHT,
            "repetition_matching": "known lexical forms ending in ៗ receive deterministic priority over base + separator",
        },
        "lexicon": lexicon_summary,
        "frequency_iterations": iteration_reports,
        "focus_frequencies": focus,
        "repetition_evaluation": repetition_report,
        "target_cases": targets,
        "data_dir": str(data_dir),
        "model_manifest": str(manifest_path),
    }
    summary_path = output_dir / "summary.json"
    _write_text_lf(summary_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    report_lines = [
        "# RAC-only frequency rebuild with lexical repetition forms",
        "",
        "## Lexicon",
        "",
        f"- Explicit RAC spellcheck forms: {lexicon_summary['explicit_spellcheck_words']:,}",
        f"- Explicit RAC segmentation forms: {lexicon_summary['explicit_segmentation_words']:,}",
        f"- RAC-derived repetition forms promoted: {lexicon_summary['derived_repetition_promoted']:,}",
        f"- Final spellcheck forms: {lexicon_summary['spellcheck_words']:,}",
        f"- Final segmentation forms: {lexicon_summary['segmentation_words']:,}",
        "",
        "The repetition mark `ៗ` is allowed inside a curated lexical form. It remains a separator fallback only when no complete accepted form matches.",
        "",
        "## Frequency recalculation",
        "",
        "| Iteration | Observed forms | Weighted total | L1 change |",
        "|---:|---:|---:|---:|",
    ]
    for item in iteration_reports:
        delta = (
            "—"
            if item["distribution_l1_from_previous"] is None
            else f"{item['distribution_l1_from_previous']:.6f}"
        )
        report_lines.append(
            f"| {item['iteration']} | {item['observed_forms']:,} | {item['weighted_total']:,.2f} | {delta} |"
        )
    report_lines.extend(
        [
            "",
            "## Repetition-form validation",
            "",
            f"- Trusted `…ៗ` forms tested: {repetition_report['trusted_repetition_forms']:,}",
            f"- Uniform model single-token rate: {repetition_report['uniform_single_token_rate']:.2%}",
            f"- RAC-weighted model single-token rate: {repetition_report['weighted_single_token_rate']:.2%}",
            "",
            "Requested examples:",
            "",
        ]
    )
    for row in targets:
        report_lines.append(
            f"- `{row['text']}` → `{row['segmentation'].replace(chr(0x200B), ' + ')}`"
        )
    report_path = output_dir / "REPORT.md"
    _write_text_lf(report_path, "\n".join(report_lines) + "\n")

    return RACBuildResult(
        output_dir=output_dir,
        data_dir=data_dir,
        audit_dir=audit_dir,
        summary_path=summary_path,
        report_path=report_path,
    )
