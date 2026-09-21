# Changelog

## 0.3.2

- Added the `unknown_word` diagnostic kind: out-of-vocabulary fragments are
  reported without suggestions instead of being corrected without a reference
  (`កូវីដ`, `ហ្វេសប៊ុក`).
- Kept whole unknown words and real typos on their normal handling
  (`ជូយ` -> `ជួយ`), and left names made of valid short words untouched.
- Exposed `unknown_word` in the Python, Rust, and WebAssembly APIs, independent
  of the profile `min_confidence`.

## 0.3.1

- Stopped typo detection from reporting common phrases as rare-compound typos
  (for example `ត្រីសួរ` and `អ្នកគ្រូ`).
- Added a reviewed phrase-collision exclusion list shared by the Python, Rust,
  and WebAssembly ports; approved pairs and real missing or extra `រ` typos are
  unchanged.

## 0.3.0

- Added safe Khmer word-break opportunities for layout engines, including a
  lone-consonant guard and runtime composition breaks that share the segmenter's
  cost model.
- Added a runtime word-composition policy that splits long curated forms into
  smaller accepted words, with a reviewed keep-list, a cost-dominance guard, and
  a completion length cap.
- Baked the composition split and completion cap into KDIC compilation so Rust,
  WASM, and C inherit the same behaviour.
- Added a selectable spelling authority (`official` by default, or `community`)
  that accepts a reviewed practical lexicon of legacy words and variants
  (`អោយ`, `ឲ្យ`, and reviewed Chuon Nath / SBBIC forms), each tagged by source.
  The choice is shared by the Python, Rust, and WebAssembly APIs and both CLIs.
- Added a secondary Chuon Nath 1967 frequency source, blended into segmentation
  costs by default.
- Changed the default spelling accuracy to `visual`, and removed the
  strict/inclusive lexicon mode so every supplied pack participates in
  segmentation.
- Added a checksum-verified source fetch that restores fresh-clone
  reproducibility for repository scripts.

## 0.2.0

- Rebuilt the default model around attributed RAC Dictionary 2022 data.
- Separated segmentation evidence from curated spelling validity.
- Added layered KDIC v2 lexicons for RAC, reviewed terminology, community, and
  application/user dictionaries.
- Added whole-span typo diagnostics, reviewed correction pairs, Khmer-aware
  spelling suggestions, and conservative typing/document profiles.
- Added lexical and visual COENG DA/TA spelling policies.
- Added frequency-ranked word completion and unified mapped text analysis.
- Synchronized the Python, Rust, WASM, and command-line analysis interfaces.
- Made Rust dictionary loading explicit and hardened CLI dictionary discovery
  and failure reporting.
- Added source provenance to compiled language packs.
- Added an optional 126-entry pilot community pack for inclusive segmentation;
  its entries remain invalid for spelling and autocomplete.
- Added safe Khmer word-break opportunities for layout engines.
- Removed experimental internal-word hyphenation and the KHYP data format.

The 300-sentence benchmark is a human-reviewed, model-seeded regression suite.
It should not be interpreted as an independent measurement of general Khmer
language accuracy.
