# Official Lexicon Experiment

## Purpose

This experiment evaluates whether lexicons extracted from official Khmer sources can improve spellchecking and, after separate validation, word segmentation. The first phase is local-only and Python-only. It must not alter the default RAC 2022 model or redistribute source publications before their reuse terms are confirmed.

The extracted records are OCR-assisted staging data. An official publication is an authoritative source, but that does not guarantee that an extracted spelling or lexical boundary is correct. Every new runtime entry therefore requires human review.

## Initial scope

- Include every available subject domain in one filterable review queue.
- Promote reviewed continuous Khmer words and proper names to experimental spellcheck overlays.
- Keep segmentation words and word frequencies identical to the RAC base model.
- Defer phrases, alternatives, entries containing punctuation or digits, and uncertain OCR.
- Keep the extracted PDFs, source records, review decisions, and generated overlays local.
- Leave Rust, WASM, C, PyPI packages, and the public web demo unchanged during this pilot.

## Data preparation

Build a consolidated staging table from the official-source TSV files while preserving:

- original and normalized forms;
- publisher, publication, year, domain, page, and source checksum;
- record identifier and bounding box or crop reference when available;
- translations, definitions, OCR confidence, and extraction status.

Normalize Unicode and remove invisible word-boundary characters used as formatting artifacts, but never silently repair OCR spelling. Deduplicate records by normalized form and source identity while retaining every provenance link. Existing RAC words remain available as extraction-quality references but do not enter the new-word promotion queue.

Classify each candidate as a continuous word, proper noun, phrase, abbreviation, punctuation-contaminated entry, or invalid/uncertain OCR. Source occurrence counts are evidence for review priority only; they must not be treated as general-language word frequencies.

## Browser review queue

Extend the local review page so each candidate shows its original record, normalized form, source page or crop, provenance, translations, confidence, domain, and current RAC segmentation.

The reviewer can record:

- `approved`, `rejected`, or `deferred` for spellchecking;
- a separately controlled segmentation decision, defaulting to `deferred`;
- a corrected canonical form;
- lexical class and domain;
- reviewer name, timestamp, and note.

Review progress should remain local and support deterministic TSV export and import. One source record may produce multiple lexical forms only through an explicit reviewer action.

The decision file should contain at least:

```text
candidate_id
corrected_form
lexical_class
domain
spellcheck_status
segmentation_status
reviewer
reviewed_at
note
provenance_reference
```

## Experimental overlays

Add a preparation command that validates the review decisions and generates a complete local data directory for a selected set of domains.

For the spellcheck-first phase:

- copy the RAC segmentation dictionary and frequencies without modification;
- create the spellcheck list from the RAC spellcheck lexicon plus approved overlay entries;
- reject unreviewed, malformed, empty, or deferred records;
- produce a manifest containing the parent RAC model, selected domains, decision-file hash, source checksums, entry counts, and `local_only: true`;
- load the generated directory through `KhmerSegmenter.from_data_dir(...)` without changing the stable public API.

Planned utilities:

```text
scripts/build_official_lexicon_review.py
scripts/promote_lexicon_overlay.py
review_decisions.tsv
```

These names describe the intended interfaces; their exact local output directory may be chosen by the scripts but must be excluded from distribution and version control by default.

## Later segmentation promotion

An entry may affect segmentation only after an explicit `segmentation_status=approved` review. Extraction counts must never become Viterbi frequencies.

Evaluate conservative candidate frequencies of `1`, `2`, and `5`, selecting the lowest value that keeps the reviewed term intact without causing unacceptable regressions. Specialized terms and proper names should remain opt-in domain overlays unless evidence supports inclusion in the default general-language model.

Rust and WASM overlay support should be designed only after the Python experiment shows measurable value and the redistribution policy is settled.

## Evaluation and release gates

Automated checks must verify:

- expected source counts, checksums, required columns, and normalization behavior;
- deterministic deduplication and byte-identical outputs from identical inputs;
- rejection of malformed, unreviewed, phrase-like, and punctuation-contaminated entries;
- preservation of all provenance fields;
- unchanged segmentation dictionary, frequencies, and segmentation output for a spellcheck-only overlay;
- approved-word recognition and deterministic typo-mutation correction recall;
- false-positive rate on valid RAC and curated words;
- diagnostic latency and memory use.

Run comparisons on the curated development benchmark, the local folklore corpus, RAC words, reviewed domain terms, and generated typo mutations. Keep the overlay experimental if clean-text segmentation changes, valid-word false positives increase materially, or runtime or memory regresses by more than 15 percent.

## Rights and distribution

Official-source attribution and provenance must remain attached to every reviewed entry. Until redistribution rights are confirmed for each source, do not commit generated overlays or extracted source content to release artifacts, publish them to PyPI, embed them in Rust/WASM packages, or deploy them in the public web demo.

The experiment code and review decisions may be versioned separately from restricted source material, provided they do not reproduce content whose redistribution has not been authorized.
