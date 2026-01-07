import sys
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

# Add project root to path
sys.path.append(os.path.abspath('.'))

from khmer_segmenter import KhmerSegmenter

# Global segmenter for worker processes
_global_seg = None

def init_worker():
    global _global_seg
    _global_seg = KhmerSegmenter(
        dictionary_path="data/khmer_dictionary_words.txt", 
        frequency_path="data/khmer_word_frequencies.json"
    )

def segment_line(line):
    if not line.strip():
        return ""
    try:
        return " | ".join(_global_seg.segment(line))
    except:
        return "ERROR"

def main():
    input_path = "data/khmer_wiki_corpus.txt"
    limit = 100000
    threads = 10
    
    print(f"Loading first {limit} lines from {input_path}...")
    lines = []
    with open(input_path, "r", encoding="utf-8") as f:
        for _ in range(limit):
            line = f.readline()
            if not line:
                break
            lines.append(line.strip())
    
    actual_limit = len(lines)
    print(f"Loaded {actual_limit} lines.")

    # Create output dir
    output_dir = os.path.abspath("output")
    os.makedirs(output_dir, exist_ok=True)

    # Save to temp file for C segmenter
    temp_input = os.path.join(output_dir, "temp_wiki_100k.txt")
    with open(temp_input, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    # 1. Run C segmenter
    print(f"\n[C Port] Running with {threads} threads...")
    c_exe = "./port/c/zig-out/win/bin/khmer_segmenter.exe"
    c_output = os.path.join(output_dir, "results_c.txt")
    
    start_c = time.time()
    subprocess.run([
        c_exe, 
        "--input", temp_input, 
        "--output", c_output, 
        "--threads", str(threads)
    ], check=True, stderr=subprocess.PIPE)
    end_c = time.time()
    dur_c = end_c - start_c
    print(f"C Port finished in {dur_c:.2f}s ({actual_limit/dur_c:.2f} lines/sec)")

    # 2. Run Python segmenter (Parallel)
    print(f"\n[Python Baseline] Running with {threads} processes...")
    start_py = time.time()
    with ProcessPoolExecutor(max_workers=threads, initializer=init_worker) as executor:
        results_py = list(executor.map(segment_line, lines))
    end_py = time.time()
    dur_py = end_py - start_py
    print(f"Python Baseline finished in {dur_py:.2f}s ({actual_limit/dur_py:.2f} lines/sec)")

    # 3. Parse C Output
    print("\nComparing results...")
    results_c = []
    with open(c_output, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("Segmented: "):
                results_c.append(line.replace("Segmented: ", "").strip())
    
    # 4. Compare
    matches = 0
    mismatches = []
    
    # Trim results_c if it has extra empty lines or similar
    results_c = results_c[:actual_limit]
    
    for i in range(min(len(results_py), len(results_c))):
        if results_py[i] == results_c[i]:
            matches += 1
        else:
            if len(mismatches) < 5:
                mismatches.append(f"Line {i+1}:\nPY: {results_py[i]}\nC : {results_c[i]}")
    
    match_rate = (matches / actual_limit) * 100
    print(f"\n--- Results ---")
    print(f"Total Lines   : {actual_limit}")
    print(f"Matches       : {matches}")
    print(f"Match Rate    : {match_rate:.2f}%")
    print(f"Speedup Ratio : {dur_py/dur_c:.2f}x")

    if mismatches:
        print("\nFirst 5 Mismatches:")
        for m in mismatches:
            print(m)
            print("-" * 20)

    # Cleanup
    if os.path.exists(temp_input): os.remove(temp_input)
    if os.path.exists(c_output): os.remove(c_output)

if __name__ == "__main__":
    main()
