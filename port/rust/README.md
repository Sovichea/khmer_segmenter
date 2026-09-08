# Rust Port Experiment

This is an experimental port of the Khmer Segmenter to Rust. It aims to replicate the logic of the C port while leveraging Rust's safety and concurrency features.

## Setup

Ensure you have Rust installed.

The Rust port includes a ready-to-load language pack under `data/`:

- `khmer_dictionary.kdict` is the optimized runtime file.
- `khmer_dictionary.klex.json` is its editable, reproducible source.

The linguistic data is derived from
[Seanghay Hay's attributed Khmer Dictionary 2022 publication](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k)
and is redistributed for noncommercial use with attribution. The Rust code is
MIT licensed, but the bundled language pack is governed by
[the linguistic data notice](../../DATA_LICENSE.md).
KDIC v2 contains segmentation costs, curated spelling and autocomplete flags,
and approved typo corrections in the same binary file. Supplemental entries
can therefore remain useful segmentation units without becoming accepted
spellings. KDIC v1 remains readable through the embedded compatibility data.
The complete conversion and embedded-deployment workflow is in
[Prepare Dictionaries for Python, C, and Rust](../../docs/EMBEDDED_DICTIONARY.md).

Regenerate the Rust pair after updating the canonical model:

```bash
python ../../scripts/export_rust_language_pack.py
```

```bash
cd port/rust
```

## Compilation

```bash
cargo build --release
```

## WebAssembly

The Rust library can load KDIC bytes directly and exports a browser wrapper for
segmentation, unknown-word status, typo diagnostics, and ranked correction
suggestions. File-system loading and the Rayon CLI are disabled in WASM builds.

```bash
cargo check --target wasm32-unknown-unknown \
  --no-default-features --features wasm

wasm-pack build --target web --out-dir pkg \
  . --no-default-features --features wasm
```

In JavaScript, fetch the compiled KDIC and initialize the wrapper once inside a
Web Worker:

```javascript
import init, { WasmKhmerSegmenter } from './pkg/khmer_segmenter.js';

await init();
const bytes = new Uint8Array(await fetch('./khmer_dictionary.kdict').then(r => r.arrayBuffer()));
const segmenter = new WasmKhmerSegmenter(bytes);
const analysis = segmenter.analyzeWithProfile('សម្បត្ត', 'typing');
const completions = segmenter.complete('សម្', 8);
```

Offsets returned to JavaScript use UTF-16 code units and can therefore be used
with `String.slice()` and browser editor ranges. The native Rust diagnostics
retain UTF-8 byte ranges.

The profile names and thresholds match Python: use `typing` for live editor
feedback, `document` for an explicit full-document check, and reserve
`high-recall` for experimental corpus review. Native Rust exposes the same API:

```rust
use khmer_segmenter::{KhmerSegmenter, SegmenterConfig, SpellcheckProfile};

let segmenter = KhmerSegmenter::from_path(
    "khmer_dictionary.kdict",
    SegmenterConfig::default(),
)?;

let diagnostics = segmenter.check_text(text, SpellcheckProfile::Typing)?;

// Preferred when the caller also needs tokens and original-source ranges.
let analysis = segmenter.analyze_text(text, SpellcheckProfile::Typing)?;
```

Every constructor requires a valid KDIC. Native applications can use
`from_path()`, while embedded and WASM integrations can use `from_bytes()`.
Callers that already loaded a `KDict` can pass ownership to `from_kdict()`.
This prevents a segmenter from being created in an unusable dictionary-less
state. Native ranges use UTF-8 byte offsets; the WASM wrapper converts ranges
to JavaScript UTF-16 code-unit offsets.

The native CLI exposes the same combined output:

```bash
khmer_segmenter analyze --profile typing "សួរស្តី"
```

Load a custom unified pack without recompiling the library:

```rust
use khmer_segmenter::{KhmerSegmenter, SegmenterConfig};

let segmenter = KhmerSegmenter::from_path(
    "custom.kdict",
    SegmenterConfig::default(),
)?;
```

The precompiled CLI can create the pack directly from a KLEX JSON file:

```bash
khmer_segmenter data compile custom.klex.json --output custom.kdict
```

## Usage

Run the binary directly or via `cargo run`.

### Spellcheck diagnostics

```bash
cargo run --release -- diagnose --profile typing "សម្បត្ត"
cargo run --release -- diagnose --profile document --input manuscript.txt
cargo run --release -- diagnose --dictionary custom.kdict --profile typing "ដេល"
cargo run --release -- --kdict custom.kdict analyze --profile typing "ដេល"
```

For installed binaries, `--dictionary` and `--kdict` can appear before or
after `diagnose`, `analyze`, or `word-breaks`. If neither is supplied, the CLI
checks `KHMER_SEGMENTER_KDICT`, the working directory (including `data/`), and
then the executable directory (including its `data` subdirectory). A missing
or invalid configured dictionary is an error; the CLI never silently runs
without lexical data.

### Segment Raw Text
```bash
# Direct input
cargo run --release -- "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"

# Special Characters / Currency
# Ensure you quote the string to prevent shell expansion
cargo run --release -- "$10,000.00"
# Output: $ | 10,000.00
```

### Benchmarking
```bash
# Run internal benchmark
cargo run --release -- --benchmark

# Run with input file
cargo run --release -- --input ../../dataset/corpus.txt --benchmark
```

### Word-break opportunities

Layout engines can request legal Khmer word-boundary byte offsets or insert
U+200B at those boundaries. The operation uses the segmenter's main KDIC, not
a separate hyphenation dictionary, and never adds breaks inside a dictionary
word.

```bash
cargo run --release -- word-breaks --format json "ខ្មែរស្រឡាញ់ខ្មែរ"
```

## Performance



| Metric | Performance | Notes |
| :--- | :--- | :--- |
| **Micro Latency** | ~0.34 ms | Single Thread (Seq) |
| **Micro Throughput** | ~10,909 calls/s | 4 Threads |
| **Macro Throughput** | ~31,250 lines/s | 4 Threads (File I/O) |
| **Memory (Init)** | ~2.2 MB | Dictionary Load |
| **Memory (Overhead)** | ~0.0 MB | Multi-thread overhead |
