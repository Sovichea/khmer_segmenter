# Khmer Segmenter (C Port)

A high-performance, cross-platform C port of the Khmer Segmenter, capable of segmenting Dictionary-based and Rule-based Khmer text. This port is built using the [Zig Build System](https://ziglang.org/) for easy cross-compilation and dependency management.

## Platform Support

✅ **Windows** (x86_64, ARM64)  
✅ **Linux** (x86_64, ARM64)  
✅ **macOS** (x86_64, Apple Silicon)  
✅ **BSD** (FreeBSD, OpenBSD, NetBSD)

The codebase automatically adapts to the target platform, using platform-specific APIs for:
- **Threading**: Windows threads vs pthreads
- **High-precision timing**: QueryPerformanceCounter vs gettimeofday
- **Memory measurement**: Windows PSAPI, macOS Mach, Linux /proc
- **Rule Engine**: Zero-allocation, Hardcoded logic (No Regex dependency)

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

## Data Preparation

The C port requires compiled dictionary and frequency files to function. These are generated from the Python project.

If you are just building the C port, these files might already be in `port/common/`. If not, or if you modified the dictionary (`data/khmer_dictionary_words.txt`), run:

```bash
# From project root
python scripts/prepare_data.py
```

This will generate:
- `port/common/khmer_dictionary.kdict` (Baked Dictionary)
- `port/common/khmer_frequencies.bin` (Binary Frequencies)

## Building

Navigate to the `port/c` directory:
```bash
cd port/c
```

### Build Commands

```bash
# Build both debug and release for current platform
zig build

# Build debug version only
zig build debug

# Build release version only  
zig build release

# Cross-compile for Linux from Windows
zig build -Dtarget=x86_64-linux

# Cross-compile for macOS from Windows
zig build -Dtarget=aarch64-macos
```

### Output Structure

Binaries are organized by platform and build type:

```
zig-out/
├── win/bin/              # Windows builds
│   ├── khmer_segmenter.exe        (release)
│   └── khmer_segmenter_debug.exe  (debug)
├── linux/bin/            # Linux builds
│   ├── khmer_segmenter
│   └── khmer_segmenter_debug
└── macos/bin/            # macOS builds
    ├── khmer_segmenter
    └── khmer_segmenter_debug
```

**Size comparison:**
- Release build: ~32 KB (optimized)
- Debug build: ~2.6 MB (with symbols)

## Usage

The executable supports direct text input, multi-file processing, and benchmarking. **All segmentation results are automatically saved to files.**

### Common Flags
- `--input <path...>`: Path to one or more input files.
- `--output <path>`: Path to save result (defaults vary by mode).
- `--threads <N>`: Number of threads for batch processing or benchmark (default: 4).
- `--limit <N>`: Stop processing after N lines across all input files.
- `--benchmark`: Run performance suite. Can be combined with `--input`.

### Segment Raw Text
```bash
# Direct text input via CLI
./zig-out/win/bin/khmer_segmenter.exe "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"

# Console output: ខ្ញុំ | ស្រឡាញ់ | ប្រទេស | កម្ពុជា
# File output: segmentation_results.txt (contains original + segmented)
```

> [!NOTE]
> Results are saved to `segmentation_results.txt` by default, or specify `--output` to customize.

### Batch File Processing
Process one or more files and save to a single output file. The output includes both original and segmented text for each line.

```bash
# Process multiple files with 8 threads and a limit of 1000 lines
./zig-out/linux/bin/khmer_segmenter --input file1.txt file2.txt --output results.txt --threads 8 --limit 1000
```

**Output format** (`results.txt`):
```
Original:  ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា
Segmented: ខ្ញុំ | ស្រឡាញ់ | ប្រទេស | កម្ពុជា
----------------------------------------
Original:  ...
Segmented: ...
```

### Benchmarking
Run performance tests using the built-in sample or your own data. Results are always saved to file.

```bash
# Use built-in sample text (saves to benchmark_results.txt)
./zig-out/macos/bin/khmer_segmenter --benchmark --threads 4

# Benchmark using your actual data
./zig-out/win/bin/khmer_segmenter.exe --input corpus.txt --benchmark --threads 4 --limit 50000 --output segmented_benchmark.txt
```

> [!NOTE]
> When `--benchmark` is used with `--input`, it runs both Sequential (1-thread) and Concurrent (N-threads) benchmarks on the provided text and saves the segmented results to the `--output` path.

## Performance Comparison

Performance metrics on various workloads:


| Metric | Performance | Notes |
| :--- | :--- | :--- |
| **Micro Latency** | ~0.36 ms | Single Thread (Seq) |
| **Micro Throughput** | ~10,970 calls/s | 4 Threads |
| **Macro Throughput** | ~30,838 lines/s | 4 Threads (File I/O) |
| **Memory (Init)** | ~4.8 MB | Dictionary Load |
| **Memory (Overhead)** | ~0.2 MB | Multi-thread overhead |

*> Note: Benchmarks run on standard consumer hardware (Linux/Ryzen 7) with 4 threads.*

## Platform-Specific Notes

### Windows
- UTF-8 console support is automatically enabled for proper Khmer text display
- Requires no additional setup

### Linux/Unix
- POSIX threads (pthread) library is automatically linked
- Tested on Ubuntu, Debian, and Arch Linux

### macOS  
- Supports both Intel and Apple Silicon
- Uses native Mach APIs for memory measurement

### WSL (Windows Subsystem for Linux)
For best performance and to avoid permission issues with Zig cache:
```bash
# Option 1: Work in WSL native filesystem
cp -r /mnt/c/path/to/project ~/project
cd ~/project/port/c
zig build

# Option 2: Clear cache in Windows directories
rm -rf .zig-cache zig-out
zig build
```

## File Output

All operations automatically save results to files with both original and segmented text:

| Operation | Default Output File | Override with |
|-----------|-------------------|---------------|
| Direct text input | `segmentation_results.txt` | `--output` |
| File processing | `segmentation_results.txt` | `--output` |
| Benchmark (internal) | `benchmark_results.txt` | `--output` |
| Benchmark (with input) | Specified by `--output` | Required |

