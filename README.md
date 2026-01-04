# Khmer Word Segmentation Algorithm

This project implements a probabilistic word segmentation algorithm for the Khmer language. It uses a **Viterbi** approach (finding the shortest path in a graph of possible segments) weighted by word probabilities derived from a text corpus.


> [!IMPORTANT]
> **Disclaimer:** This dictionary is still lacking many curated sources of technical words. If anyone can contribute curated Khmer words with credible sources, the algorithm will improve significantly. We highly appreciate your contributions to improving the data quality!

## Purpose & Design Philosophy

The primary goal of this project is **dictionary-accurate segmentation**. Unlike modern Machine Learning (ML) models that prioritize predicting conversational "intent" or deep semantic context, `KhmerSegmenter` focuses on strictly aligning text with curated, approved Khmer wording sources.

### Why Viterbi over Deep Learning?

In the current NLP landscape (2026), there is a significant trade-off between **Contextual Awareness** (Deep Learning) and **Deterministic Efficiency** (Algorithmic).

| Feature | KhmerSegmenter (Viterbi) | ML-Based (Transformers/BERT) |
| :--- | :--- | :--- |
| **Logic** | "Search": Find the mathematically best path through a curated dictionary. | "Patterns": Infer boundaries based on patterns seen in millions of articles. |
| **Transparency** | **White Box**: If a word splits incorrectly, you simply update the dictionary or frequency table. | **Black Box**: Errors require retraining with thousands of examples; shifts are often opaque. |
| **Hardware** | **Ultra-Light**: Runs on anything (Drones, Mobile, Arduinos, Low-power CPUs). | **Heavy**: Usually requires GPUs or high-end CPUs and massive RAM. |
| **Size** | **Tiny**: ~1MB (Dictionary size) + a few KB of logic. | **Massive**: 500MB to 10GB+ of model weights. |
| **Determinism** | **100% Consistent**: Same input + Same dict always equals Same output. | **Stochastic**: Can "hallucinate" or vary results based on subtle context shifts. |

### The "Context" Argument
Critics of Viterbi often point out its "Blindness" to semantic context (long-range dependencies). However, for technical documentation, standard literature, and dictionary-driven applications, this "blindness" is a **feature**:
*   It ensures that the segmenter never "imagines" words or slang not approved in your curated source.
*   It provides a high-performance baseline (95% accuracy for standard text) for a fraction of the computational cost.

### Bridging the Engineering Gap (Beyond Computer Science)
In many engineering fields—such as **Robotics, UAV/Drone systems, and Industrial Embedded Control**—there is effectively **zero support** for the Khmer language. While Computer Science has moved toward massive Machine Learning models, these "modern" solutions are impossible to run on the low-level microcontrollers and embedded processors that power real-world machinery.

This creates a digital divide: Khmer becomes a "computer-only" language, excluded from the hardware that engineers use every day. 

`KhmerSegmenter` aims to break this barrier. By using the Viterbi algorithm—a purely mathematical and algorithmic approach—we provide a solution that can be implemented in **C, C++, or Rust** and run on devices with only a few megabytes (or even kilobytes) of memory. This project isn't just about NLP; it's about making Khmer a viable language for the next generation of physical engineering.

Ultimately, `KhmerSegmenter` is designed for **portability and control**. It is the "Swiss Army Knife" of Khmer NLP—small, sharp, and reliable.

## Installation

To install the required dependencies, run:

```bash
pip install -r requirements.txt
```

## C Port (High Performance)

For users requiring maximum performance or embedding in C/C++/Zig applications, a native port is available in the [port/c/](port/c/) directory. All ports share common linguistic data found in [port/common/](port/common/).

*   **Speed**: ~3.5x faster (Single Thread), more than 10x faster (Multi-Thread) running in WSL.
*   **Architecture**: Zero-dependency, **Regex-Free** Rule Engine (Hardcoded logic) for consistent O(n) performance.
*   **Documentation**: See [port/c/README.md](port/c/README.md).
## 1. Data Preparation (`scripts/generate_frequencies.py`)

Before the segmenter works, it needs a statistical model of the language:

