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
from collections import Counter

# Add project root to path
sys.path.append(os.getcwd())
try:
    from khmer_segmenter.normalization import KhmerNormalizer
    from khmer_segmenter import KhmerSegmenter
except ImportError:
    print("Error: Could not import khmer_segmenter package. Run from project root.")
    sys.exit(1)

try:
    import khmernltk
except ImportError:
    print("Warning: khmernltk not found. Some functionality may be limited.")

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

def step_normalize_corpus(input_paths, output_path):
    print(f"[*] Step 1: Normalizing Corpus...")
    norm = KhmerNormalizer()
    count = 0
    with open(output_path, 'w', encoding='utf-8') as f_out:
        for path in input_paths:
            if not os.path.exists(path): continue
            print(f"  > Processing {path}")
            with open(path, 'r', encoding='utf-8') as f_in:
                for line in f_in:
                    # KhmerNormalizer.normalize already strips ZWS/ZWNJ/ZWJ
                    f_out.write(norm.normalize(line))
                    count += 1
    print(f"  > Normalized {count} lines to {output_path}")

def step_generate_frequencies(corpus_path, dict_path, output_json, limit=None, engine="khmernltk"):
    print(f"[*] Step 2: Generating Frequencies...")
    
    # Load Dict for filtering
    valid_words = set()
    with open(dict_path, "r", encoding="utf-8") as f:
        for line in f:
            w = strip_control_chars(line.strip())
            if w: valid_words.add(w)
            
    word_counts = Counter()
    
    # Setup Segmenter
    internal_seg = None
    if engine == "internal":
        internal_seg = KhmerSegmenter(dict_path, None) # No freq yet
        
    processed = 0
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            if limit and processed >= limit: break
            line = line.strip()
            if not line: continue
            
            if engine == "khmernltk":
                try: tokens = khmernltk.word_tokenize(line)
                except: continue
            else:
                try: tokens = internal_seg.segment(line)
                except: continue
                
            for t in tokens:
                t = strip_control_chars(t)
                if t in valid_words:
                    word_counts[t] += 1
            processed += 1
            if processed % 10000 == 0: print(f"  > Processed {processed} lines...")

    sorted_counts = dict(sorted(word_counts.items(), key=lambda x: x[1], reverse=True))
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(sorted_counts, f, ensure_ascii=False, indent=4)
    print(f"  > Frequencies saved to {output_json}")
    return sorted_counts

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
        print(f"  > Removing {len(words_to_remove)} 'ឬ' compounds for split enforcement.")
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
    parser.add_argument("--corpus", nargs="+", default=["data/khmer_wiki_corpus.txt", "data/khmer_folktales_extracted.txt"], help="Input corpus paths")
    parser.add_argument("--dict", default="data/khmer_dictionary_words.txt", help="Input dictionary text file")
    parser.add_argument("--output-json", default="data/khmer_word_frequencies.json", help="Output frequency JSON path")
    parser.add_argument("--output-bin", default="port/common/khmer_frequencies.bin", help="Output frequency binary (KLIB) path")
    parser.add_argument("--output-kdict", default="port/common/khmer_dictionary.kdict", help="Output dictionary binary (KDIC) path")
    parser.add_argument("--limit", type=int, help="Limit lines processed for testing")
    parser.add_argument("--engine", choices=["khmernltk", "internal"], default="internal", help="Tokenization engine")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary normalized corpus file")
    
    args = parser.parse_args()
    
    temp_norm_path = "data/corpus_normalized.tmp.txt"
    
    try:
        # Step 1: Normalize
        step_normalize_corpus(args.corpus, temp_norm_path)
        
        # Step 2: Frequencies (JSON)
        step_generate_frequencies(temp_norm_path, args.dict, args.output_json, args.limit, args.engine)
        
        # Step 3: Legacy Binary Frequencies
        step_export_binary_frequencies(args.output_json, args.output_bin)
        
        # Step 4: KDict Compilation
        step_compile_kdict(args.dict, args.output_json, args.output_kdict)
        
        # Also copy KDict to root for convenience
        shutil.copy2(args.output_kdict, os.path.join(os.getcwd(), "khmer_dictionary.kdict"))
        
        print("\n[!] Pipeline completed successfully.")
        
    finally:
        if not args.keep_temp and os.path.exists(temp_norm_path):
            print(f"[*] Cleaning up temporary file {temp_norm_path}...")
            os.remove(temp_norm_path)

if __name__ == "__main__":
    main()
