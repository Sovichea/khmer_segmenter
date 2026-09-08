# Linguistic Data Notice

The software source code in this repository is licensed under the MIT License.
That license does not apply to the bundled Khmer linguistic data.

## Dictionary source and credit

The bundled dictionary is derived from **Khmer Dictionary 2022** of the
National Council of Khmer Language, Royal Academy of Cambodia, as extracted
and published by **Seanghay Hay (`seanghay`)**:

https://huggingface.co/datasets/seanghay/khmer-dictionary-44k

This dictionary dataset may be redistributed for **noncommercial use with attribution**.

## Included adaptations

This distribution includes normalized or generated adaptations for runtime
use:

- `khmer_dictionary_words.txt`
- `khmer_dictionary_official_2022_words.txt`
- `khmer_dictionary_author_curated_words.txt`
- `khmer_dictionary_rac_derived_words.txt`
- `khmer_dictionary_rac_phrase_exclusions.txt`
- `khmer_dictionary_rac_derived_review.tsv`
- `khmer_dictionary_rac_usage_words.txt`
- `khmer_dictionary_rac_usage_review.tsv`
- `khmer_dictionary_supplemental_words.txt` (segmentation-only legacy forms)
- `khmer_spellcheck_words.txt`
- `port/rust/data/khmer_spellcheck_words.txt` (synchronized Rust copy)
- `port/rust/data/khmer_dictionary.klex.json` (editable Rust language-pack source)
- `port/rust/data/khmer_dictionary.kdict` (compiled Rust runtime pack)
- `khmer_typo_corrections.tsv` (review workflow and approved exact pairs)
- `khmer_word_frequencies.json`
- `khmer_word_pos.json`
- `khmer_model_manifest.json`

The segmentation frequencies are generated only from RAC definitions and
examples: definition occurrences have weight 1, examples weight 3, and a
headword's occurrence in its own record has weight 0.25. The supplemental file
is a conservative decomposition of the project's earlier attributed runtime
dictionary. It is segmentation evidence only: it cannot make a spelling valid
or enter correction and autocomplete results. No uncurated corpus is used to
accept spellings. The model manifest records the source SHA-256, parameters,
record counts, and generated-file hashes.

The RAC-derived and RAC-usage lists are manually reviewed adaptations. They
promote reusable words found inside RAC headword phrases, definitions, or
examples, while their review tables retain rejected source variants and
fragments. They do not imply that every token occurring in dictionary prose is
an authoritative RAC headword.

The typo-correction table is separate from dictionary and frequency data.
Its pending observations retain source identifiers documented in
`benchmarks/typos/README.md`; entries derived from Pisethan's Khmer spelling
dataset are credited to that CC BY 4.0 source. Pending rows do not affect
runtime behavior. Maintainer-approved exact pairs are project curation and
must retain their per-row provenance when redistributed.

These bundled linguistic files remain under the same noncommercial and
attribution conditions. Redistribution must retain this notice and credit
Seanghay Hay and the Royal Academy of Cambodia source.

No restriction in this notice applies to independently supplied dictionaries
used with the MIT-licensed segmentation code.

## Optional community evidence pack

`community/panhapich_khmer_text_corpus.klex.json` and its compiled KDIC are a
small, AI-assisted and auditable, segmentation-only adaptation derived from
frequency and context observations in **Panhapich's Khmer Text Corpus**:

https://huggingface.co/datasets/Panhapich/khmer-text-corpus

The source is pinned in the pack metadata and credited to Panhapich. Its
dataset card currently labels the license as `other` and states that inherited
source licenses require confirmation. The repository does not redistribute
the source sentences or candidate cache. Downstream distributors must review
the upstream terms; provenance metadata is attribution, not a license grant.
