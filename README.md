# Khmer Segmenter

Khmer Segmenter is a lightweight deterministic Khmer lexical segmentation
engine for formal documents, technical writing, research papers, search
indexing, spell-check preprocessing, and other infrastructure-level NLP tasks.
It combines Khmer Unicode normalization, dictionary lookup, frequency-weighted
Viterbi decoding, rule-based handling, and unknown-word recovery. No LLM or
runtime machine-learning model is required.

## Try it out!

🚀 **[Live Demo](https://sovichea.github.io/khmer_segment_webui_demo/)**

### 1. Editor Mode

<img src="assets/webui_editor_mode.png" width="800" alt="Editor Mode">

**Real-time Segmentation & Editing**
*   **Native Typing Experience**: Type quickly with zero lag.
*   **Instant Feedback**: Unknown words are underlined in red, updating in real-time (~0.3ms latency) as you type.
*   **Smart Paste**: Automatically re-segments pasted text while preserving formatting signals.

### 2. View Mode

<img src="assets/webui_view_mode.png" width="800" alt="View Mode">

**Visual Analysis & Navigation**
*   **Segmentation Blocks**: See exactly how the algorithm splits each word.
*   **Navigation Tools**: Jump instantly between unknown words to verify potential errors or new vocabulary.
*   **Analytics**: View word count and unknown word statistics.



## Acknowledgements

*   **[khmernltk](https://github.com/VietHoang1512/khmer-nltk)**: Used for benchmarking.
*   **[sovichet](https://github.com/sovichet)**: For providing the [Khmer Folktales Corpus](https://github.com/sovichet) and Dictionary resources.
*   **[phylypo](https://github.com/phylypo/segmentation-crf-khmer)**: For providing the `kh_data_10000b` dataset used for frequency analysis.

### Data Sources and Credits

| Project data | Original source | Credit | Source terms |
|:---|:---|:---|:---|
| RAC/NCKL Khmer Dictionary 2022 headwords | [Seanghay Hay's `khmer-dictionary-44k` extraction](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k) | National Council of Khmer Language, Royal Academy of Cambodia (dictionary authority); Seanghay Hay / `seanghay` (extraction and publication) | Research only; not for commercial use, as stated by the dataset card |
| khPOS training and evaluation tokens | [`ye-kyaw-thu/khPOS`](https://github.com/ye-kyaw-thu/khPOS) | Vichet Chea and Ye Kyaw Thu; manual POS annotation acknowledged to Sorn Kea and Leng Greyhuy | CC BY-NC-SA 4.0 |
| Khmer ALT training and evaluation tokens | [Zenodo record 3937914](https://doi.org/10.5281/zenodo.3937914) | Chenchen Ding, Masao Utiyama, and Eiichiro Sumita; developed by NICT and NIPTICT | The description states CC BY-NC-SA 4.0, while Zenodo's rights field displays CC BY 4.0; review the record before redistribution |

Source metadata was checked on 2026-07-01. Derived data retains upstream
usage and attribution requirements; the repository's MIT license applies only
to project code and does not relicense those datasets.

Source corpora are not redistributed in this repository. Download any corpus
you need directly from its original source above and keep it in the ignored
`dataset/` directory. The older local corpus inputs were credited to
[sovichet](https://github.com/sovichet) (Khmer folktales and dictionary
resources) and [phylypo](https://github.com/phylypo/segmentation-crf-khmer)
(`kh_data_10000b`); obtain them from those authors rather than from this repo.


> [!IMPORTANT]
> This is a lexical segmenter, not a semantic parser. Its production scope is
> formal Khmer text. Names, new terminology, slang, and mixed-language text may
> be returned as unknown spans for review instead of being semantically inferred.



## Why Dictionary-First?

**TL;DR:** Most ML-based Khmer segmentation relies on inconsistent Zero-Width Space (ZWS) annotations in training data. Since 100 people annotate ZWS differently, models learn "average human inconsistency" rather than linguistic correctness. I ignore ZWS entirely, using curated dictionaries and frequency-based Viterbi search for **deterministic, dictionary-accurate segmentation**.

### Key Advantages

✅ **100% Deterministic** – Same input always produces identical output  
✅ **Explainable** – Update dictionary/frequency = instant improvement  
✅ **Ultra-Fast** – ~0.34ms/call (C port) vs. ~5-50ms for transformers  
✅ **Portable** – Runs on embedded systems, mobile, web (WASM), and cloud  
✅ **No Model Inference** – Works without GPU, neural weights, or an LLM

### Real-World Applications

I've built this as **foundational infrastructure** for:

- **ML Research**: Clean training data for Khmer LLMs by providing dictionary-accurate baselines
- **Spellcheck/Grammar Tools**: Essential word boundary detection for text editors, IDEs, browsers, and mobile keyboards
- **Formal Production Text**: Technical documentation, research papers, and official writing
- **Unknown-Word Collection**: Review queues for names, terminology, loanwords, and emerging vocabulary

📖 **[Read the full design philosophy and use cases ▸](docs/DESIGN_PHILOSOPHY.md)**

## Installation

To install the required dependencies, run:

```bash
pip install -r requirements.txt
```

## Usage

```python
from pathlib import Path

from khmer_segmenter import KhmerSegmenter

data_dir = Path("khmer_segmenter/dictionary_data")
seg = KhmerSegmenter(
    data_dir / "khmer_dictionary_words.txt",
    data_dir / "khmer_word_frequencies.json",
)

# Segment text
text = "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល"
result = seg.segment(text)

print(result) 
# Output: ['ក្រុមហ៊ុន', 'ទទួល', 'បាន', 'ប្រាក់ចំណូល']
```

### Production Contract

- Identical normalized input and data versions produce identical output.
- Known vocabulary is decoded using the RAC/community dictionary and observed frequencies.
- Unknown Khmer clusters are preserved rather than guessed from semantics.
- Output represents lexical boundaries; a different valid compound convention may disagree.
- Pin the dictionary and frequency artifact versions for reproducible deployments.

### Segmentation with Lexical POS Metadata

Use `segment_with_metadata()` when preparing structured corpora:

```python
tokens = seg.segment_with_metadata("ខ្ញុំសរសេរឯកសារ")
```

Each item contains:

```python
{
    "text": "សរសេរ",
    "start": 5,
    "end": 10,
    "known": True,
    "type": "word",
    "source": "rac_2022",
    "frequency": 123,
    "pos": None,
    "pos_candidates": ["NN", "VB"],
}
```

`pos_candidates` are deterministic lexical candidates learned from the khPOS
training partition. `pos` is populated only when exactly one candidate exists.
This is not contextual POS tagging: ambiguous and unknown tokens return
`pos: None`. Existing `segment()` behavior remains unchanged.

Rebuild the POS artifact with:

```bash
python scripts/build_lexical_pos.py
```

## C Port (High Performance)

For users requiring maximum performance or embedding in C/C++/Zig applications, a native port is available in the [port/c/](port/c/) directory. All ports share common linguistic data found in [port/common/](port/common/).

*   **Speed**: ~16x faster (Single Thread), more than 30x faster (Multi-Thread) running in WSL.
*   **Architecture**: Zero-dependency, **Regex-Free** Rule Engine (Hardcoded logic) for consistent O(n) performance.
*   **Documentation**: See [port/c/README.md](port/c/README.md).
## 1. Data Preparation (`scripts/prepare_data.py`)

I've built a consolidated data pipeline to normalize text, generate frequencies, and compile binary dictionaries for all ports.

### Pipeline Steps:
1.  **Normalize**: Strips ZWS, ZWNJ, and fixes composite vowels/clusters in the corpus.
2.  **Generate Frequencies (Iterative)**: Uses the C-based `khmer_segmenter` to iteratively segment the corpus and refine word frequencies (Self-Supervised).
    > **Robustness**: This method starts with a clean slate (dictionary only) and converges to a stable frequency distribution in **minimal iterations** (typically 3 passes). It is robust against initial noise and effectively learns the corpus's natural word usage without external dependencies.
3.  **Compile Binaries**:
    *   `khmer_dictionary.kdict`: Optimized Hash Table for C/Zig port (Saved to `port/common/`).
    *   `khmer_frequencies.bin`: Legacy binary format (Saved to `port/common/`).

> [!NOTE]
> Corpora are intentionally not included. Download data from the credited
> original author, review its license, and place your local copy under the
> ignored `dataset/` directory.

### Usage

Run the pipeline to rebuild all data assets:
```bash
# Supply a locally downloaded corpus
python scripts/prepare_data.py --corpus dataset/my_corpus.txt --dict khmer_segmenter/dictionary_data/my_dict.txt

```

To add new words:
1.  Add word to `khmer_segmenter/dictionary_data/khmer_dictionary_words.txt`.
2.  Run `python scripts/prepare_data.py`.
3.  The new word is now compiled into `khmer_dictionary.kdict` and ready for the C port.

### Incremental Updates (`scripts/incremental_update.py`)

If you are adding new words and want to assign them frequencies based on your existing corpus (using the unknown word frequencies captured during `prepare_data.py`), use the incremental update script. This is faster than re-running the full pipeline.

1.  **Ensure you have unknown word data**: Run `prepare_data.py` at least once to generate `khmer_segmenter/dictionary_data/unknown_word_frequencies.json`.
2.  **Add new words**: Add your new words to `khmer_segmenter/dictionary_data/khmer_dictionary_words.txt`.
3.  **Run the update**:
    ```bash
    python scripts/incremental_update.py \
      --dict khmer_segmenter/dictionary_data/khmer_dictionary_words.txt \
      --freq khmer_segmenter/dictionary_data/khmer_word_frequencies.json \
      --unknown-freq khmer_segmenter/dictionary_data/unknown_word_frequencies.json
    ```
    This script will:
    *   Find words in your dictionary that are missing from the frequency list.
    *   Look up their count in `unknown_word_frequencies.json`.
    *   If not found, try to derive frequency from component words (for compounds).
    *   Otherwise, assign a default floor frequency.
    *   Update `khmer_word_frequencies.json`.

### Hyphenation (Word Processor Support)

For text editors and rendering engines that need to line-break long compound Khmer words without breaking semantic rules, `KhmerSegmenter` supports generating and querying **Hyphenation Pairs**.

1.  **Generate Text Pairs**: 
    Run `python generate_hyphenation_pairs.py` to process the official dictionary. This forces the Viterbi segmenter to break down long compound words into sub-dictionary words, producing `khmer_segmenter/dictionary_data/khmer_dictionary_hyphenation_pairs.txt` (e.g., `សហប្រតិបត្តិការ` -> `សហ-ប្រតិបត្តិការ`).
2.  **Build Binary KHYP Dict**:
    Run `python build_hyphenation_kdict.py` to compile the text pairs into an ultra-fast `O(1)` binary hash table (`port/common/khmer_hyphenation.kdict`) designed for zero-parsing startup in C/Rust ports.
3.  **Use in Rust/C**:
    The Rust CLI has built-in testing flags to demonstrate hyphenation lookups on segmented text using the invisible Zero Width Space (`\u200b`):
    ```bash
    cargo run --release --bin khmer_segmenter -- --hyphenate-sentence "សហប្រតិបត្តិការពហុភាគីគឺជារបាំងធុរកិច្ចដ៏សំខាន់មួយ។"
    ```

## 2. The Segmentation Algorithm

For a detailed step-by-step explanation of the Viterbi algorithm, Normalization logic, and Rules I use in this project, please refer to the **[Porting Guide & Algorithm Reference](port/README.md)**.

### Dictionary Provenance

The runtime dictionary combines two explicitly separated vocabularies:

- `khmer_dictionary_official_2022_words.txt`: normalized RAC/NCKL Khmer
  Dictionary 2022 headwords. Pronunciation strings are not imported.
- `khmer_dictionary_supplemental_words.txt`: community vocabulary absent from
  that reference. These entries are retained because names, compounds,
  loanwords, and modern terms are not invalid merely because they are absent.

Synchronize from [Seanghay Hay's research-use TSV extraction](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k),
which credits the National Council of Khmer Language at the Royal Academy of
Cambodia as the dictionary authority:

```bash
python scripts/sync_rac_dictionary.py --rac-tsv path/to/pairs.tsv
```

`khmer_dictionary_provenance.json` records the source and overlap counts. This
project uses the extraction as a non-profit Khmer community resource.

The synchronized extraction contained 44,706 rows. After deduplicating,
normalizing, and rejecting entries containing whitespace, 38,671 official
headwords were accepted; 6,015 were newly added to the runtime dictionary.
For a row such as `កករចិត្ត<TAB>ក-ក-ចិត`, only `កករចិត្ត` is imported.

## 3. Comparison with khmernltk

I compared the performance and output of `KhmerSegmenter` against `khmernltk` using a complex sentence from a folktale.

### Finding Unknown Words

Unknown output is expected for valid names, new technical terminology,
loanwords, and modern vocabulary that is not yet in the dictionary. It should
be treated as a review category, not automatically as a spelling error. Analyze
segmented output with:

```bash
python scripts/find_unknown_words.py --input segmentation_results.txt
```

This will generate `output/unknown_words_from_results.txt` showing the unknown words, their frequency, and **context** (2 words before and after) to help you decide if they should be added to the dictionary.

## 4. Benchmark & Performance Comparison

### Gold-Standard Accuracy

The current frequency model uses only the derived training partitions. The
following results are from stable, held-out test partitions and use Unicode
boundary scoring:

| Dataset | Sentences | Boundary Precision | Boundary Recall | Boundary F1 | Exact Sentence | Unknown Tokens |
|:---|---:|---:|---:|---:|---:|---:|
| khPOS test | 1,179 | 89.96% | 93.31% | **91.61%** | 37.49% | 3.34% |
| Khmer ALT POS test | 1,981 | 89.97% | 78.32% | **83.74%** | 0.30% | 4.54% |

khPOS is the more representative result for local formal/news-style Cambodian
text. Khmer ALT is translated Wikinews and uses a finer, often morpheme-level
annotation convention, so its lower recall and exact-match rate should not be
interpreted entirely as lexical errors. Boundary F1 is the primary metric;
exact sentence match is intentionally strict.

Training-only gold augmentation improved khPOS test F1 from 91.46% to 91.61%.
It changed ALT test F1 from 83.78% to 83.74%, showing that the two corpora do
not encode precisely the same segmentation standard.

### Frequency Coverage

The frequency artifacts combine 3,120,579 corpus tokens with 585,396 validated
tokens from the gold training partitions. The model contains 29,719 observed
frequency entries. Counts and document frequencies are recorded separately in
`khmer_word_frequencies_provenance.json`; dev and test sentences are excluded.

### Runtime Performance

Two runtime benchmarks are provided: **Real-Time Latency** (single sentence,
micro-benchmark) and **Batch Throughput** (large corpus, macro-benchmark).

### Benchmark Results
*Context: Comparison across two scenarios: (1) **Micro-Benchmark** (Latency/Real-time) simulating single-sentence requests, and (2) **Macro-Benchmark** (Throughput) processing a large 50k-line corpus.*

| Scenario | Metric | khmernltk | Python (v3) | C Port | Rust Port | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Micro-Benchmark** | Latency (Seq) | ~2.90 ms | ~2.21 ms | ~0.36 ms | **~0.34 ms** | Lower is better |
| **Micro-Benchmark** | Throughput (4-Thread) | ~330 calls/s | ~503 calls/s | ~10,970 calls/s | **~10,909 calls/s** | Higher is better |
| **Macro-Benchmark** | Throughput (4-Thread) | ~378 lines/s | ~585 lines/s | ~30,838 lines/s | **~31,250 lines/s** | File I/O + Process |
| **Memory Usage** | Baseline (Init) | ~113 MB | ~36 MB | ~4.8 MB | **~2.2 MB** | Dict Load |
| **Memory Usage** | Overhead (Conc) | ~12 MB | ~18 MB | ~0.2 MB | **~0.0 MB** | Efficiency |

*> Note: Benchmarks run on standard consumer hardware (Linux/Ryzen 7) with 4 threads.*

### Performance Analysis

#### 1. Massive Throughput (C Port)
With file-based benchmarking on Linux, the C port processes **~30,838 lines per second** using 4 threads, compared to ~553 lines/sec in Python. This **~55x speedup** validates the linear scaling and SIMD optimizations of the C implementation on multi-core systems, making it suitable for high-volume ETL pipelines.

#### 2. Concurrency & The GIL
Python-based segmenters (both ours and `khmernltk`) see **negative scaling** (0.9x speedup) when adding threads due to the **Global Interpreter Lock (GIL)** and overhead. Python is strictly limited to single-core CPU speeds for this workload.

#### 3. Low Latency & Cold Start
`KhmerSegmenter` initializes in **~0.28s**, whereas `khmernltk` takes **~1.8s+** to load its model. This makes `KhmerSegmenter` ideal for "Serverless" functions where startup latency is a primary billing and UX concern.

### Real-World Complex Sentence Example

**Input:**
> "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។ លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។"

**khmernltk Result (v1.5):**
> `ក្រុមហ៊ុន` | `ទទួលបាន` | `ប្រាក់` | `ចំណូល` | ` ` | `១` | ` ` | `០០០` | ` ` | `០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈ` | `ដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើនឡើង` | ` ` | `៥%` | ` ` | `ស្មើនឹង` | ` ` | `50.` | `00$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការសិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(` | `ស.` | `ភ.` | `ភ.` | `ព.` | `)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាពជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺជា` | `សក្ខីភាព` | `នៃ` | `កិច្ច` | `ខិតខំ` | `ប្រឹងប្រែង` | `របស់` | `ក្រុមការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការជឿទុកចិត្ត` | `ពីសំណាក់` | `វិនិយោគិន` | `។`

**KhmerSegmenter Result:**
> `ក្រុមហ៊ុន` | `ទទួល` | `បាន` | `ប្រាក់ចំណូល` | ` ` | `១` | ` ` | `០០០` | ` ` | `០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈ` | `ដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើនឡើង` | ` ` | `៥` | `%` | ` ` | `ស្មើនឹង` | ` ` | `50.00` | `$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការសិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(` | `ស.ភ.ភ.ព.` | `)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាព` | `ជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺជា` | `សក្ខីភាព` | `នៃ` | `កិច្ច` | `ខិតខំ` | `ប្រឹងប្រែង` | `របស់` | `ក្រុមការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការ` | `ជឿ` | `ទុកចិត្ត` | `ពីសំណាក់` | `វិនិយោគិន` | `។`

**Key Differences:**
1.  **Numbers**: `khmernltk` splits `១ ០០០ ០០០` into 5 tokens. `KhmerSegmenter` also splits them to support granular processing.
2.  **Acronyms**: `khmernltk` destroys `(ស.ភ.ភ.ព.)` into multiple tokens. `KhmerSegmenter` keeps it as **one**.
3.  **Dictionary Adherence**: `KhmerSegmenter` strictly adheres to the dictionary. For example, it correctly splits `ភាគហ៊ុន` into `ភាគ` | `ហ៊ុន` if `ភាគហ៊ុន` isn't in the loaded dictionary but the parts are (or vice versa depending on dictionary state). *Note: Benchmarks reflect the current state of `khmer_dictionary_words.txt`. As you add words like `ភាគហ៊ុន`, the segmenter will automatically group them.*

## 5. Portability & Universal Compatibility

`KhmerSegmenter` is designed with a "Run Anywhere" philosophy. Unlike modern ML models that are tied to heavy runtimes (Python/PyTorch/TensorFlow) and specific hardware, this algorithm is pure mathematical logic.

### Multi-Platform & Infrastructure
The implementation is verified and optimized for all major operating systems and architectures:
- ✅ **Windows, Linux, macOS, BSD** (x86_64, ARM64, Apple Silicon)
- ✅ **Cloud & Serverless**: Minimal cold start (<50ms in C) for AWS Lambda, Google Cloud Functions, and Edge Computing.
- ✅ **Embedded & IoT**: Runs on bare-metal C, RTOS, and microcontrollers (Arduino, ESP32, STM32) with as little as 9MB of RAM.

### Language Agnostic Architecture
The core Viterbi logic and Normalization rules rely only on standard data structures. It can be ported to any language:
- **High-Level**: Python (Official), JS/TS, Go, Java, C#.
- **Native**: C (Official), C++, Rust, Zig.
- **Web**: Compile to **WASM** for blazingly fast client-side performance.

### Zero-Dependency & Hardware Lean
- **Zero External Libs**: Works without `numpy`, `scikit-learn`, or `khmernltk` at runtime.
- **No GPU Required**: Strictly CPU-based, deterministic, and 100% reproducible across different hardware.

## 6. Testing & Verification

You can verify the segmentation logic using the `scripts/test_viterbi.py` script. This script supports both single-case regression testing and batch processing of a corpus.

### Run Standard Test Cases
```bash
python scripts/test_viterbi.py
```

### Batch Process a Corpus
To test against a file and see the output:
```bash
python scripts/test_viterbi.py --source path/to/your/local_corpus.txt --limit 500
```
This will generate `output/segmentation_results.txt`.

### Gold-Corpus Evaluation

The khPOS evaluator downloads the manually segmented corpus on first use, strips
its internal compound markers (`_`, `~`, and `^`), normalizes each gold token,
and scores Unicode code-point boundary offsets.

```bash
python scripts/evaluate_segmentation.py \
  --dataset khpos \
  --split test \
  --output results/khpos_eval.json
```

Use `--limit 100` for a smoke test or `--dataset-path PATH` for an existing
`train.all2` file. The report contains micro-averaged boundary precision,
recall and F1, exact sentence match, predicted-token unknown rate, latency, and
per-sentence boundary disagreements.

[khPOS](https://github.com/ye-kyaw-thu/khPOS) publishes one 12,000-sentence
source split under CC BY-NC-SA 4.0. Credit goes to contributors Vichet Chea
and Ye Kyaw Thu, with manual annotation assistance acknowledged to Sorn Kea
and Leng Greyhuy. The
loader derives stable 80/10/10 train/dev/test partitions from SHA-256 hashes of
sentence IDs. Only `train` may be used to build frequencies; report final
accuracy on `test`.

[Khmer ALT POS](https://doi.org/10.5281/zenodo.3937914) is also supported from
the official `km-nova.zip` release, credited to Chenchen Ding, Masao Utiyama,
and Eiichiro Sumita (NICT), with development by NICT and NIPTICT:

```bash
python scripts/evaluate_segmentation.py \
  --dataset khmer_alt_pos \
  --split test \
  --output results/khmer_alt_pos_eval.json
```

The archive publishes one 20,106-sentence source split and uses the same stable
80/10/10 derived partition policy. Its own license terms should be reviewed
before use; later Khmer Treebank material adds an academic-research restriction
beyond the license label shown in some dataset catalogs.

Training-only gold counts can be combined with the corpus counts reproducibly:

```bash
python scripts/augment_frequencies_from_gold.py
```

The corpus-only baseline remains in `khmer_word_frequencies_corpus.json`.
`khmer_word_frequencies_provenance.json` records gold occurrence counts,
document frequencies, excluded out-of-dictionary tokens, and split policy.
Gold-derived data artifacts retain the usage restrictions of their source
datasets and are not relicensed by the source-code MIT license.

## 7. License

MIT License

Copyright (c) 2026 Sovichea Tep

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

You are free to use, modify, and distribute this software, but you **must acknowledge usage** by retaining the copyright notice and license in your copies.
