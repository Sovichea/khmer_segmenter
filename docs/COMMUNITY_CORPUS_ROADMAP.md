# Community Corpus Roadmap (0.3)

The community corpus will not be treated as a spelling dictionary and will not
silently promote frequent text to lexical authority. Its role is to improve
segmentation preference and completion while preserving curated spellcheck.

## Data layers

1. **RAC pack** — primary spelling and lexical authority.
2. **Reviewed lexicon packs** — names, borrowed terms, Pali vocabulary, and
   specialist terminology with provenance.
3. **User packs** — application- or user-approved vocabulary and corrections.
4. **Community pack** — corpus-derived segmentation evidence and common variants;
   excluded from strict spelling validity.

Strict mode uses the first three layers. A community-aware mode may use all four
for segmentation and completion, while diagnostics continue to distinguish a
standard spelling, an accepted common variant, and an unknown form.

## Proposed curation pipeline

1. Preserve document source, date, domain, and license metadata.
2. Remove ZWSP and normalize Unicode without losing original-source mappings.
3. Deduplicate documents and filter boilerplate, spam, malformed text, and
   near-identical reposts.
4. Segment with the frozen stable model and collect unknown spans, alternative
   boundaries, and n-gram counts.
5. Reject candidates already covered by RAC or reviewed lexicons after accepted
   visual normalization.
6. Group candidates into names, borrowings, common variants, probable typos,
   phrases, and unresolved forms.
7. Require evidence across multiple independent documents or sources; do not
   let one copied article create artificial frequency.
8. Review high-impact candidates before they enter a distributable pack.
9. Evaluate clean-text boundary accuracy, valid-prose false positives,
   completion ranking, memory, and latency before enabling the pack by default.

Long phrases should normally contribute n-gram evidence rather than become
indivisible dictionary entries. For example, repeated evidence for `ឥត គិត ថ្លៃ`
can improve completion of `ឥតគិតថ្លៃ` without declaring every observed phrase a
dictionary headword.

## Release boundary

The 0.2 release remains deterministic and RAC-led. Corpus-derived bigram and
trigram scoring must be optional in 0.3 until it demonstrates measurable gains
without increasing valid-text false positives or materially harming interactive
latency.