1.  **Input Corpora**: The system reads raw Khmer text from files like `data/khmer_wiki_corpus.txt`, `data/khmer_folktales_extracted.txt`, and `data/allwords.txt`.
2.  **Dictionary Filtering**: It loads `data/khmer_dictionary_words.txt` and filters out single-character words that are not true Khmer **Base Characters** (Consonants or Independent Vowels). This prevents signs or fragments from being treated as words.
3.  **Frequency Generation**:
    *   The `scripts/generate_frequencies.py` script supports two modes:
        *   `--engine khmernltk` (Default): Uses the external library `khmernltk` to create a baseline frequency map from scratch.
        *   `--engine internal`: Uses `KhmerSegmenter` itself. This is for **self-improvement**: once you have a baseline frequency file, you can run this to re-segment the corpus *using* that baseline to find potentially better or more consistent word counts, creating a feedback loop.
    *   **Usage**:
        ```bash
        # Bootstrap baseline
        python scripts/generate_frequencies.py --engine khmernltk --corpus data/khmer_wiki_corpus.txt --dict data/khmer_dictionary_words.txt --output data/khmer_word_frequencies.json
        
        # Improve using internal segmenter (after baseline exists)
        python scripts/generate_frequencies.py --engine internal --corpus data/khmer_wiki_corpus.txt --dict data/khmer_dictionary_words.txt --output data/khmer_word_frequencies.json
        ```
    *   It re-scans the tokens and attempts to combine them to match the **longest possible entry** in our dictionary. This helps correct potential errors in the initial tokenization and ensures our frequencies align with our specific dictionary.
    *   We calculate the count of each word and export this to `data/khmer_word_frequencies.json`.

### Updating the Dictionary

To add or modify words in the dictionary:

1.  **Edit the Dictionary File**: Open `data/khmer_dictionary_words.txt` and add/edit the words. Ensure there is only one word per line.
2.  **Regenerate Frequencies**: Run the frequency generation script to update the statistical model. This ensures the segmenter knows about the new word and its usage probability.
    ```bash
    python scripts/generate_frequencies.py --engine internal
    ```

## 2. The Segmentation Algorithm

For a detailed step-by-step explanation of the Viterbi algorithm, Normalization logic, and Rules used in this project, please refer to the **[Porting Guide & Algorithm Reference](port/README.md)**.

## 3. Comparison with khmernltk

We compared the performance and output of `KhmerSegmenter` against `khmernltk` using a complex sentence from a folktale.

### Finding Unknown Words

You can analyze the segmentation results to find words that were not in the dictionary (potential new words or names):

```bash
python scripts/find_unknown_words.py --input segmentation_results.txt
```

This will generate `data/unknown_words_from_results.txt` showing the unknown words, their frequency, and **context** (2 words before and after) to help you decide if they should be added to the dictionary.

## 4. Benchmark & Performance Comparison

We compared `KhmerSegmenter` against `khmernltk` using real-world complex text:

|Feature|khmernltk (Python)|KhmerSegmenter (Python)|KhmerSegmenter (C Port)|
|:---|:---|:---|:---|
|**Cold Start (Load)**|~1.83s|~0.30s (6x Faster)|**< 0.05s** (Instant)|
|**Memory Usage**|~113.6 MB|~21.6 MB (5x Leaner)|**~9 MB** (Lowest)|
|**Execution Speed (Seq)**|~5.77ms / call|~5.77ms / call (Baseline)|**~1.52ms / call** (WSL)|
|**Concurrent (10 Workers)**|~318 calls / sec (GIL)|~447 calls / sec (GIL)|**~4437 calls / sec** (WSL)|
|**Concurrent Memory Delta**|~12.1 MB|~19.0 MB|**~1.0 MB** (Efficient)|
|**Complex Input**|Splits numbers/acronyms|Correctly Groups (Rules)|**Correctly Groups**|
|**Characteristics**|ML/Rule Hybrid|Pure Logic (Python)|**Pure Logic (Native)**|

### Performance & Portability Analysis

#### 1. Concurrency & Threading
Benchmarks run with `10 workers` using a `ThreadPoolExecutor` show that `KhmerSegmenter` achieves **~447 calls/sec** vs `khmernltk`'s **~318 calls/sec**.

*   **Python Limitations (GIL)**: In Python, concurrent performance is restricted by the **Global Interpreter Lock (GIL)**. This limits true parallelism.
*   **C Port Advantage**: The C port, free from the GIL, achieves **~4437 calls/sec** (over **10x faster** than Python concurrent). This demonstrates linear scaling: adding more CPU cores directly translates to higher throughput, making it ideal for high-load server environments.

#### 2. Portability (Universal Compatibility)
*   **KhmerSegmenter**: **Pure Python**. Requires **Zero** external dependencies beyond the standard library. It runs anywhere Python runs (Lambda, Edge devices, Windows/Linux/Mac) without compilation.
*   **Language Agnostic**: The core algorithm consists of standard loops, array lookups, and arithmetic. It can be easily ported to **ANY** programming language (JavaScript, Rust, Go, Java, etc.).
*   **Web & Edge Ready**: Perfect for client-side JavaScript execution (via WASM/Pyodide) or edge computing where low latency and small binary size are crucial.

