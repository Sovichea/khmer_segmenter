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
- `khmer_dictionary_supplemental_words.txt` (segmentation-only legacy forms)
- `khmer_spellcheck_words.txt`
- `port/rust/data/khmer_spellcheck_words.txt` (synchronized Rust copy)
- `khmer_typo_corrections.tsv` (review workflow and approved exact pairs)
- `khmer_word_frequencies.json`
- `khmer_word_pos.json`
- `khmer_dictionary_hyphenation_pairs.txt`
- `khmer_model_manifest.json`

The segmentation frequencies are generated only from RAC definitions and
examples: definition occurrences have weight 1, examples weight 3, and a
headword's occurrence in its own record has weight 0.25. The supplemental file
is a conservative decomposition of the project's earlier attributed runtime
dictionary. It is segmentation evidence only: it cannot make a spelling valid
or enter correction and autocomplete results. No uncurated corpus is used to
accept spellings. The model manifest records the source SHA-256, parameters,
record counts, and generated-file hashes.

The typo-correction table is separate from dictionary and frequency data.
Its pending observations retain source identifiers documented in
`benchmarks/typos/README.md`; entries derived from Pisethan's Khmer spelling
dataset are credited to that CC BY 4.0 source. Pending rows do not affect
runtime behavior. Maintainer-approved exact pairs are project curation and
must retain their per-row provenance when redistributed.

The experimental hyphenation pairs predate the strict RAC segmentation rebuild
and are preserved as a separate runtime asset; they are not presented as output
of that rebuild. These bundled linguistic files remain under the same
noncommercial and attribution conditions. Redistribution must retain this
notice and credit Seanghay Hay and the Royal Academy of Cambodia source.

No restriction in this notice applies to independently supplied dictionaries
used with the MIT-licensed segmentation code.
