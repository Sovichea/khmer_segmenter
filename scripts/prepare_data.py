#!/usr/bin/env python3
"""
Integrated Data Pipeline for Khmer Segmenter.
Consolidates normalization, frequency generation, and binary dictionary compilation.

Workflow:
1. Normalize Corpus: Strip control chars (ZWS/ZWNJ/ZWJ) and fix clusters.
2. Generate Frequencies: Tokenize normalized corpus and count dictionary words.
3. Export Binary Frequencies: Legacy KLIB format for other ports.
4. Compile KDict: Open-addressing hash table with costs and string pool for C port.
5. Cleanup: Remove temporary files.
"""

import os
import sys
import json
import math
import struct
import argparse
import re
import shutil
import subprocess
from collections import Counter

# Add project root to path
sys.path.append(os.getcwd())
try:
    from khmer_segmenter.normalization import KhmerNormalizer
    from khmer_segmenter import KhmerSegmenter
except ImportError:
    print("Error: Could not import khmer_segmenter package. Run from project root.")
    sys.exit(1)



# --- Utility Functions ---

def djb2_hash(s):
    h = 5381
    for char in s.encode('utf-8'):
        h = ((h << 5) + h) + char
        h &= 0xFFFFFFFF
    return h

def next_power_of_two(n):
    if n <= 0: return 1
    return 1 << (n - 1).bit_length()

def strip_control_chars(text):
    return text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')

def generate_variants(word):
    """Generates interchangeable variants for a word (Ta/Da and Ro-swap)."""
    coeng_ta = '\u17D2\u178F'
    coeng_da = '\u17D2\u178A'
    
    base_set = {word}
    if coeng_ta in word:
        base_set.add(word.replace(coeng_ta, coeng_da))
    if coeng_da in word:
        base_set.add(word.replace(coeng_da, coeng_ta))
        
    final_variants = set(base_set)
    final_variants.discard(word)
    
    p1 = re.compile(r'(\u17D2\u179A)(\u17D2[^\u179A])')
    p2 = re.compile(r'(\u17D2[^\u179A])(\u17D2\u179A)')
    
    for w in base_set:
        if p1.search(w):
            final_variants.add(p1.sub(r'\2\1', w))
        if p2.search(w):
            final_variants.add(p2.sub(r'\2\1', w))
            
    return final_variants

# --- Pipeline Steps ---

def get_corpus_files(paths):
    """Recursively finds files in paths. Filters for *_orig.txt in kh_data folders."""
    all_files = []
    for p in paths:
        if os.path.isfile(p):
            all_files.append(p)
        elif os.path.isdir(p):
            print(f"  > Scanning directory: {p}")
            for root, _, files in os.walk(p):
                for file in files:
                    if not file.endswith(".txt"): continue
                    
                    # Specific filter for experimental dataset
                    if "kh_data" in root and not file.endswith("_orig.txt"):
                        continue
                        
                    all_files.append(os.path.join(root, file))
    return all_files

def step_normalize_corpus(input_paths, output_path):
    print(f"[*] Step 1: Normalizing Corpus...")
    norm = KhmerNormalizer()
    count = 0
    
    files = get_corpus_files(input_paths)
    print(f"  > Found {len(files)} files to process.")
    
    with open(output_path, 'w', encoding='utf-8') as f_out:
        for path in files:
            if not os.path.exists(path): continue
            # print(f"  > Processing {path}") # Too verbose for many files
            with open(path, 'r', encoding='utf-8') as f_in:
                for line in f_in:
                    # KhmerNormalizer.normalize already strips ZWS/ZWNJ/ZWJ
                    f_out.write(norm.normalize(line))
                    count += 1
    print(f"  > Normalized {count} lines to {output_path}")

