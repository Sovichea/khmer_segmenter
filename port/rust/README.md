# Rust Port Experiment

This is an experimental port of the Khmer Segmenter to Rust. It aims to replicate the logic of the C port while leveraging Rust's safety and concurrency features.

## Setup

Ensure you have Rust installed.

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
