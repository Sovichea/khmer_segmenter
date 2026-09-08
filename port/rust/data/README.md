# Rust language-pack data

This directory contains the canonical generated language pack for the Rust and
WebAssembly ports:

- `khmer_dictionary.klex.json` is the editable KLEX source with explicit model
  costs and lexical-policy flags.
- `khmer_dictionary.kdict` is the compiled KDIC v2 runtime pack.

Regenerate both files from the repository root after rebuilding the canonical
model:

```bash
python scripts/export_rust_language_pack.py
```

The exporter preserves the trained costs, typo corrections, and segmentation,
spelling, autocomplete, and supplemental flags. Python and Rust compile this
KLEX to byte-identical KDIC output.

The software is MIT licensed, but these linguistic files are derived from
**Khmer Dictionary 2022** of the National Council of Khmer Language, Royal
Academy of Cambodia, as extracted and published by **Seanghay Hay
(`seanghay`)**. They are redistributed for noncommercial use with attribution.
See [DATA_LICENSE.md](../../../DATA_LICENSE.md) and the
[original Hugging Face publication](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k).
