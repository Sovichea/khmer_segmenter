# Khmer Viterbi Segmenter 0.3.0

Version 0.3.0 makes segmentation safer for text layout and adds a reviewed
spelling-authority layer for editors and spellcheckers. It keeps the Python,
Rust, WebAssembly, and embedded C ports aligned.

Highlights:

- safe Khmer word-break opportunities for layout engines, with a lone-consonant
  guard and runtime composition breaks that share the segmenter's cost model;
- a runtime word-composition policy that splits long curated forms into smaller
  accepted words, using a reviewed keep-list, a cost-dominance guard, and a
  completion length cap; applications can opt out with `composition=False`;
- the composition split and completion cap are baked into KDIC compilation so
  Rust, WASM, and C inherit the same behaviour;
- a selectable spelling authority (`official` by default, or `community`) that
  accepts a reviewed practical lexicon of legacy words and common variants such
  as `អោយ` and `ឲ្យ`, plus reviewed Chuon Nath and SBBIC forms, each tagged by
  source; the choice is shared by the Python, Rust, and WebAssembly APIs and
  both CLIs;
- a secondary Chuon Nath 1967 frequency source blended into segmentation costs
  by default;
- the default spelling accuracy is now `visual`, so the COENG DA/TA forms that
  render equivalently are accepted without weakening segmentation;
- the strict/inclusive lexicon mode has been removed; every supplied pack
  participates in segmentation, with community evidence applied last;
- a checksum-verified source fetch restores fresh-clone reproducibility for the
  repository build scripts.

The bundled RAC-derived lexical data is redistributed for noncommercial use with
attribution. See `DATA_LICENSE.md` for its source, pinned revision, and terms.
The program source remains under the MIT license.

Known limitations:

- segmentation is lexical and deterministic, not full semantic parsing;
- unknown names, new terminology, and informal forms can still require an
  application dictionary;
- the reviewed practical spelling lexicon is intentionally permissive and
  source-tagged; consumers that need a narrower policy should filter by tag;
- the 300-sentence benchmark was seeded from model output and then reviewed, so
  it is a regression set rather than an independent linguistic gold standard;
- the C port reads KDIC data but does not yet expose the full analysis API.
