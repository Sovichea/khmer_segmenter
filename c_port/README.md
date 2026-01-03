# Khmer Segmenter (C Port)

A high-performance C port of the Khmer Segmenter, capable of segmenting Dictionary-based and Rule-based Khmer text. This port is built using the properties of the [Zig Build System](https://ziglang.org/) for easy cross-compilation and dependency management.

## Prerequisites

### Install Zig Compiler
1.  Download Zig from [https://ziglang.org/download/](https://ziglang.org/download/).
    -   *Recommended version*: **0.13.0** or latest stable.
2.  Extract the archive to a location (e.g., `C:\zig` or `/usr/local/zig`).
3.  Add the folder containing `zig.exe` (or `zig` binary) to your system **PATH**.
4.  Verify installation:
    ```bash
    zig version
    ```

## Building

Navigate to the `c_port` directory:
```bash
cd c_port
```

### 1. Debug Build (Default)
Fast compilation, includes debug symbols and runtime safety checks. Slower execution speed.
```bash
zig build
```
*Output*: `zig-out/bin/khmer_segmenter.exe`

### 2. Release Build (Optimized)
Fully optimized for speed. **Recommended for production or benchmarking.**
```bash
zig build -Doptimize=ReleaseFast
```
*Output*: `zig-out/bin/khmer_segmenter.exe`

## Usage

The executable supports direct text input, multi-file processing, and benchmarking.

### Common Flags
- `--input <path...>`: Path to one or more input files.
- `--output <path>`: Path to save result (defaults to `segmentation_results.txt` if `--input` is used).
- `--threads <N>`: Number of threads for batch processing or benchmark (default: 4).
- `--limit <N>`: Stop processing after $N$ lines across all input files.
- `--benchmark`: Run performance suite. Can be combined with `--input`.

### Segment Raw Text
```bash
# Direct text input via CLI
.\zig-out\bin\khmer_segmenter.exe "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"

# Output: ខ្ញុំ | ស្រឡាញ់ | ប្រទេស | កម្ពុជា
```

### Batch File Processing
Process one or more files and save to a single output file.
```bash
# Process multiple files with 8 threads and a limit of 1000 lines
.\zig-out\bin\khmer_segmenter.exe --input file1.txt file2.txt --output results.txt --threads 8 --limit 1000
```

### Benchmarking
Run performance tests using the built-in sample or your own data.
```bash
# Use built-in sample text
.\zig-out\bin\khmer_segmenter.exe --benchmark --threads 10

# Benchmark using your actual data
.\zig-out\bin\khmer_segmenter.exe --input corpus.txt --benchmark --threads 12 --limit 5000 --output segmented_benchmark.txt
```
> [!NOTE]
> When `--benchmark` is used with `--input`, it runs both Sequential (1-thread) and Concurrent (N-threads) benchmarks on the provided text and saves the segmented results to the `--output` path.


## Performance Comparison

Comparing segmentation speed on a long text paragraph (~935 characters) 1000 iterations for Single Thread, 5000 iterations for 10 Threads:

| Version | Build Type | Time per Call | Throughput | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Python** | N/A | ~5.77 ms | ~173 calls/s | Baseline logic |
| **C Port** | Debug | ~8.56 ms | ~116 calls/s | Includes safety checks & unoptimized code |
| **C Port** | Release (Seq) | ~3.91 ms | ~255 calls/s | Single Thread (~1.5x Faster than Python) |
| **C Port** | **Release (10 Threads)** | **~0.31 ms*** | **~3235 calls/s** | **Massive Throughput scaling** |

*> * Effective time per call under load (1/Throughput).*
*> Note: Benchmarks run on standard consumer hardware. Multi-threaded throughput scales linearly with core count.*
