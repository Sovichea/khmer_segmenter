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

**Sentence:**
> ឯ​ខ្មាំង​សត្រូវ​ឃើញ​គង់ហ៊ាន​បំបោល​ដំរី​ចូល​ដូច្នោះ គិត​ស្មាន​ថា​មេទ័ព​នេះ​ពូកែ​ណាស់​ ក៏​បាក់​ទ័ព​ចាញ់ រត់​យក​តែ​ព្រះ​អាយុ​ដោយ​ខ្លួន​ទៅ ។

**Results:**

| Feature | khmernltk | KhmerSegmenter (Ours) |
| :--- | :--- | :--- |
| **Time** | ~0.89s | **~0.001s** (Significantly Faster) |
| **Segmentation** | `ឯ` \| `ខ្មាំង` \| `សត្រូវ` \| `ឃើញ` \| `គង់` \| `ហ៊ាន` \| `បំបោល` \| `ដំរី` \| `ចូល` \| `ដូច្នោះ` \| ` ` \| `គិត` \| `ស្មាន` \| `ថា` \| `មេទ័ព` \| `នេះ` \| `ពូកែ` \| `ណាស់` \| ` ` \| `ក៏` \| `បាក់` \| `ទ័ព` \| `ចាញ់` \| ` ` \| `រត់` \| `យក` \| `តែ` \| `ព្រះអាយុ` \| `ដោយ` \| `ខ្លួន` \| `ទៅ` \| ` ` \| `។` | `ឯ` \| `ខ្មាំងសត្រូវ` \| `ឃើញ` \| `គង់` \| `ហ៊ាន` \| `បំបោល` \| `ដំរី` \| `ចូល` \| `ដូច្នោះ` \| ` ` \| `គិតស្មាន` \| `ថា` \| `មេទ័ព` \| `នេះ` \| `ពូកែ` \| `ណាស់` \| ` ` \| `ក៏` \| `បាក់ទ័ព` \| `ចាញ់` \| ` ` \| `រត់` \| `យកតែព្រះអាយុ` \| `ដោយខ្លួន` \| `ទៅ` \| ` ` \| `។` |
| **Characteristics** | Tends to split compound words (e.g., `ខ្មាំង` \| `សត្រូវ`). | Preserves compound words found in the dictionary (e.g., `ខ្មាំងសត្រូវ`, `បាក់ទ័ព`) and handles unknown phrases as chunks. |

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