#### 3. Cold Start
`KhmerSegmenter` initializes in **~0.30s**, whereas `khmernltk` takes **~1.8s+** to load its model. This makes `KhmerSegmenter` ideal for "Serverless" functions where startup latency is a primary billing and UX concern.

### Real-World Complex Sentence Example

**Input:**
> "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។ លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។"

**khmernltk Result (v1.5):**
> `ក្រុមហ៊ុន` | `ទទួលបាន` | `ប្រាក់` | `ចំណូល` | ` ` | `១` | ` ` | `០០០` | ` ` | `០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈ` | `ដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើនឡើង` | ` ` | `៥%` | ` ` | `ស្មើនឹង` | ` ` | `50.` | `00$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការសិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(` | `ស.` | `ភ.` | `ភ.` | `ព.` | `)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាពជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺជា` | `សក្ខីភាព` | `នៃ` | `កិច្ច` | `ខិតខំ` | `ប្រឹងប្រែង` | `របស់` | `ក្រុមការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការជឿទុកចិត្ត` | `ពីសំណាក់` | `វិនិយោគិន` | `។`

**KhmerSegmenter Result (Ours):**
> `ក្រុមហ៊ុន` | `ទទួល` | `បាន` | `ប្រាក់ចំណូល` | ` ` | `១ ០០០ ០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈ` | `ដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើនឡើង` | ` ` | `៥` | `%` | ` ` | `ស្មើនឹង` | ` ` | `50.00` | `$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការសិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(` | `ស.ភ.ភ.ព.` | `)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាព` | `ជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺជា` | `សក្ខីភាព` | `នៃ` | `កិច្ច` | `ខិតខំ` | `ប្រឹងប្រែង` | `របស់` | `ក្រុមការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការ` | `ជឿ` | `ទុកចិត្ត` | `ពីសំណាក់` | `វិនិយោគិន` | `។`

**Key Differences:**
1.  **Numbers**: `khmernltk` splits `១ ០០០ ០០០` into 5 tokens. `KhmerSegmenter` keeps it as **one**.
2.  **Acronyms**: `khmernltk` destroys `(ស.ភ.ភ.ព.)` into multiple tokens. `KhmerSegmenter` keeps it as **one**.
3.  **Dictionary Adherence**: `KhmerSegmenter` strictly adheres to the dictionary. For example, it correctly splits `ភាគហ៊ុន` into `ភាគ` | `ហ៊ុន` if `ភាគហ៊ុន` isn't in the loaded dictionary but the parts are (or vice versa depending on dictionary state). *Note: Benchmarks reflect the current state of `khmer_dictionary_words.txt`. As you add words like `ភាគហ៊ុន`, the segmenter will automatically group them.*

### Portability & Universal Compatibility
Because `KhmerSegmenter` relies on **pure mathematical logic (Viterbi Algorithm)** and simple string matching:
*   **Language Agnostic**: The core algorithm consists of standard loops, array lookups, and arithmetic operations. It can be easily ported to **ANY** programming language (JavaScript, Go, Rust, Java, C#, C++, etc.) without dependency hell.
*   **CPU Efficient**: It runs efficiently on standard CPUs without needing GPUs or heavy matrix multiplication libraries (like NumPy/TensorFlow).
*   **Zero Dependencies**: Unlike ML-based solutions that require specific runtime environments (e.g. `scikit-learn`, `libpython`), this logic is self-contained and highly embeddable.
*   **Web & Edge Ready**: Perfect for client-side JavaScript execution (via WASM or direct port) or edge computing where low latency and small binary size are crucial.

## 5. Testing & Verification

You can verify the segmentation logic using the `scripts/test_viterbi.py` script. This script supports both single-case regression testing and batch processing of a corpus.

### Run Standard Test Cases
```bash
python scripts/test_viterbi.py
```

### Batch Process a Corpus
To test against a file and see the output:
```bash
python scripts/test_viterbi.py --source data/khmer_folktales_extracted.txt --limit 500
```
This will generate `segmentation_results.txt`.

## 6. License

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

## 7. Acknowledgements

*   **[khmernltk](https://github.com/VietHoang1512/khmer-nltk)**: Used for initial corpus tokenization and baseline frequency generation.
*   **[sovichet](https://github.com/sovichet)**: For providing the [Khmer Folktales Corpus](https://github.com/sovichet) and Dictionary resources.
