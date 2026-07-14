# Rust Port Experiment

This is an experimental port of the Khmer Segmenter to Rust. It aims to replicate the logic of the C port while leveraging Rust's safety and concurrency features.

## Setup

Ensure you have Rust installed.

The Rust port requires local dictionary artifacts that are not redistributed
by this repository. Obtain the dictionary from
[Seanghay Hay's original Hugging Face publication](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k),
review its terms, and follow [the data guide](../../docs/DATA.md) to generate
the ignored files under `port/common/`.
The complete conversion and embedded-deployment workflow is in
[Prepare Dictionaries for Python, C, and Rust](../../docs/EMBEDDED_DICTIONARY.md).

```bash
cd port/rust
```

## Compilation

```bash
cargo build --release
```

## Usage

Run the binary directly or via `cargo run`.

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

### Hyphenation Lookups
You can query the compiled `khmer_hyphenation.kdict` directly to fetch sub-word hyphenation break points (inserted with invisible Zero Width Space characters).

```bash
# Query a single word for its hyphenation mapping
cargo run --release -- --test-hyphenation "កក្រើករំជួល"
# Output: កក្រើក-រំជួល

# Segment an entire sentence and apply hyphenation lookups to each token
cargo run --release -- --hyphenate-sentence "សហប្រតិបត្តិការពហុភាគីគឺជារបាំងធុរកិច្ចដ៏សំខាន់មួយ។"
# Output: សហ-ប្រតិបត្តិការ | ពហុ-ភាគី | គឺជា | របាំង-ធុរកិច្ច | ដ៏ | សំ-ខាន់ | មួយ | ។
```

## Performance



| Metric | Performance | Notes |
| :--- | :--- | :--- |
| **Micro Latency** | ~0.34 ms | Single Thread (Seq) |
| **Micro Throughput** | ~10,909 calls/s | 4 Threads |
| **Macro Throughput** | ~31,250 lines/s | 4 Threads (File I/O) |
| **Memory (Init)** | ~2.2 MB | Dictionary Load |
| **Memory (Overhead)** | ~0.0 MB | Multi-thread overhead |
