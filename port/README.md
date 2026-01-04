# Khmer Segmenter Porting Guide

This guide provides a step-by-step manual for porting the `KhmerSegmenter` to new programming languages (e.g., Rust, Go, Java, Swift). The goal is to ensure identical behavior and high performance across all implementations.

## 1. Shared Data Resources

All ports must load data from the `port/common/` directory to ensure synchronization.

### 1.1 Dictionary (`khmer_dictionary_words.txt`)
- **Format**: Plain text, one word per line, UTF-8.
- **Loading**:
    - Read line by line.
    - Trim whitespace.
    - Store in a **HashSet** or **Trie** for O(1) / O(L) lookup.

### 1.2 Binary Frequencies (`khmer_frequencies.bin`)
Designed for fast loading (mmap-friendly). All integers are **Little Endian**.

| Offset | Type | Description |
| :--- | :--- | :--- |
| 0 | `char[4]` | Magic Header: `"KLIB"` |
| 4 | `uint32` | Version: `1` |
| 8 | `float32` | **Default Cost** (Use for known dictionary words missing from frequency list) |
| 12 | `float32` | **Unknown Cost** (Use for unknown chunks) |
| 16 | `uint32` | **Word Information Count** (N) |

**Entry Structure (Repeated N times):**
| Type | Description |
| :--- | :--- |
| `uint16` | Length of word in bytes (L) |
| `byte[L]` | UTF-8 Bytes of the word |
| `float32` | Cost of the word |

**Implementation Tip**:
- Read the Header first to get global costs.
- Load entries into a `HashMap<String, float>`.
- **Merge Logic**: If a word is in the Dictionary but NOT in this map, assign it `Default Cost`.

---

## 2. Normalization Engine

Before segmentation, text **MUST** be normalized to canonical Unicode order. This solves the "visual typing" problem (e.g., typing vowel before subscript).

### 2.1 Pre-Processing
1.  **Remove ZWS**: Delete all Zero Width Spaces (`\u200B`).
2.  **Fix Composites**: Replace split vowels with their combined forms.
    - `\u17C1` (េ) + `\u17B8` (ី) $\rightarrow$ `\u17BE` (ើ)
    - `\u17C1` (េ) + `\u17B6` (ា) $\rightarrow$ `\u17C4` (ោ)

### 2.2 Cluster Reordering
Khmer text is a sequence of **Clusters**. A cluster starts with a **Base Consonant** or **Independent Vowel**.
Parse the stream into clusters and sort the internal components of each cluster by this priority:

1.  **Base Char** (Consonant `0x1780-0x17A2` or Indep Vowel `0x17A3-0x17B3`)
2.  **Subscripts (Non-Ro)** (`\u17D2` + Consonant $\neq$ Ro)
3.  **Subscript Ro** (`\u17D2` + `\u179A`)
4.  **Registers** (`\u17C9` Muusikatoan, `\u17CA` Triisap)
5.  **Dependent Vowels** (`0x17B6-0x17C5`)
6.  **Signs** (`0x17C6-0x17D1`, `0x17D3`, `0x17DD`)

---

## 3. Viterbi Algorithm (The Core)

The segmenter finds the path of words that minimizes the total cost.
Let `dp[i]` be the minimum cost to reach character index `i`.
Initialize `dp[0] = 0`, `dp[1..n] = infinity`.

Iterate `i` from `0` to `n-1`:

### 3.1 Constraints & Recovery (Safety First)
Check if starting a segment at `i` violates Khmer rules (e.g., starting with a subscript).
- **Condition**: `text[i]` is a Subscript (`\u17D2`), Dep. Vowel, or Sign.
- **Action**: **Force 1-char skip**. Consumes `text[i]` with `Cost = Previous + UnknownCost + 50`.
- **Why**: Prevents crashes on typos like " ា".

### 3.2 Main Transitions (Priority Order)

Evaluate all possible segments starting at `i` and update `dp[i + length]`:

| Priority | Type | Check Logic | Transition Cost |
| :--- | :--- | :--- | :--- |
| **1** | **Numbers** | Arabic (`0-9`) or Khmer (`០-៩`) digits. Groups separators (.,) if sandwiched. <br>Includes leading currency (e.g., `$50`). | `1.0` |
| **2** | **Separators** | Punctuation, Symbols, Space. | `0.1` |
| **3** | **Acronyms** | Pattern: `(Cluster + .)+` (e.g., `ស.ភ.`). | `DefaultCost` |
| **4** | **Dictionary** | Check all substrings `text[i : i+1...k]` in Dictionary. | `WordCost` (from Map) |
| **5** | **Unknown** | If `text[i]` is Khmer: `GetClusterLength()`. <br> Else: length 1. | `UnknownCost` |

