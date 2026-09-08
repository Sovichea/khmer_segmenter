# Optional community lexicon

This directory contains the first conservative, AI-assisted, corpus-derived
community language pack approved for the v0.2 release as a pilot. It is
optional and is intended for `inclusive`
segmentation. Decisions are deliberately recorded so maintainers can audit,
reverse, or extend the curation rather than treating AI review as authority.

- `panhapich_khmer_text_corpus.review.json` records the accepted and rejected
  contextual decisions.
- `panhapich_khmer_text_corpus.klex.json` is the editable source.
- `panhapich_khmer_text_corpus.kdict` is the portable Python/Rust/WASM binary.
- `REPORT.md` summarizes the reviewed batch by category.

Every accepted entry is segmentation-only and supplemental. It is not accepted
by spellcheck and is not offered by autocomplete. Applications that want a
name or new term to become spelling-valid should add it to a reviewed user or
official lexicon pack instead.

The source corpus and 127,752-row candidate cache remain ignored and local.
See [the reproducible workflow](../docs/COMMUNITY_CORPUS.md) and the
[linguistic data notice](../DATA_LICENSE.md).
