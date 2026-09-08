# Changelog

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
- Added safe Khmer word-break opportunities for layout engines.
- Removed experimental internal-word hyphenation and the KHYP data format.

The 300-sentence benchmark is a human-reviewed, model-seeded regression suite.
It should not be interpreted as an independent measurement of general Khmer
language accuracy.
