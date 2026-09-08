# Khmer Viterbi Segmenter 0.2.0

Version 0.2.0 turns the project into a portable Khmer lexical-analysis engine
for Python, Rust, WebAssembly, and embedded C applications.

Highlights:

- one KDIC v2 policy pack for segmentation, spelling, completion, reviewed
  corrections, lexical classes, and source provenance;
- unified analysis APIs with stable diagnostic kinds and editor-friendly source
  ranges;
- configurable lexical or visual handling of COENG DA and COENG TA variants;
- conservative typing and strict spellcheck profiles, with higher-recall
  analysis available explicitly;
- application dictionaries and correction pairs through the portable KLEX
  interchange format;
- safe Khmer word-break opportunities and ZWSP insertion for layout engines;
- equivalent core behavior in the Python, Rust, and WASM ports;
- an optional pilot community pack containing 126 AI-assisted, auditable,
  segmentation-only forms discovered from Panhapich's Khmer Text Corpus;
- an approved 300-sentence project regression benchmark.

The experimental hyphenation feature and KHYP data have been removed. Khmer
layout should use legal word boundaries rather than inserting Latin-style
hyphens inside words.

The bundled RAC-derived lexical data is redistributed for noncommercial use
with attribution. See `DATA_LICENSE.md` for its source, pinned revision, and
terms. The program source remains under the MIT license.

Known limitations:

- segmentation is lexical and deterministic, not full semantic parsing;
- unknown names, new terminology, and informal forms can still require an
  application dictionary;
- the 300-sentence benchmark was seeded from model output and then reviewed, so
  it is a regression set rather than an independent linguistic gold standard;
- the C port reads KDIC data but does not yet expose the full analysis API.

The pilot community pack does not grant spelling or autocomplete validity and
is loaded only when an application explicitly selects inclusive mode. Broader
community curation and contextual bigram/trigram reranking remain work for the
0.3 development line.