def step_generate_frequencies_iterative(corpus_path, dict_path, output_json, limit=None, iterations=3):
    print(f"[*] Step 2: Generating Frequencies (Iterative Approach)...")
    
    # Load Dict for filtering
    valid_words = set()
    with open(dict_path, "r", encoding="utf-8") as f:
        for line in f:
            w = strip_control_chars(line.strip())
            if w: valid_words.add(w)
            
            
    # Iteration Loop
    os.makedirs("temp", exist_ok=True)
    temp_freq_file = "temp/temp_frequencies.json"
    temp_freq_bin = "temp/temp_frequencies.bin"
    temp_segmented_output = "temp/temp_segmented.txt"
    current_freq_file = None 
    
    # Store previous iterations' counts for convergence check
    previous_counts = {}

    # Path to C Binary
    # Adjust based on platform if needed
    if sys.platform.startswith("linux"):
        c_binary = os.path.normpath("port/c/zig-out/linux/bin/khmer_segmenter")
    else:
        c_binary = os.path.normpath("port/c/zig-out/win/bin/khmer_segmenter.exe")
    if not os.path.exists(c_binary):
        print(f"Error: C binary not found at {c_binary}. Please run 'zig build release' in port/c/")
        return {}

    for i in range(iterations):
        print(f"  > Iteration {i+1}/{iterations} (Using C Port)...")
        
        # 1. Export Current Frequencies to Binary (if exists)
        if current_freq_file and os.path.exists(current_freq_file):
            step_export_binary_frequencies(current_freq_file, temp_freq_bin)
        else:
            # Create a "default" binary file if it doesn't exist?
            # Or pass nothing/default to C?
            # The C port likely needs a valid binary file if --freq is passed.
            # If default costs are needed, we can create a minimal binary file with no words but default costs.
            # OR, we can just NOT pass --freq for the first run if C supports it?
            # Let's create a minimal binary file with defaults.
            _create_default_binary_freq(temp_freq_bin)

        # 2. Run C Segmenter
        # khmer_segmenter.exe --input <corpus> --output <temp_out> --threads 10 --dict <dict> --freq <bin>
        cmd = [
            c_binary,
            "--input", corpus_path,
            "--output", temp_segmented_output,
            "--threads", "10",
            "--dict", dict_path,
            "--freq", temp_freq_bin
        ]
        
        if limit:
            cmd.extend(["--limit", str(limit)])
            
        print(f"    > Running C segmenter...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running C segmenter: {e}")
            break
            
        # 3. Process Output and Count
        print(f"    > Counting frequencies from output...")
        word_counts = Counter()
        processed = 0
        with open(temp_segmented_output, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|") # Assuming | is delimiter
                for t in parts:
                    t = strip_control_chars(t.strip())
                    if t in valid_words:
                        word_counts[t] += 1
                processed += 1
                if processed % 100000 == 0: print(f"    > Processed {processed} segmented lines...")
                
        # Save intermediate frequencies for next iteration
        sorted_counts = dict(sorted(word_counts.items(), key=lambda x: x[1], reverse=True))
        with open(temp_freq_file, "w", encoding="utf-8") as f:
            json.dump(sorted_counts, f, ensure_ascii=False, indent=4)
            
        current_freq_file = temp_freq_file
        print(f"    > Iteration {i+1} complete. Found {len(sorted_counts)} unique words.")

        # Convergence Check
        if previous_counts:
            # 1. Total Words Change
            prev_keys = set(previous_counts.keys())
            curr_keys = set(sorted_counts.keys())
            added = len(curr_keys - prev_keys)
            removed = len(prev_keys - curr_keys)
            
            # 2. Count Delta (for common words)
            common = prev_keys & curr_keys
            total_delta = 0
            for w in common:
                total_delta += abs(sorted_counts[w] - previous_counts[w])
            
            avg_delta = total_delta / len(common) if common else 0
            
            print(f"    [Convergence Metrics] vs Iteration {i}:")
            print(f"      - Words Added: {added}, Removed: {removed}")
            print(f"      - Common Words Count Delta (Avg): {avg_delta:.4f}")
            
            # Stop if converged? (Optional, but user asked to observe evolution)
            
        previous_counts = sorted_counts

    # Final Save
    shutil.copy2(temp_freq_file, output_json)
    
    # Save Unknown Frequencies if requested (or default behavior)
    # We need to collect them from the LAST iteration's segmentation.
    # To do this robustly, we should scan the temp_segmented_output one last time OR
    # integrate it into the counting loop above.
    
    # Re-scanning the latest segmented output to find UNKNOWN words
    print(f"    > extracting unknown word frequencies with context...")
    # Structure: { word: { 'count': int, 'examples': [] } }
    unknown_data = {}
    
    with open(temp_segmented_output, "r", encoding="utf-8") as f:
        for line in f:
            # Skip "Original:" lines if they exist
            if line.startswith("Original:"): continue
            
            # Remove "Segmented:" prefix if present
            content = line.strip()
            if content.startswith("Segmented:"):
                content = content[len("Segmented:"):].strip()
                
            parts = content.split("|")
            # Clean parts first to align indices
            cleaned_parts = [strip_control_chars(p.strip()) for p in parts]
            
            for i, t in enumerate(cleaned_parts):
                if t and t not in valid_words and not t.isdigit(): 
                    # Basic unknown filter (same as before)
                    # Note: Using isdigit() is rudimentary.
                    
                    if t not in unknown_data:
                        unknown_data[t] = {'count': 0, 'examples': []}
                    
                    unknown_data[t]['count'] += 1
                    
                    # Store up to 5 examples
                    if len(unknown_data[t]['examples']) < 5:
                        # Grab context: 3 words before, 3 words after
                        start = max(0, i - 3)
                        end = min(len(cleaned_parts), i + 4)
                        context_tokens = cleaned_parts[start:end]
                        # Highlight the unknown work in context (e.g. wrap with matching ** or similar, 
                        # but simple listing is fine. Let's use a list of tokens)
                        # Or better join them.
                        context_str = " | ".join(context_tokens)
                        unknown_data[t]['examples'].append(context_str)

    # Filter "junk" from unknown counts
    final_unknowns = {}
    for w, data in unknown_data.items():
        if len(w) > 1: # Skip single chars
             final_unknowns[w] = data
            
    # Determine output path for unknowns
    # Put it alongside output_json
    unknown_output_json = os.path.join(os.path.dirname(output_json), "unknown_word_frequencies.json")
    with open(unknown_output_json, "w", encoding="utf-8") as f:
        json.dump(final_unknowns, f, ensure_ascii=False, indent=4)
    print(f"  > Unknown word frequencies saved to {unknown_output_json}")

    # Cleanup
    for f_path in [temp_freq_file, temp_freq_bin, temp_segmented_output]:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except OSError as e:
                print(f"Warning: Could not remove temporary file {f_path}: {e}")
        
    print(f"  > Frequencies saved to {output_json}")
    return sorted_counts

def _create_default_binary_freq(output_path):
    # Create a minimal KLIB with default costs
    # default_cost = 10.0?, unknown = 15.0?
    # Logic similar to export but empty
    with open(output_path, 'wb') as f:
        f.write(b'KLIB')
        f.write(struct.pack('<I', 1)) 
        f.write(struct.pack('<ff', 10.0, 15.0)) # Default costs
        f.write(struct.pack('<I', 0)) # 0 words

def step_export_binary_frequencies(freq_json_path, output_bin_path):
    print(f"[*] Step 3: Exporting Binary Frequencies (KLIB)...")
    with open(freq_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    min_freq_floor = 5.0
    effective_counts = {}
    total_tokens = 0
    for w, c in data.items():
        w = strip_control_chars(w)
        eff = max(float(c), min_freq_floor)
        effective_counts[w] = eff
        total_tokens += eff
    
    min_prob = min_freq_floor / (total_tokens if total_tokens > 0 else 1)
    default_cost = -math.log10(min_prob)
    unknown_cost = default_cost + 5.0
    
    with open(output_bin_path, 'wb') as f:
        f.write(b'KLIB')
        f.write(struct.pack('<I', 1)) 
        f.write(struct.pack('<ff', default_cost, unknown_cost))
        f.write(struct.pack('<I', len(effective_counts)))
        for word in sorted(effective_counts.keys()):
            w_bytes = word.encode('utf-8')
            cost = -math.log10(effective_counts[word] / total_tokens)
            f.write(struct.pack('<H', len(w_bytes)))
            f.write(w_bytes)
            f.write(struct.pack('<f', cost))
    print(f"  > Binary frequencies written to {output_bin_path}")

def step_compile_kdict(dict_path, freq_json_path, output_kdict):
    print(f"[*] Step 4: Compiling KDict Binary...")
    
    # 1. Load Words and Generate Variants
    words = set()
    word_to_primary = {}
    with open(dict_path, 'r', encoding='utf-8') as f:
        for line in f:
            w = strip_control_chars(line.strip())
            if not w: continue
            
            # Simple Filter
            if len(w) == 1:
                cp = ord(w)
                if not ((0x1780 <= cp <= 0x17A2) or (0x17A3 <= cp <= 0x17B3)): continue
            if w.startswith('\u17D2'): continue
            if '\u17D7' in w: continue

            words.add(w)
            for v in generate_variants(w):
                if v not in words:
                    words.add(v)
                    word_to_primary[v] = w

    # Python's 'ឬ' Filtering
    words_to_remove = set()
    for w in list(words):
        if "ឬ" in w and len(w) > 1:
            if w.startswith("ឬ"):
                if w[1:] in words: words_to_remove.add(w)
            elif w.endswith("ឬ"):
                if w[:-1] in words: words_to_remove.add(w)
            else:
                parts = w.split("ឬ")
                if all((p in words or p == "") for p in parts): words_to_remove.add(w)
    
    if words_to_remove:
        print(f"  > Removing {len(words_to_remove)} compound OR words (unicode: U+17AC) for split enforcement.")
        words -= words_to_remove

    # 2. Costs
    with open(freq_json_path, 'r', encoding='utf-8') as f:
        raw_freq = json.load(f)
        
    min_freq_floor = 5.0
    counts = {}
    total_tokens = 0
    for w, c in raw_freq.items():
        w = strip_control_chars(w)
        eff = max(float(c), min_freq_floor)
        counts[w] = eff
        total_tokens += eff
        
    if total_tokens == 0: total_tokens = 1
    min_prob = min_freq_floor / total_tokens
    default_cost = -math.log10(min_prob)
    unknown_cost = default_cost + 5.0

    word_costs = {}
    max_bytes = 0
    for w in words:
        c = counts.get(w, 0)
        if c == 0 and w in word_to_primary:
            c = counts.get(word_to_primary[w], 0)
        
        cost = -math.log10(c/total_tokens) if c > 0 else default_cost
        word_costs[w] = cost
        max_bytes = max(max_bytes, len(w.encode('utf-8')))

    # 3. Build Hash Table
    num_entries = len(words)
    table_size = next_power_of_two(int(num_entries / 0.70))
    
    string_pool = bytearray(b'\x00')
    word_offsets = {}
    for w in sorted(list(words)):
        word_offsets[w] = len(string_pool)
        string_pool.extend(w.encode('utf-8') + b'\x00')

    table = [(0, 0.0)] * table_size
    for w, cost in word_costs.items():
        idx = djb2_hash(w) & (table_size - 1)
        while table[idx][0] != 0:
            idx = (idx + 1) & (table_size - 1)
        table[idx] = (word_offsets[w], cost)

    # 4. Write
    with open(output_kdict, 'wb') as f:
        f.write(b'KDIC')
        f.write(struct.pack('<III', 1, num_entries, table_size))
        f.write(struct.pack('<ff', default_cost, unknown_cost))
        f.write(struct.pack('<II', max_bytes, 0))
        for offset, cost in table:
            f.write(struct.pack('<If', offset, cost))
        f.write(string_pool)
    
    print(f"  > Compiled KDict to {output_kdict} ({os.path.getsize(output_kdict)/1024:.2f} KB)")

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Consolidated Data Pipeline for Khmer Segmenter")
    parser.add_argument("--corpus", nargs="+", default=["dataset/khmer_wiki_corpus.txt", "dataset/khmer_folktales_extracted.txt"], help="Input corpus paths")
    parser.add_argument("--dict", default="khmer_segmenter/dictionary_data/khmer_dictionary_words.txt", help="Input dictionary text file")
    parser.add_argument("--output-json", default="khmer_segmenter/dictionary_data/khmer_word_frequencies.json", help="Output frequency JSON path")
    parser.add_argument("--output-bin", default="port/common/khmer_frequencies.bin", help="Output frequency binary (KLIB) path")
    parser.add_argument("--output-kdict", default="port/common/khmer_dictionary.kdict", help="Output dictionary binary (KDIC) path")
    parser.add_argument("--limit", type=int, help="Limit lines processed for testing")
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations for frequency generation")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary normalized corpus file")
    
    args = parser.parse_args()
    
    temp_norm_path = "temp/corpus_normalized.tmp.txt"
    
    try:
        # Step 1: Normalize
        step_normalize_corpus(args.corpus, temp_norm_path)
        
        # Step 2: Frequencies (Iterative)
        step_generate_frequencies_iterative(temp_norm_path, args.dict, args.output_json, args.limit, args.iterations)
        
        # Step 3: Legacy Binary Frequencies
        step_export_binary_frequencies(args.output_json, args.output_bin)
        
        # Step 4: KDict Compilation
        step_compile_kdict(args.dict, args.output_json, args.output_kdict)
        
        print("\n[!] Pipeline completed successfully.")
        
    finally:
        if not args.keep_temp and os.path.exists(temp_norm_path):
            print(f"[*] Cleaning up temporary file {temp_norm_path}...")
            os.remove(temp_norm_path)

if __name__ == "__main__":
    main()