**Optimization Note**:
- For **Priority 4 (Dictionary)**, limit the loop to `min(n, i + MAX_WORD_LENGTH)`.
- **Unknown Penalty**: If an unknown cluster is a *single valid consonant* (e.g., `ក`), add `+10` cost to discourage splitting words into letters.

---

## 4. Backtracking

Once `dp[n]` is reached, reconstruct the path:
1.  Start at `current = n`.
2.  While `current > 0`:
    - Retrieve `prev_index` stored in `dp[current]`.
    - Extract string `text[prev_index : current]`.
    - Push to list.
    - Set `current = prev_index`.
3.  Reverse the list to get natural order.

---

## 5. Post-Processing Rules

The raw Viterbi output is logically correct but may be linguistically rigid. Apply these passes:

### 5.1 Rule-Based Engine (The "Polisher")

The Viterbi algorithm is probabilistic and sometimes makes "mathematically correct but linguistically wrong" splits, especially with rare names or typos. The Rule Engine runs **after** Viterbi to deterministic fix these edge cases.

**Common Rules**:
- **Merge Orphan Signs**: If a cluster ends with `\u17CB` (Bantoc), merge with previous.
- **Merge Technical IDs**: Group alphanumeric codes.

#### 5.1.1 Rule Structure
Rules are defined in `rules.json` (for reference) but should be implemented differently based on your language's constraints.

**JSON Schema**:
```json
{
    "name": "Consonant + Robat Merge Prev",
    "priority": 90,
    "trigger": { "type": "regex", "value": "^[\\u1780-\\u17A2]\\u17CC$" },
    "checks": [{ "target": "prev", "exists": true }],
    "action": "merge_prev"
}
```

#### 5.1.2 Implementation Strategy

**A. High-Level Languages (Python, JS, Go)**
For languages with rich managed runtimes, you can implement a **Generic Engine**:
1.  **Load JSON**: Read `rules.json` at startup.
2.  **Compile Regex**: Pre-compile `trigger.value` into Regex objects.
3.  **Iterate**: Loop through segments. For each segment, iterate through Rules (sorted by Priority).
4.  **Apply**: If `trigger` matches AND `checks` pass $\rightarrow$ execute `action`.

*Pros*: Easy to update rules without code changes.
*Cons*: Slower startup, higher memory overhead.

**B. Resource-Constrained Languages (C, C++, Rust, Embedded)**
For high-performance or embedded ports, **DO NOT** use JSON or Regex at runtime. It is too heavy.
The **C Port** in this repository implements this **Hardcoded** strategy.
Instead, **Hardcode** the logic into a static function.

**Recommended Pattern**:
1.  Create a function `apply_rules(segments)`.
2.  Iterate through segments.
3.  Use Fast Character Checks (Masks/Ranges) instead of Regex.

**Example (C-like Pseudo-code)**:
```c
// Rule: Consonant + Robat (\u17CC) -> Merge Previous
// Logic: Starts with Consonant (E1 9E [80-A2]) AND Ends with Robat (E1 9F 8C)
// Exact bytes: [0xE1, 0x9E, 0x??, 0xE1, 0x9F, 0x8C] (Total Length 6)

char* txt = seg->text;
if (strlen(txt) == 6) {
    // 1. Check Base Consonant (0x1780 - 0x17A2)
    // UTF-8 Pattern: E1 9E [80-A2]
    if (txt[0] == 0xE1 && txt[1] == 0x9E && txt[2] >= 0x80 && txt[2] <= 0xA2) {
        
        // 2. Check Robat Suffix (0x17CC)
        // UTF-8 Pattern: E1 9F 8C
        if (txt[3] == 0xE1 && txt[4] == 0x9F && txt[5] == 0x8C) {
            
            if (has_previous_segment()) {
                merge_with_previous(i);
                // Restart loop or adjust index to handle merged segment
                continue; 
            }
        }
    }
}
```

*Pros*: Blazing fast (nanoseconds), zero allocation, tiny binary size.
*Cons*: Requires recompilation to change rules.

### 5.2 Merge Consecutive Unknowns
Iterate through the segments. If you find adjacent segments that are **Unknown** (not in Dict, not Number, not Separator), merge them into a single token (e.g., names like "សុវិចិត្រ" if not in dict).

---



## 6. Checklist for Implementers

- [ ] Can load binary frequencies?
- [ ] Does Normalization pass all tests (Ro swapping, Composite fixing)?
- [ ] Does `$1,000.00` group as one token?
- [ ] Does `ស.ភ.ភ.ព.` group as one token?
- [ ] Does `ក` (single char) have higher cost than `ក` inside a word?
- [ ] **Performance**: Is it multi-threaded? (The algorithm is stateless and thread-safe).

And finally... **Welcome to the Family!** 🚀
