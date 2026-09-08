# 0.2 Release Checklist

The Python package and Rust crate identify the stable `0.2.0` release line.

Completed engineering gates:

- one KDIC v2 policy model for segmentation, spelling, completion, and reviewed corrections;
- additive base-pack plus application KLEX compilation in Python and Rust;
- typed diagnostic kinds with stable serialized names;
- one-pass analysis in Python, Rust, and WASM;
- normalized and original-source ranges for editor integrations;
- structural KDIC validation before runtime lookup;
- editor-facing spellcheck, completion, memory, and false-positive benchmark tooling.
- removal of internal-word hyphenation and KHYP assets;
- mapped word-break opportunities in Python, Rust, WASM, and the CLI;
- an approved, project-owned 300-sentence regression benchmark;
- Python/Rust pack conformance plus native Rust, WASM, and C build checks;
- first-use, steady-state spellcheck, completion, and memory benchmark tooling;
- final wheel/sdist metadata, attribution, and bundled-data audits.

Stable `0.2.0` remains blocked by evidence, not implementation completeness:

- run false-positive evaluation on reviewed valid Khmer prose, including names,
  official terminology, compounds, and mixed-language text;
- retain the reviewed visual-mode classifications as release regression cases.

The current segmentation-reviewed set produces 59 diagnostics on 54 lines in
lexical mode and seven diagnostics on six lines in visual mode. Lexical-mode
COENG DA/TA warnings are intentional. Six visual-mode occurrences are now
classified as reviewed vocabulary, common variants, names, or an intentional
unknown-name diagnostic. These figures are not an independent false-positive
estimate because the benchmark was reviewed for segmentation, not
comprehensively for spelling policy. The classifications are recorded in
[`SPELLCHECK_REVIEW_0_2.md`](../benchmarks/curated/SPELLCHECK_REVIEW_0_2.md).

Do not publish merely because legacy benchmark scores are favorable. See
[Evaluation Guide](EVALUATION.md).
