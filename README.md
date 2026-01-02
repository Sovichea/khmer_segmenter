# Khmer Word Segmentation Algorithm

This project implements a probabilistic word segmentation algorithm for the Khmer language. It uses a **Viterbi** approach (finding the shortest path in a graph of possible segments) weighted by word probabilities derived from a text corpus.

## Installation

To install the required dependencies, run:

```bash
pip install -r requirements.txt
```

## 1. Data Preparation (`scripts/generate_frequencies.py`)

Before the segmenter works, it needs a statistical model of the language:

1.  **Input Corpora**: The system reads raw Khmer text from files like `data/khmer_wiki_corpus.txt` and `data/khmer_folktales_extracted.txt`.
2.  **Dictionary Filtering**: It loads `data/khmer_dictionary_words.txt` and filters out single-character words that are not in a predefined "Valid Single Consonant" whitelist (e.g., stopping random letters from being treated as words).
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
    python scripts/generate_frequencies.py --engine internal --corpus data/khmer_wiki_corpus.txt --dict data/khmer_dictionary_words.txt --output data/khmer_word_frequencies.json
    ```

## 2. The Segmentation Algorithm (`khmer_segmenter/viterbi.py`)

The core engine is a class `KhmerSegmenter` that uses **Viterbi Algorithm** (Dynamic Programming) to find the sequence of words with the *lowest total cost*.

### Cost Calculation
*   **Cost** = $-\log_{10}(Probability)$
*   **Probability**: The frequency of the word in our generated `khmer_word_frequencies.json` divided by total tokens.
*   **Unknown Word Cost**: A fixed high penalty (higher than any known word) to discourage splitting into unknown chunks if a known word is available.

---

### Step-by-Step Logic
When `segment(text)` is called:

#### Phase 1: Viterbi Forward Pass
We maintain an array `dp[i]` representing the *minimum cost* to segment the text suffix ending at index `i`.
We iterate `i` from `0` to `len(text)`. At each position `i`, we look forward to find potential next segments:

**1. Number Grouping**
*   **Check**: Is `text[i]` a digit (0-9 or ០-៩)?
*   **Action**: Look ahead to consume all consecutive digits, including separators like `,` or `.` (e.g., `1,200.50`).
*   **Cost**: Very low (prefer numbers staying together).

**2. Dictionary Match**
*   **Check**: Does `text[i:j]` exist in our dictionary?
*   **Action**: Loop `j` from `i+1` up to `min(len, i + max_word_length)`.
*   **Cost**: The pre-calculated word cost.

**3. Unknown Cluster (Fallback)**
*   **Check**: If it's not a dictionary word, what is the smallest valid "atomic" Khmer unit?
*   **Logic**: A Khmer "cluster" is defined structurally:
    *   `Base Consonant` + `(Coeng + Subscript)*` + `(Vowel/Diacritic)*`
    *   Example: `ខ្មែ` is ONE cluster (`ខ` + `្` + `ម` + `ែ`).
*   **Cost**: `Unknown Cost`.
*   **Penalty**: If the cluster is a **single consonant** (e.g., `ក`) and NOT in our whitelist of valid single words (like `ក៏`, `នៃ` are valid, but `ក` is usually a prefix), add an **Extra Penalty**. This forces the algorithm to prefer combining it if possible (e.g., avoiding `ក` | `ការ` vs `កការ`).

**4. Repair Mode (Constraints)**
*   **Rule**: A word cannot start with a subscript (Coeng `\u17D2`) or a dependent vowel.
*   **Action**: If we find a "orphan" vowel or coeng at `i`, we enter **Repair Mode**: strictly consume 1 character with a HUUUGE penalty. This prevents getting stuck on typos like " ា".

---

### Phase 2: Backtracking
We trace back the path of `dp[N]` to `dp[0]` to get the raw list of segments.
*   *Raw Output Example*: `["ខ្ញុំ", "ទៅ", "សាលា", "រ", "ៀ", "ន"]` (Hypothetical bad segmentation)

---

### Phase 3: Post-Processing Steps
The raw Viterbi output is good but often leaves small debris for unknown words or names.

**Step A: Snap Invalid Singles**
*   **Problem**: Typos or unknown names might result in loose consonants.
*   **Rule**: If a segment is 1 character long AND NOT in `valid_single_words` AND NOT a digit/symbol:
    *   **Action**: Attach it to the *previous* segment.
*   **Example**: 
    *   Raw: `["ឈ្មោះ", "ស", "៊", "ុ", "យ"]` (Bad scan of "Suy")
    *   Process: `ស` is valid? No. Snap to `ឈ្មោះ` -> `["ឈ្មោះស", "៊", "ុ", "យ"]` ... proceeds ... eventually merges.

**Step B: Merge Consecutive Unknowns**
*   **Problem**: Proper names (e.g., "សុវិជ្ជា") aren't in the dictionary. Viterbi might output `["សុ", "វិ", "ជ្ជា"]` (3 unknown clusters).
*   **Action**: We group consecutive "Unknown" segments into one block.
*   **Result**: `["សុវិជ្ជា"]`.

## 3. Concrete Examples

### Example 1: Known Words
**Input**: `កងកម្លាំងរក្សាសន្តិសុខ` (Security Forces)
1.  **Viterbi**: Finds `កងកម្លាំង` (Known Compound), `រក្សា` (Known), `សន្តិសុខ` (Known).
2.  **Path**: The path `កងកម្លាំង` -> `រក្សា` -> `សន្តិសុខ` has the lowest cost.
3.  **Result**: `កងកម្លាំង` | `រក្សា` | `សន្តិសុខ`

### Example 2: Names & Foreign Words
**Input**: `លោក ចន ស្មីត` (Mr. John Smith)
1.  **Viterbi**:
    *   `លោក`: Known.
    *   `ចន`: Known (John).
    *   `ស្មី`: Known (Ray/Light).
    *   `ត`: Known (Connector/Per).
    *   *Note*: Since `ស្មី` and `ត` are valid words, the segmenter prefers them over treating `ស្មីត` as a single unknown block.
2.  **Result**: `លោក` | ` ` | `ចន` | ` ` | `ស្មី` | `ត`

### Example 3: Invalid Single Consonant Penalty
**Input**: `ការងារ` (Job)
*   Dictionary has `ការងារ` as a compound word.
*   The algorithm prefers the longest match `ការងារ` over splitting into `ការ` | `ងារ` or smaller parts.
*   **Result**: `ការងារ`

**Input**: `តាប៉ិ` (Old man, slang/informal)
*   `តា` (Known "Grandpa").
*   `ប៉ិ` (Unknown).
*   **Result**: `តា` | `ប៉ិ` (Correctly keeps known word, flags rest as unknown).

## 4. Comparison with khmernltk

We compared the performance and output of `KhmerSegmenter` against `khmernltk` using a complex sentence from a folktale.

### Finding Unknown Words

You can analyze the segmentation results to find words that were not in the dictionary (potential new words or names):

```bash
python scripts/find_unknown_words.py --input segmentation_results.txt
```

This will generate `data/unknown_words_from_results.txt` showing the unknown words, their frequency, and **context** (2 words before and after) to help you decide if they should be added to the dictionary.

## 3. Supported Features

### Smart Segmentation
*   **Numbers**: Automatically groups digits, separators (e.g., `1,234.50`) and space-separated integers (e.g. `1 000 000`).
*   **Currency & Symbols**: Separates currency (e.g. `$`, `៛`) and percent (`%`) symbols from numbers.
*   **Acronyms**: Recognizes complex Khmer acronyms (e.g. `គ.ម.`, `ច្រ.ប្រ.`) as single tokens.
*   **Context for Single Consonants**: Prevents single consonants (e.g. `ក`) from being merged with neighbors if they are explicitly surrounded by separators or spaces.
*   **Interchangeable Characters**:
    *   **Coeng Ta/Da**: Recognizes words using either `្`+`ត` or `្`+`ដ` interchangeably.
    *   **Coeng Ro**: Handles variable ordering of Coeng Ro relative to other subscripts.
*   **Robustness**: Handles "orphan" subscripts (typos) without crashing.

### Post-Processing Steps
The raw Viterbi output is good but often leaves small debris for unknown words or names.

**Results:**

|Feature|khmernltk|KhmerSegmenter (Ours)|
|:---|:---|:---|
|**Cold Start (Load)**|~1.83s|**~0.22s** (8x Faster)|
|**Memory Usage (Load)**|~114.6 MB|**~19.1 MB** (6x Leaner)|
|**Execution Speed (Seq)**|~2.99ms / call|**~2.08ms / call** (1.4x Faster)|
|**Concurrent (10 Workers)**|~317 calls / sec|**~497 calls / sec** (1.5x Faster)|
|**Concurrent Memory Delta**|~2.2 MB|~19.7 MB (High Throughput)|
|**Complex Input**|`ក្រុមហ៊ុន... ១ ០០០ ០០០... (ស.ភ.ភ.ព.)`|`ក្រុមហ៊ុន... ១ ០០០ ០០០... (ស.ភ.ភ.ព.)`|
|**Segmentation**|`១` \| `០០០` \| `០០០` \| `(` \| `ស` \| `.` \| `ភ` \| ...|`១ ០០០ ០០០` \| `(ស.ភ.ភ.ព.)`|
|**Characteristics**|Tends to split numbers, symbols, and acronyms.|**Correctly groups** space-separated numbers, currencies, and complex acronyms.|

### Performance & Portability Analysis

#### 1. Concurrency & Threading
Benchmarks run with `10 workers` using a `ThreadPoolExecutor` show that `KhmerSegmenter` achieves **~497 calls/sec** vs `khmernltk`'s **~317 calls/sec**.
*   **GIL Bottleneck**: In the current Python implementation, concurrent performance is restricted by the **Global Interpreter Lock (GIL)**. This means that while we use multiple threads, Python only executes one thread's bytecode at a time, limiting the speedup to roughly the efficiency of the underlying C-calls or I/O.
*   **True Parallelism (Future Potential)**: Because our algorithm is purely mathematical and stateless (no complex model locking), porting it to a language without a GIL (like **C**, **C++**, **Rust**, or **Go**) would result in **dramatic performance increases**. In those environments, the 10 workers would run in true parallel across CPU cores, potentially reaching thousands or tens of thousands of calls per second.
*   **Memory Efficiency**: `KhmerSegmenter` loads its dictionary structures once (~19 MB). `khmernltk` adds ~115 MB. In a threaded environment, both share memory, but `KhmerSegmenter`'s small footprint and lightweight arithmetic make it significantly easier to scale.

#### 2. Portability (Zero-Dependency)
*   **KhmerSegmenter**: **Pure Python**. Requires **Zero** external dependencies (no `pip install` needed other than standard lib). It runs anywhere Python runs (Lambda, Edge devices, Windows/Linux/Mac) without compilation.
*   **khmernltk**: Requires `sklearn-crfsuite` and `python-crfsuite`, which are **C++ extensions**. These require compilation or binary wheels, making deployment on restricted environments (e.g. Alpine Linux, WASM, specific embedded hardware) significantly harder.

#### 3. Cold Start
`KhmerSegmenter` initializes in **~0.2s**, whereas `khmernltk` takes **~1.8s+** to load its model. This makes `KhmerSegmenter` ideal for "Serverless" functions where startup latency matters.

### Real-World Complex Sentence Example

### Real-World Complex Sentence Example

**Input:**
> "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។ លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។"

**khmernltk Result (v1.5):**
> `ក្រុមហ៊ុន` | `ទទួល` | `បាន` | `ប្រាក់` | `ចំណូល` | ` ` | `១` | ` ` | `០០០` | ` ` | `០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈ` | `ដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើន` | `ឡើង` | ` ` | `៥` | `%` | ` ` | `ស្មើ` | `នឹង` | ` ` | `50.00` | `$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការ` | `សិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(` | `ស` | `.` | `ភ` | `.` | `ភ` | `.` | `ព` | `.` | `)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាព` | `ជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺ` | `ជា` | `សក្ខីភាព` | `នៃ` | `កិច្ច` | `ខិតខំ` | `ប្រឹងប្រែង` | `របស់` | `ក្រុម` | `ការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការ` | `ជឿ` | `ទុកចិត្ត` | `ពី` | `សំណាក់` | `វិនិយោគិន` | `។`

**KhmerSegmenter Result (Ours):**
> `ក្រុមហ៊ុន` | `ទទួលបាន` | `ប្រាក់ចំណូល` | ` ` | `១ ០០០ ០០០` | ` ` | `ដុល្លារ` | `ក្នុង` | `ឆ្នាំ` | `នេះ` | ` ` | `ខណៈដែល` | `តម្លៃ` | `ភាគហ៊ុន` | `កើនឡើង` | ` ` | `៥` | `%` | ` ` | `ស្មើនឹង` | ` ` | `50.00` | `$` | `។` | ` ` | `លោក` | ` ` | `ទេព` | ` ` | `សុវិចិត្រ` | ` ` | `នាយក` | `ប្រតិបត្តិ` | `ដែល` | `បញ្ចប់` | `ការសិក្សា` | `ពី` | `សាកលវិទ្យាល័យ` | `ភូមិន្ទ` | `ភ្នំពេញ` | ` ` | `(ស.ភ.ភ.ព.)` | ` ` | `បាន` | `ថ្លែង` | `ថា` | ` ` | `ភាពជោគជ័យ` | `ផ្នែក` | `ហិរញ្ញវត្ថុ` | `នា` | `ឆ្នាំ` | `នេះ` | ` ` | `គឺជា` | `សក្ខីភាព` | `នៃ` | `កិច្ចខិតខំប្រឹងប្រែង` | `របស់` | `ក្រុមការងារ` | `ទាំងមូល` | ` ` | `និង` | `ការជឿទុកចិត្ត` | `ពីសំណាក់` | `វិនិយោគិន` | `។`

**Key Differences:**
1.  **Numbers**: `khmernltk` splits `១ ០០០ ០០០` into 5 tokens. `KhmerSegmenter` keeps it as **one**.
2.  **Acronyms**: `khmernltk` destroys `(ស.ភ.ភ.ព.)` into 11 tokens. `KhmerSegmenter` keeps it as **one**.
3.  **Compound Words**: `KhmerSegmenter` tends to group common compounds like `កិច្ចខិតខំប្រឹងប្រែង` and `ការជឿទុកចិត្ត` better than the CRF approach which fragments them.

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

## License

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

## 6. Acknowledgements

*   **[khmernltk](https://github.com/VietHoang1512/khmer-nltk)**: Used for initial corpus tokenization and baseline frequency generation.
*   **[sovichet](https://github.com/sovichet)**: For providing the [Khmer Folktales Corpus](https://github.com/sovichet) and Dictionary resources.
