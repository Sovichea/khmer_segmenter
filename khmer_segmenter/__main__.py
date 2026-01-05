import argparse
import sys
import os
import time
import concurrent.futures

# Try to import psutil for memory tracking
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .viterbi import KhmerSegmenter

def get_memory_mb():
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    return 0.0

def run_concurrently(segment_func, lines, workers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # Map returns an iterator, converting to list forces execution
        list(executor.map(segment_func, lines))

def main():
    parser = argparse.ArgumentParser(description="Khmer Segmenter CLI")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark mode")
    parser.add_argument("--input", nargs="+", help="Input file(s)")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of lines")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads for concurrent benchmark")
    parser.add_argument("--no-norm", action="store_true", help="Disable normalization")
    
    args = parser.parse_args()
    
    # Initialize Segmenter
    # Resolve default paths relative to the package location
    # If run as 'python -m khmer_segmenter', __file__ is inside the package.
    # We assume 'data/' is at the root of the repo, i.e., sibling to 'khmer_segmenter/' directory.
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    default_data_dir = os.path.join(project_root, 'data')
    
    dict_path = os.path.join(default_data_dir, "khmer_dictionary_words.txt")
    freq_path = os.path.join(default_data_dir, "khmer_word_frequencies.json")
    
    if not os.path.exists(dict_path):
        # Fallback to current directory or other typical locations
        if os.path.exists("data/khmer_dictionary_words.txt"):
            dict_path = "data/khmer_dictionary_words.txt"
            freq_path = "data/khmer_word_frequencies.json"
        elif os.path.exists("khmer_dictionary_words.txt"):
            dict_path = "khmer_dictionary_words.txt"
            freq_path = "khmer_word_frequencies.json"
    
    try:
        seg = KhmerSegmenter(dict_path, freq_path)
    except FileNotFoundError:
        print(f"Error: Could not find dictionary at {dict_path}")
        sys.exit(1)
    
    if args.benchmark and args.input:
        lines = []
        limit = args.limit
        total_bytes = 0
        
        print(f"Reading input files...")
        for filepath in args.input:
            if limit == 0: break
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if limit == 0: break
                        line = line.strip()
                        if not line: continue
                        
                        lines.append(line)
                        total_bytes += len(line.encode('utf-8'))
                        if limit > 0: limit -= 1
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                
        count = len(lines)
        total_mb = total_bytes / (1024 * 1024)
        print(f"\n--- Input Benchmark ({count} lines, {total_mb:.2f} MB) ---")
        print(f"Initial Memory: {get_memory_mb():.2f} MB")
        
        # 1. Sequential
        print("[1 Thread] Processing...", end="", flush=True)
        start_time = time.time()
        start_mem = get_memory_mb()
        
        for line in lines:
            seg.segment(line)
            
        end_time = time.time()
        end_mem = get_memory_mb()
        dur_seq = end_time - start_time
        if dur_seq < 0.001: dur_seq = 0.001
        
        print(f" Done in {dur_seq:.3f}s")
        print(f"Throughput: {count / dur_seq:.2f} lines/sec ({total_mb / dur_seq:.2f} MB/s)")
        print(f"Mem Delta: {end_mem - start_mem:.2f} MB")
        
        # 2. Concurrent
        if args.threads > 1:
            print(f"\n[{args.threads} Threads] Processing...", end="", flush=True)
            start_time = time.time()
            start_mem = get_memory_mb()
            
            run_concurrently(seg.segment, lines, args.threads)
            
            end_time = time.time()
            end_mem = get_memory_mb()
            dur_conc = end_time - start_time
            if dur_conc < 0.001: dur_conc = 0.001
            
            print(f" Done in {dur_conc:.3f}s")
            print(f"Throughput: {count / dur_conc:.2f} lines/sec ({total_mb / dur_conc:.2f} MB/s)")
            print(f"Mem Delta: {end_mem - start_mem:.2f} MB")
            print(f"Speedup: {dur_seq / dur_conc:.2f}x")
            
    elif args.input:
        # Normal processing
        limit = args.limit
        for filepath in args.input:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if limit == 0: break
                    line = line.strip()
                    if not line: continue
                    
                    res = seg.segment(line)
                    print(f"Original:  {line}")
                    print(f"Segmented: {' | '.join(res)}")
                    print("-" * 40)
                    
                    if limit > 0: limit -= 1
    else:
        print("Usage: python -m khmer_segmenter --benchmark --input <file> [options]")

if __name__ == "__main__":
    main()
