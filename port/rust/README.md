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

## Performance



| Metric | Performance | Notes |
| :--- | :--- | :--- |
| **Micro Latency** | ~0.34 ms | Single Thread (Seq) |
| **Micro Throughput** | ~10,909 calls/s | 4 Threads |
| **Macro Throughput** | ~31,250 lines/s | 4 Threads (File I/O) |
| **Memory (Init)** | ~2.2 MB | Dictionary Load |
| **Memory (Overhead)** | ~0.0 MB | Multi-thread overhead |
