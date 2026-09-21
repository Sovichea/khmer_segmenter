# Khmer Viterbi Segmenter 0.3.2

Version 0.3.2 stops the typo detector from "correcting" out-of-vocabulary
words without a reference.

Highlights:

- Out-of-vocabulary fragments are now reported with the new diagnostic kind
  `unknown_word` and no suggestions, instead of a probable misspelling. For
  example `កូវីដ` reports `កូ` and `ហ្វេសប៊ុក` reports `ប៊ុ` as `unknown_word`.
- A whole unknown word that is not embedded in a longer run keeps its usual
  fuzzy handling, so a genuine typo such as `ជូយ` -> `ជួយ` is still a
  `probable_misspelling`.
- A name built only from valid short words (`សុខលីដា`) has no `unknown` flag
  and is left untouched; the segmenter does not guess.
- `unknown_word` is available in the Python, Rust, and WebAssembly APIs and is
  not suppressed by the profile `min_confidence`, because it is a statement
  about the lexicon, not a spelling confidence.

The bundled RAC-derived lexical data is redistributed for noncommercial use with
attribution. See `DATA_LICENSE.md` for its source, pinned revision, and terms.
The program source remains under the MIT license.

Known limitations:

- The segmenter still splits an out-of-vocabulary run into small tokens; it
  signals the unsupported fragments and leaves recognition to downstream NER,
  spellcheck, or an application dictionary.
- A name made entirely of valid short words cannot be detected as unknown.
- segmentation is lexical and deterministic, not full semantic parsing;
- the 300-sentence benchmark was seeded from model output and then reviewed, so
  it is a regression set rather than an independent linguistic gold standard.
