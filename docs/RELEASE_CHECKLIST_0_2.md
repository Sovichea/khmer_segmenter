# 0.2 Release Checklist

The Python package and Rust crate now identify the same 0.2 release-candidate
line (`0.2.0rc3` in Python and SemVer-equivalent `0.2.0-rc.3` in Cargo).

Completed engineering gates:

- one KDIC v2 policy model for segmentation, spelling, completion, and reviewed corrections;
- additive base-pack plus application KLEX compilation in Python and Rust;
- typed diagnostic kinds with stable serialized names;
- one-pass analysis in Python, Rust, and WASM;
- normalized and original-source ranges for editor integrations;
- structural KDIC validation before runtime lookup;
- editor-facing spellcheck, completion, memory, and false-positive benchmark tooling.

Stable `0.2.0` remains blocked by evidence, not implementation completeness:

- finish and freeze the project-owned 300-sentence segmentation benchmark;
- run false-positive evaluation on reviewed valid Khmer prose, including names,
  official terminology, compounds, and mixed-language text;
- record first-use and steady-state spellcheck/completion results on supported targets;
- verify Python/Rust pack conformance and WASM behavior in release CI;
- review all bundled typo corrections and data attribution for the final artifact.

Do not promote the release candidate merely because legacy benchmark scores are
favorable. See [Evaluation Guide](EVALUATION.md).
