#!/usr/bin/env python3
"""Extract conservative non-RAC lexical additions from official lexicon OCR.

The input TSV rows are source headwords, but many headwords are compounds,
phrases, alternatives, or explanatory text.  This script keeps RAC as the
primary authority, removes exact RAC entries, peels RAC words from the edges of
technical expressions, and emits only the remaining lexical core.  Every kept
form retains its PDF page/region provenance in KLEX and KDIC.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from khmer_segmenter.kdict import compile_klex
from khmer_segmenter.normalization import KhmerNormalizer
from khmer_segmenter.orthography import COENG_DA, COENG_TA, coeng_da_ta_variants


DEFAULT_INPUT = PROJECT_ROOT / "dataset" / "lexicon"
DEFAULT_RAC = (
    PROJECT_ROOT
    / "src"
    / "khmer_segmenter"
    / "dictionary_data"
    / "khmer_dictionary_official_2022_words.txt"
)
DEFAULT_OUTPUT = DEFAULT_INPUT / "generated"
DEFAULT_REVIEW = DEFAULT_INPUT / "official_lexicon_review.tsv"
GEOGRAPHY_CORROBORATION = (
    PROJECT_ROOT
    / "dataset"
    / "all_extracted_official_khmer_lexicons"
    / "nckl_country_city_geography"
    / "country_city_lexicon.tsv"
)

SOURCE_CONFIG = {
    "economic-lexicon": {
        "id": "rac-economics-2019",
        "title": "Lexicon of Economics, Khmer-English-French",
        "authority": "Royal Academy of Cambodia, National Council of Khmer Language",
        "year": 2019,
        "tsv": "economic_headwords.tsv",
    },
    "geography-lexicon": {
        "id": "nckl-geography-2013",
        "title": "Lexicon of Geographical Terms Especially Relating to Country and City Names",
        "authority": "National Council of Khmer Language",
        "year": 2013,
        "tsv": "geography_headwords.tsv",
        "proper_names": True,
    },
    "law-lexicon": {
        "id": "council-ministers-civil-law-2007",
        "title": "Lexicon of Legal Terms: Civil Law and Civil Procedure",
        "authority": "Office of the Council of Ministers, Legal Terminology Approval Committee",
        "year": 2007,
        "tsv": "law_headwords.tsv",
    },
    "MPTC-Lexicon": {
        "id": "mptc-digital-terminology-2025",
        "title": "Lexicon of Digital Terminology, Volume 1",
        "authority": "Ministry of Post and Telecommunications",
        "year": 2025,
        "tsv": "mptc_headwords.tsv",
        "license": (
            "Copyright MPTC 2025; the source states that copying for distribution "
            "or commercial use requires permission. Generate this pack locally."
        ),
    },
    "science-lexicon": {
        "id": "nckl-science-technology-2014",
        "title": "Lexicon of Science and Technology, Khmer-English-French",
        "authority": "Royal Academy of Cambodia, National Council of Khmer Language",
        "year": 2014,
        "tsv": "science_headwords.tsv",
    },
}

ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")
ALTERNATIVE_BREAK = re.compile(r"\s*ឬ\s*|\s+និង\s+|[/|()]|\s+")
PAGE_REGION = re.compile(r"page_(\d+)_region_(\d+)\.png$")
TRIM = " -–—,;:។៕!?«»“”\"'[]{}"

# These are productive wrappers and connectors that turn a lexical item into a
# source headword phrase. Do not peel arbitrary RAC words: doing so would turn
# borrowed forms such as តេឡេក្រាម into the false fragment តេឡេ.
PHRASE_COMPONENTS = {
    "កញ្ចប់",
    "កម្រិត",
    "កម្មវិធី",
    "ការ",
    "ការងារ",
    "ការិយាល័យ",
    "កិច្ច",
    "កិច្ចសន្យា",
    "ក្រុម",
    "ក្រសួង",
    "កាបូប",
    "កូដ",
    "ខ្សែ",
    "គោលការណ៍",
    "ច្បាប់",
    "ចំណុច",
    "ជំនាន់",
    "ជា",
    "ជីវិត",
    "ឈ្មោះ",
    "ថ្លៃ",
    "ដំណាក់",
    "ដំណើរការ",
    "ឌីជីថល",
    "តំបន់",
    "ទិន្នន័យ",
    "ទ្រឹស្តី",
    "ទម្រង់",
    "ធនាគារ",
    "នៃ",
    "និង",
    "បច្ចេកវិទ្យា",
    "បណ្ណ",
    "បណ្តាញ",
    "បរិស្ថាន",
    "ប្រព័ន្ធ",
    "ប្រាក់",
    "ផលិតកម្ម",
    "ផែនការ",
    "ផ្ទៃ",
    "ផ្សារ",
    "ពន្ធ",
    "ព័ត៌មាន",
    "ភាគី",
    "ភាព",
    "មួយ",
    "លើ",
    "ម៉ាស៊ីន",
    "រូបិយបណ្ណ",
    "វិទ្យាសាស្ត្រ",
    "សិទ្ធិ",
    "សេដ្ឋកិច្ច",
    "សេវា",
    "ហិរញ្ញវត្ថុ",
    "អ្នក",
    "អាជីវកម្ម",
    "ឧបករណ៍",
}

SHORT_FUNCTION_WORDS = {"ជា", "នៃ", "លើ", "និង", "ទៅ", "ដោយ", "មួយ", "ក្រោយ"}

# A source phrase occasionally contains a genuinely new lexical core that does
# not occur as its own row. These narrow, inspected exceptions are preferable
# to automatically stripping arbitrary dictionary words.
CORE_OVERRIDES = {
    ("law-lexicon", "បច្ឆាញាតិផ្ទាល់"): ("បច្ឆាញាតិ",),
    ("law-lexicon", "សាមយិកមួយជីវិត"): ("សាមយិក",),
    ("MPTC-Lexicon", "កាបូបគ្រីបតូ"): ("គ្រីបតូ",),
    ("MPTC-Lexicon", "កិច្ចកុំព្យូទ័រពពក/កុំព្យូទីងពពក"): ("កុំព្យូទីង",),
    ("MPTC-Lexicon", "តេស្តទទួលយក"): ("តេស្ត",),
    ("MPTC-Lexicon", "ស៊ីមកាត/កាតម៉ូឌុលបញ្ជាក់អត្តសញ្ញាណអ្នកជាវ"): ("ស៊ីម",),
    ("science-lexicon", "ក្រុមកាបូនីល"): ("កាបូនីល",),
    ("science-lexicon", "ទ្រឹស្តីរេស៊ីឌុយ"): ("រេស៊ីឌុយ",),
    ("science-lexicon", "ទម្រង់ប៉ូលែ"): ("ប៉ូលែ",),
    ("science-lexicon", "ផ្ទៃស្វ៊ែរ"): ("ស្វ៊ែរ",),
    ("science-lexicon", "ក្រុមអាបែល"): ("អាបែល",),
}

# Human-reviewed source rows that are definitions, examples, or productive
# phrases rather than reusable lexical units. They remain visible in the audit
# with their page locator, but are deliberately not promoted to a KDIC word.
REVIEWED_PHRASE_EXCLUSIONS = {
    "law-lexicon": {
        "កាតព្វកិច្ចអនិយ័ត",
        "ក្បួនរីតីសាសនា",
        "ជននៅក្រោមហិតូបត្ថម្ភ",
        "ដីបម្រើ",
        "ដីប្រើ",
        "ផលធម្មជាតិ",
        "សកម្មភាពសុពល",
        "ឧបកម្មសិទ្ធិអវិភាគ",
        "ឧបភោគីនៃសិទ្ធិលើបំណុល",
    },
    "MPTC-Lexicon": {
        "ឆ្នូលអនានុញ្ញាត/អាក់សេសអនានុញ្ញាត",
        "ថតចរន្ត",
        "ថតមេ",
        "ថតឫស",
        "ទីក្រុងស្មាត",
        "ទីតាំងទទួលយក",
        "ទីប្រគល់",
        "បច្ចេកវិទ្យាពពក",
        "បណ្ណក្លែងក្លាយ/កាតក្លែងក្លាយ",
        "មជ្ឈមណ្ឌលបញ្ញើនៅអាកាសយានដ្ឋាន",
        "ម្ចាស់បណ្ណ/ម្ចាស់កាត",
        "រូបិយបណ្ណគ្រីបតូ",
        "លំហអន្តរព័ន្ធ/លំហសាយប័រ",
        "វិដំណាក់ប៊ីជំនាន់ក្រោយ",
        "វិសាលគមអនាជ្ញាបណ្ណ",
        "សន្តិសុខអន្តរព័ន្ធ/សន្តិសុខសាយប័រ",
        "សោចូល/សោអាក់សេស",
        "សោដែនបញ្ជាក់អត្តសញ្ញាណសារ",
        "ស៊ីមស្មាត",
        "អ៊ីនធឺណិតបង់ទូលាយ/អ៊ីនធឺណិតប្រូដបែន",
        "អ៊ីសឺណិតជីហ្គាប៊ីត",
        "អ៊ីសឺណិតល្បឿនលឿន",
        "ឧក្រិដ្ឋកម្មអន្តរព័ន្ធ/ឧក្រិដ្ឋកម្មសាយប័រ",
        "ឯកតាអនុគមន៍",
    },
    "science-lexicon": {
        "ក្តារមេ",
        "ឫសគូប",
        "ផ្ទះពុម្ពធំ",
        "ឧទាហរណ៍ បើខ្នាតជាក្រាម ១ហិកតូក្រាម",
        "ឧទាហរណ៍ បើខ្នាតជាម៉ែត្រ ១មិល្លីម៉ែត្រ",
        "ឧទាហរណ៍ បើខ្នាតជាម៉ែត្រ ១សង់ទីម៉ែត្រ",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_plain_khmer(value: str) -> bool:
    return (
        bool(value)
        and "\u1780" <= value[0] <= "\u17b3"
        and value[-1] != "\u17d2"
        and all("\u1780" <= char <= "\u17d3" or char == "\u17dd" for char in value)
    )


def runtime_rac_forms(words: set[str]) -> set[str]:
    forms = set(words)
    for word in words:
        forms.update(coeng_da_ta_variants(word))
    return forms


def requires_coeng_review(word: str) -> bool:
    """Return whether strict spelling depends on COENG DA/TA selection."""

    return COENG_DA in word or COENG_TA in word


def strong_rac_split(value: str, rac: set[str]) -> list[str] | None:
    """Return a credible all-RAC phrase split, excluding accidental fragments."""

    usable = {
        word
        for word in rac
        if len(word) >= 3 or word in SHORT_FUNCTION_WORDS
    }
    max_length = min(len(value), max(map(len, usable), default=0))
    paths: list[list[str] | None] = [None] * (len(value) + 1)
    paths[0] = []
    for start in range(len(value)):
        if paths[start] is None:
            continue
        for end in range(start + 1, min(len(value), start + max_length) + 1):
            word = value[start:end]
            if word not in usable:
                continue
            candidate = paths[start] + [word]
            if paths[end] is None or len(candidate) < len(paths[end]):
                paths[end] = candidate
    result = paths[-1]
    return result if result and len(result) > 1 else None


def edge_words(value: str, rac: set[str], *, prefix: bool) -> list[str]:
    candidates = []
    for word in PHRASE_COMPONENTS & rac:
        if len(word) >= len(value):
            continue
        if (prefix and value.startswith(word)) or (not prefix and value.endswith(word)):
            candidates.append(word)
    return sorted(candidates, key=len, reverse=True)


def lexical_core(value: str, rac: set[str]) -> tuple[str, list[str], list[str]]:
    """Peel credible RAC components while retaining one unknown lexical core."""

    leading: list[str] = []
    trailing: list[str] = []
    core = value
    changed = True
    while changed and core and core not in rac:
        changed = False
        prefixes = edge_words(core, rac, prefix=True)
        suffixes = edge_words(core, rac, prefix=False)
        # Prefer the edge that removes the longest trusted component. This
        # avoids breaking borrowed forms into accidental one-letter headwords.
        prefix = prefixes[0] if prefixes else ""
        suffix = suffixes[0] if suffixes else ""
        if len(prefix) >= len(suffix) and prefix:
            leading.append(prefix)
            core = core[len(prefix) :]
            changed = True
        elif suffix:
            trailing.insert(0, suffix)
            core = core[: -len(suffix)]
            changed = True
    return core, leading, trailing


def source_metadata(folder: Path, config: dict) -> tuple[dict, Path]:
    pdfs = sorted(folder.glob("*.pdf"))
    if len(pdfs) != 1:
        raise ValueError(f"{folder}: expected exactly one PDF source")
    pdf = pdfs[0]
    return (
        {
            "id": config["id"],
            "title": config["title"],
            "authority": config["authority"],
            "year": config["year"],
            "document": pdf.name,
            "sha256": sha256(pdf),
            "license": config.get(
                "license", "See the source document and verify redistribution terms."
            ),
        },
        pdf,
    )


def load_review_decisions(path: Path, normalizer: KhmerNormalizer) -> dict[tuple[str, str, str], dict]:
    """Load durable, human-reviewed OCR decisions from a local TSV."""

    if not path.is_file():
        return {}
    decisions = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle, delimiter="\t"), start=2):
            status = row.get("status", "").strip()
            if status not in {"approved", "rejected"}:
                raise ValueError(f"{path}:{row_number}: status must be approved or rejected")
            candidate = normalizer.normalize(ZERO_WIDTH.sub("", row.get("candidate", "")).strip())
            key = (row.get("source", "").strip(), row.get("locator", "").strip(), candidate)
            if not all(key):
                raise ValueError(f"{path}:{row_number}: source, locator, and candidate are required")
            if key in decisions:
                raise ValueError(f"{path}:{row_number}: duplicate review decision for {key!r}")
            approved_word = normalizer.normalize(
                ZERO_WIDTH.sub("", row.get("approved_word", "")).strip()
            )
            if status == "approved" and not approved_word:
                approved_word = candidate
            if approved_word and not is_plain_khmer(approved_word):
                raise ValueError(f"{path}:{row_number}: approved_word is not plain Khmer")
            decisions[key] = {
                "status": status,
                "approved_word": approved_word,
                "coeng_status": row.get("coeng_status", "").strip(),
                "note": row.get("note", "").strip(),
            }
    return decisions


def prepare_one(
    folder: Path,
    output: Path,
    rac: set[str],
    rac_lexical: set[str],
    normalizer: KhmerNormalizer,
    review_decisions: dict[tuple[str, str, str], dict],
) -> dict:
    config = SOURCE_CONFIG[folder.name]
    source, pdf = source_metadata(folder, config)
    tsv = folder / config["tsv"]
    provenance_by_word: dict[str, list[dict]] = defaultdict(list)
    uses_by_word: dict[str, set[str]] = defaultdict(set)
    audit: list[dict] = []
    corroborated_names: dict[str, dict] = {}
    if config.get("proper_names") and GEOGRAPHY_CORROBORATION.is_file():
        with GEOGRAPHY_CORROBORATION.open(
            "r", encoding="utf-8-sig", newline=""
        ) as corroboration_handle:
            for corroboration in csv.DictReader(corroboration_handle, delimiter="\t"):
                if corroboration.get("entry_kind") not in {"country_name", "capital_name"}:
                    continue
                if corroboration.get("review_status") != "candidate":
                    continue
                if float(corroboration.get("confidence") or 0) < 0.80:
                    continue
                word = normalizer.normalize(corroboration.get("headword_normalized", "").strip())
                corroborated_names[word] = corroboration

    with tsv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(rows, start=2):
            original = row.get("transcription", "")
            normalized = normalizer.normalize(ZERO_WIDTH.sub("", original).strip())
            locator = row.get("filename", "")
            match = PAGE_REGION.search(locator)
            page = int(match.group(1)) if match else None
            region = int(match.group(2)) if match else None
            if not normalized:
                pieces = []
                row_reason = "empty"
            elif normalized in rac:
                pieces = []
                row_reason = "exact_rac"
            elif normalized in REVIEWED_PHRASE_EXCLUSIONS.get(folder.name, set()):
                pieces = []
                row_reason = "reviewed_phrase_or_example"
            else:
                pieces = [part.strip(TRIM) for part in ALTERNATIVE_BREAK.split(normalized)]
                pieces = [part for part in pieces if part]
                row_reason = "candidate"

            extracted: list[str] = []
            removed: list[str] = []
            override = CORE_OVERRIDES.get((folder.name, normalized))
            if override is not None:
                pieces = list(override)
            for piece in pieces:
                if piece in rac:
                    removed.append(piece)
                    continue
                if not is_plain_khmer(piece):
                    removed.append(piece)
                    continue
                if config.get("proper_names"):
                    # Pages 6-25 are the country/capital list. Later pages are
                    # general geography terminology and require a separate
                    # lexical review rather than automatic proper-name status.
                    if page is None or page > 25:
                        removed.append(piece)
                        continue
                    if corroborated_names and piece not in corroborated_names:
                        removed.append(piece)
                        continue
                    core, leading, trailing = piece, [], []
                else:
                    split = strong_rac_split(piece, rac)
                    if split:
                        removed.extend(split)
                        continue
                    core, leading, trailing = lexical_core(piece, rac)
                removed.extend(leading + trailing)
                if (leading or trailing) and override is None:
                    # The row is a compositional source expression. Keep its
                    # parts in the audit, but do not promote a guessed fragment.
                    removed.append(core)
                    continue
                if (
                    core
                    and core not in rac
                    and is_plain_khmer(core)
                    and not strong_rac_split(core, rac)
                ):
                    extracted.append(core)

            candidates = list(dict.fromkeys(extracted))
            extracted = []
            approved_forms = []
            review_states = []
            review_records = []
            for candidate in candidates:
                decision = review_decisions.get((source["id"], locator, candidate))
                if decision is not None:
                    review_status = decision["status"]
                    approved_word = decision["approved_word"]
                    coeng_status = decision["coeng_status"]
                    note = decision["note"]
                elif candidate in corroborated_names:
                    review_status = "corroborated"
                    approved_word = candidate
                    coeng_status = "verified"
                    note = "matched independent structured extraction"
                else:
                    review_status = "pending"
                    approved_word = ""
                    coeng_status = "pending"
                    note = "OCR transcription requires human review"

                needs_coeng_review = requires_coeng_review(approved_word or candidate)
                if not needs_coeng_review:
                    coeng_status = "not_applicable"
                elif approved_word in rac_lexical:
                    coeng_status = "verified_rac"
                elif decision is None:
                    # Independent OCR/cross-extraction evidence is not enough
                    # to establish lexical DA/TA choice for strict spelling.
                    coeng_status = "pending"
                elif coeng_status not in {"pending", "verified"}:
                    coeng_status = "pending"

                if review_status in {"approved", "corroborated"} and approved_word:
                    approved_forms.append(approved_word)
                    if approved_word in rac:
                        review_status = (
                            "approved_rac"
                            if approved_word in rac_lexical
                            else "approved_rac_visual_alias"
                        )
                        removed.append(approved_word)
                    else:
                        extracted.append(approved_word)
                        uses_by_word[approved_word].add("segmentation")
                        # Reviewed words without a COENG ambiguity are already
                        # lexically resolved. Only DA/TA forms require the
                        # additional explicit ``verified`` decision.
                        if coeng_status in {"not_applicable", "verified"}:
                            uses_by_word[approved_word].update({"spelling", "autocomplete"})
                        evidence = {
                            "source": source["id"],
                            "page": page,
                            "region": region,
                            "locator": locator,
                            "source_headword": normalized,
                            "ocr_candidate": candidate,
                            "review_status": review_status,
                            "coeng_status": coeng_status,
                        }
                        if note:
                            evidence["review_note"] = note
                        if candidate in corroborated_names:
                            evidence["english"] = corroborated_names[candidate].get("english", "")
                            evidence["extraction_confidence"] = float(
                                corroborated_names[candidate].get("confidence") or 0
                            )
                        if evidence not in provenance_by_word[approved_word]:
                            provenance_by_word[approved_word].append(evidence)
                review_states.append(f"{candidate}:{review_status}")
                review_records.append(
                    {
                        "candidate": candidate,
                        "status": review_status,
                        "approved_word": approved_word,
                        "coeng_status": coeng_status,
                        "note": note,
                    }
                )

            extracted = list(dict.fromkeys(extracted))
            if not candidates and row_reason == "candidate":
                row_reason = "rac_phrase_or_notation"
            if extracted:
                row_decision = "include"
            elif any(state.endswith(":pending") for state in review_states):
                row_decision = "pending"
            else:
                row_decision = "exclude"
            audit.append(
                {
                    "row": row_number,
                    "locator": locator,
                    "source_headword": normalized,
                    "decision": row_decision,
                    "candidate_words": " | ".join(candidates),
                    "approved_words": " | ".join(dict.fromkeys(approved_forms)),
                    "extracted_words": " | ".join(extracted),
                    "review_status": " | ".join(review_states),
                    "review_records": json.dumps(
                        review_records, ensure_ascii=False, separators=(",", ":")
                    ),
                    "removed_rac_components": " | ".join(removed),
                    "reason": row_reason,
                }
            )

    entries = [
        {
            "word": word,
            "uses": sorted(uses_by_word[word]),
            "provenance": provenance_by_word[word],
        }
        for word in sorted(provenance_by_word)
    ]
    klex = {
        "version": 1,
        "pack": {
            "id": f"{source['id']}-new-non-rac-v1",
            "kind": "official_lexicon",
            "priority": "secondary",
            "description": "Conservative lexical cores absent from RAC 2022",
        },
        "sources": [source],
        "entries": entries,
    }
    output.mkdir(parents=True, exist_ok=True)
    stem = folder.name.lower()
    klex_path = output / f"{stem}.klex.json"
    audit_path = output / f"{stem}.audit.tsv"
    kdict_path = output / f"{stem}.kdict"
    klex_path.write_text(
        json.dumps(klex, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(audit)
    compile_klex(klex_path, kdict_path)
    return {
        "source": source["id"],
        "pdf": str(pdf),
        "input_rows": len(audit),
        "new_words": len(entries),
        "klex": str(klex_path),
        "kdict": str(kdict_path),
        "audit": str(audit_path),
    }


def write_review_html(output: Path, reports: list[dict]) -> Path:
    """Write an interactive local review page for OCR candidates."""

    sections = []
    total = 0
    card_number = 0
    for report in reports:
        klex = json.loads(Path(report["klex"]).read_text(encoding="utf-8-sig"))
        source = klex["sources"][0]
        cards = []
        image_folder = Path(report["pdf"]).parent
        with Path(report["audit"]).open("r", encoding="utf-8-sig", newline="") as handle:
            review_rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in review_rows:
            records = json.loads(row.get("review_records") or "[]")
            for record in records:
                total += 1
                card_number += 1
                candidate = record["candidate"]
                raw_status = record["status"]
                status = (
                    "approved"
                    if raw_status
                    in {
                        "approved",
                        "approved_rac",
                        "approved_rac_visual_alias",
                        "corroborated",
                    }
                    else raw_status
                )
                approved = record.get("approved_word") or candidate
                coeng_status = record.get("coeng_status", "not_applicable")
                needs_coeng_review = (
                    requires_coeng_review(approved)
                    and coeng_status not in {"verified", "verified_rac"}
                )
                note = record.get("note", "")
                should_export = raw_status in {
                    "approved",
                    "approved_rac",
                    "approved_rac_visual_alias",
                    "rejected",
                }
                image_path = image_folder / row["locator"]
                image_src = os.path.relpath(image_path, output).replace(os.sep, "/")
                attrs = {
                    "source": source["id"],
                    "locator": row["locator"],
                    "candidate": candidate,
                    "status": status,
                    "coeng-status": coeng_status,
                    "needs-coeng-review": str(needs_coeng_review).lower(),
                    "export": str(should_export).lower(),
                }
                data = " ".join(
                    f'data-{key}="{html.escape(value, quote=True)}"'
                    for key, value in attrs.items()
                )
                coeng_control = ""
                if needs_coeng_review:
                    checked = " checked" if coeng_status == "verified" else ""
                    coeng_control = (
                        '<label class="coeng-check"><input type="checkbox" '
                        f'class="coeng-verified"{checked}>'
                        " Confirm lexical COENG DA/TA form for strict spelling</label>"
                    )
                cards.append(
                    f'<article class="entry {html.escape(status)}" {data}>'
                    f'<a href="{html.escape(image_src, quote=True)}" target="_blank" '
                    f'title="Open source crop at full size"><img '
                    f'src="{html.escape(image_src, quote=True)}" '
                    f'alt="Source crop for {html.escape(candidate, quote=True)}" loading="lazy">'
                    "</a>"
                    f'<div class="entry-body"><p class="locator">{html.escape(row["locator"])}</p>'
                    f'<p class="label">OCR candidate</p><h3 lang="km">{html.escape(candidate)}</h3>'
                    f'<label for="word-{card_number}">Correct spelling</label>'
                    f'<input id="word-{card_number}" class="approved-word" lang="km" '
                    f'type="text" value="{html.escape(approved, quote=True)}">'
                    f"{coeng_control}"
                    f'<label for="note-{card_number}">Review note</label>'
                    f'<input id="note-{card_number}" class="review-note" type="text" '
                    f'value="{html.escape(note, quote=True)}">'
                    '<div class="actions"><button type="button" data-action="approved">Approve</button>'
                    '<button type="button" data-action="rejected">Reject</button></div>'
                    f'<p class="status">Status: <strong>{html.escape(raw_status)}</strong></p>'
                    f'<details><summary>Source transcription</summary><span lang="km">'
                    f'{html.escape(row["source_headword"])}</span></details></div></article>'
                )
        sections.append(
            '<section class="source">'
            f'<h2>{html.escape(source["title"])} '
            f'<span>{len(klex["entries"])} compiled</span></h2>'
            f'<p>{html.escape(source["authority"])} · {source["year"]} · '
            f'{html.escape(source["document"])}</p>'
            f'<div class="grid">{"".join(cards)}</div>'
            "</section>"
        )
    document = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Official lexicon review</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:auto;
padding:2rem;background:#f7f7f4;color:#202522}}
h1{{margin-bottom:.25rem}}
h2{{margin-top:3rem;border-bottom:1px solid #bbb;padding-bottom:.5rem}}
h2 span{{font-size:.7em;font-weight:normal;color:#52605a}}
.toolbar{{position:sticky;top:0;z-index:2;background:#f7f7f4;padding:.8rem 0;
display:flex;gap:.6rem;flex-wrap:wrap;border-bottom:1px solid #bbb}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:1rem}}
.entry{{background:white;border:1px solid #d9ddd9;border-radius:8px;
overflow:hidden;break-inside:avoid}}
.entry img{{display:block;width:100%;height:110px;object-fit:contain;background:#eee;
image-rendering:auto;border-bottom:1px solid #ddd}}
.entry-body{{padding:.8rem 1rem}}
.entry h3{{font-size:1.35rem;margin:0 0 .4rem}}
.entry.pending{{border-color:#bd8b24}}.entry.approved{{border-color:#39805a}}
.entry.rejected{{border-color:#a54d4d;opacity:.78}}
ul{{margin:.25rem 0;padding-left:1.2rem}}
small,.locator,.label{{color:#59645e}}.locator,.label{{font-size:.8rem;margin:.2rem 0}}
label{{display:block;font-size:.82rem;margin-top:.6rem;color:#46504b}}
input{{box-sizing:border-box;width:100%;font:inherit;padding:.45rem .55rem;
border:1px solid #aeb6b1;border-radius:5px;background:#fff}}
.coeng-check{{padding:.55rem;border:1px solid #bd8b24;border-radius:5px;background:#fff8e8}}
.coeng-check input{{width:auto;margin-right:.4rem}}
.approved-word{{font-size:1.15rem}}button,select{{font:inherit;padding:.45rem .7rem;
border:1px solid #89938d;border-radius:5px;background:white;cursor:pointer}}
.actions{{display:flex;gap:.5rem;margin-top:.75rem}}.status{{font-size:.85rem}}
</style>
<h1>Official lexicon candidate review</h1>
<p>{total} conservative non-RAC candidates. These are local review results,
not a redistribution grant.</p>
<p>Edit the spelling, then choose <strong>Approve</strong> or
<strong>Reject</strong>. Save over
<code>dataset/lexicon/official_lexicon_review.tsv</code> and rerun
<code>python scripts/prepare_official_lexicons.py</code>. Click an image to
open its original crop.</p>
<p>For approved forms containing COENG DA or COENG TA, also confirm the
lexical COENG form. Without that confirmation, the form is available to
segmentation but remains invalid in strict spellcheck and is excluded from
autocomplete. Exact RAC headwords inherit RAC's lexical authority.</p>
<div class="toolbar">
<select id="status-filter" aria-label="Filter by status">
<option value="all">All candidates</option><option value="pending">Pending</option>
<option value="approved">Approved</option><option value="rejected">Rejected</option>
<option value="coeng-pending">COENG verification pending</option>
</select>
<button type="button" id="save-review">Save review TSV</button>
<button type="button" id="clear-local">Discard browser changes</button>
</div>
{"".join(sections)}
<script>
const storageKey = "khmer-official-lexicon-review-v1";
const cards = [...document.querySelectorAll(".entry")];
const keyFor = card => [card.dataset.source, card.dataset.locator,
  card.dataset.candidate].join("\\t");
let saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");

function setStatus(card, status, markForExport = true) {{
  card.dataset.status = status;
  if (markForExport) card.dataset.export = "true";
  card.classList.remove("pending", "approved", "rejected");
  card.classList.add(status);
  card.querySelector(".status strong").textContent = status;
  saved[keyFor(card)] = {{
    status,
    approved_word: card.querySelector(".approved-word").value.trim(),
    note: card.querySelector(".review-note").value.trim(),
    coeng_status: card.querySelector(".coeng-verified")?.checked ? "verified" :
      (card.dataset.needsCoengReview === "true" ? "pending" : "not_applicable"),
    export: card.dataset.export === "true"
  }};
  localStorage.setItem(storageKey, JSON.stringify(saved));
  applyFilter();
}}

for (const card of cards) {{
  const state = saved[keyFor(card)];
  if (state) {{
    card.querySelector(".approved-word").value = state.approved_word || card.dataset.candidate;
    card.querySelector(".review-note").value = state.note || "";
    if (card.querySelector(".coeng-verified")) {{
      card.querySelector(".coeng-verified").checked = state.coeng_status === "verified";
    }}
    card.dataset.export = String(Boolean(state.export));
    setStatus(card, state.status, false);
  }}
  card.querySelectorAll("button[data-action]").forEach(button => {{
    button.addEventListener("click", () => {{
      if (button.dataset.action === "approved" &&
          !card.querySelector(".approved-word").value.trim()) {{
        card.querySelector(".approved-word").value = card.dataset.candidate;
      }}
      setStatus(card, button.dataset.action);
    }});
  }});
  card.querySelectorAll("input").forEach(input => input.addEventListener("change", () => {{
    setStatus(card, card.dataset.status);
  }}));
}}

function applyFilter() {{
  const wanted = document.querySelector("#status-filter").value;
  cards.forEach(card => {{
    const coengPending = card.dataset.needsCoengReview === "true" &&
      !card.querySelector(".coeng-verified")?.checked;
    card.hidden = wanted !== "all" &&
      !(wanted === "coeng-pending" ? coengPending : card.dataset.status === wanted);
  }});
}}
document.querySelector("#status-filter").addEventListener("change", applyFilter);

function reviewTsv() {{
  const quote = value => String(value || "").replace(/[\\t\\r\\n]+/g, " ").trim();
  const rows = [["source", "locator", "candidate", "status", "approved_word",
    "coeng_status", "note"]];
  for (const card of cards) {{
    if (card.dataset.export !== "true" || card.dataset.status === "pending") continue;
    rows.push([
      card.dataset.source, card.dataset.locator, card.dataset.candidate,
      card.dataset.status,
      card.dataset.status === "approved" ? card.querySelector(".approved-word").value : "",
      card.querySelector(".coeng-verified")?.checked ? "verified" :
        (card.dataset.needsCoengReview === "true" ? "pending" : "not_applicable"),
      card.querySelector(".review-note").value
    ]);
  }}
  return rows.map(row => row.map(quote).join("\\t")).join("\\n") + "\\n";
}}

document.querySelector("#save-review").addEventListener("click", async () => {{
  const content = reviewTsv();
  if (window.showSaveFilePicker) {{
    const handle = await window.showSaveFilePicker({{
      suggestedName: "official_lexicon_review.tsv",
      types: [{{description: "TSV review", accept: {{"text/tab-separated-values": [".tsv"]}}}}]
    }});
    const writable = await handle.createWritable();
    await writable.write(content);
    await writable.close();
  }} else {{
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob(["\\ufeff", content],
      {{type: "text/tab-separated-values;charset=utf-8"}}));
    link.download = "official_lexicon_review.tsv";
    link.click();
    URL.revokeObjectURL(link.href);
  }}
}});
document.querySelector("#clear-local").addEventListener("click", () => {{
  localStorage.removeItem(storageKey); location.reload();
}});
</script>
</html>
"""
    path = output / "official_lexicons.review.html"
    path.write_text(document, encoding="utf-8", newline="\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--rac", type=Path, default=DEFAULT_RAC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    normalizer = KhmerNormalizer()
    rac_lexical = {
        normalizer.normalize(line.strip())
        for line in args.rac.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    }
    rac = runtime_rac_forms(rac_lexical)
    review_decisions = load_review_decisions(args.review, normalizer)
    reports = [
        prepare_one(
            args.input / name,
            args.output,
            rac,
            rac_lexical,
            normalizer,
            review_decisions,
        )
        for name in SOURCE_CONFIG
    ]
    review_path = write_review_html(args.output, reports)
    manifest = {
        "schema_version": 1,
        "rac": str(args.rac),
        "packs": reports,
        "review": str(review_path),
    }
    manifest_path = args.output / "official_lexicons.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
