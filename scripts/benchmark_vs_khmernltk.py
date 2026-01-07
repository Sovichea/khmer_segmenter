import argparse
import sys
import os
import time
import concurrent.futures
import statistics

# Try to import psutil for memory tracking
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from khmer_segmenter import KhmerSegmenter

try:
    from khmernltk import word_tokenize
    HAS_KHMERNLTK = True
except ImportError:
    HAS_KHMERNLTK = False
    print("Warning: khmernltk not installed.")

def get_memory_mb():
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    return 0.0

def run_benchmark_block(func, lines, total_bytes, threads=1):
    print(f"[{threads} Thread{'s' if threads > 1 else ''}] Processing...", end="", flush=True)
    
    start_mem = get_memory_mb()
    start_time = time.time()
    
    if threads > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            # Force evaluation
            list(executor.map(func, lines))
    else:
        for line in lines:
            func(line)
            
    end_time = time.time()
    end_mem = get_memory_mb()
    
    duration = end_time - start_time
    if duration < 0.001: duration = 0.001
    
    count = len(lines)
    throughput_lines = count / duration
    throughput_mb = (total_bytes / (1024 * 1024)) / duration
    mem_delta = end_mem - start_mem
    
    print(f" Done in {duration:.3f}s")
    print(f"Throughput: {throughput_lines:.2f} lines/sec ({throughput_mb:.2f} MB/s)")
    print(f"Mem Delta: {mem_delta:.2f} MB")
    
    return throughput_lines, mem_delta, duration

def main():
    parser = argparse.ArgumentParser(description="Benchmark vs khmernltk")
    parser.add_argument("--input", required=True, help="Input file")
    parser.add_argument("--limit", type=int, default=5000, help="Limit lines")
    parser.add_argument("--threads", type=int, default=10, help="Threads for concurrent test")
    
    args = parser.parse_args()
    
    # 1. Load Data
    print(f"Reading {args.input} (Limit: {args.limit})...")
    lines = []
    total_bytes = 0
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            if args.limit > 0 and len(lines) >= args.limit: break
            line = line.strip()
            if not line: continue
            lines.append(line)
            total_bytes += len(line.encode('utf-8'))
            
    total_mb = total_bytes / (1024 * 1024)
    print(f"Loaded {len(lines)} lines ({total_mb:.2f} MB).")
    
    # Track results for table
    results = {}
    
    # --- KhmerSegmenter ---
    print("\n" + "="*50)
    print("KhmerSegmenter (Python)")
    print("="*50)
    
    initial_mem = get_memory_mb()
    # Resolve paths relative to repo root (scripts/../data)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    dict_path = os.path.join(repo_root, "khmer_segmenter", "dictionary_data", "khmer_dictionary_words.txt")
    freq_path = os.path.join(repo_root, "khmer_segmenter", "dictionary_data", "khmer_word_frequencies.json")
    
    t0 = time.time()
    seg = KhmerSegmenter(dict_path, freq_path)
    load_time = time.time() - t0
    load_mem = get_memory_mb() - initial_mem
    
    print(f"Initial Memory: {initial_mem:.2f} MB")
    print(f"Load Time: {load_time:.3f}s")
    print(f"Memory Added: {load_mem:.2f} MB")
    print(f"\n--- Input Benchmark ({len(lines)} lines, {total_mb:.2f} MB) ---")
    
    seq_tps, seq_mem, seq_dur = run_benchmark_block(seg.segment, lines, total_bytes, 1)
    print("")
    conc_tps, conc_mem, conc_dur = run_benchmark_block(seg.segment, lines, total_bytes, args.threads)
    print(f"Speedup: {seq_dur/conc_dur:.2f}x")
    
    results['KhmerSegmenter'] = {
        'load_time': load_time,
        'load_mem': load_mem,
        'seq_tps': seq_tps,
        'conc_tps': conc_tps,
        'conc_speedup': seq_dur/conc_dur
    }

    # --- khmernltk ---
    if HAS_KHMERNLTK:
        print("\n" + "="*50)
        print("khmernltk (Python)")
        print("="*50)
        
        # Re-check memory before load to isolate impact
        initial_mem_nltk = get_memory_mb()
        
        t0 = time.time()
        word_tokenize("តេស្ត") # Trigger Load
        load_time_nltk = time.time() - t0
        load_mem_nltk = get_memory_mb() - initial_mem_nltk
        
        print(f"Initial Memory: {initial_mem_nltk:.2f} MB")
        print(f"Load Time: {load_time_nltk:.3f}s")
        print(f"Memory Added: {load_mem_nltk:.2f} MB")
        
        print(f"\n--- Input Benchmark ({len(lines)} lines, {total_mb:.2f} MB) ---")
        
        def nltk_wrapper(text): return word_tokenize(text)
        
        seq_tps_n, seq_mem_n, seq_dur_n = run_benchmark_block(nltk_wrapper, lines, total_bytes, 1)
        print("")
        conc_tps_n, conc_mem_n, conc_dur_n = run_benchmark_block(nltk_wrapper, lines, total_bytes, args.threads)
        print(f"Speedup: {seq_dur_n/conc_dur_n:.2f}x")
        
        results['khmernltk'] = {
            'load_time': load_time_nltk,
            'load_mem': load_mem_nltk,
            'seq_tps': seq_tps_n,
            'conc_tps': conc_tps_n,
            'conc_speedup': seq_dur_n/conc_dur_n
        }

    # Summary Table
    print("\n" + "="*60)
    print(f"{'Metric':<20} | {'KhmerSegmenter':<15} | {'khmernltk':<15}")
    print("-" * 60)
    
    ks = results['KhmerSegmenter']
    kn = results.get('khmernltk', {'load_time':0, 'load_mem':0, 'seq_tps':0, 'conc_tps':0, 'conc_speedup':0})
    
    print(f"{'Load Time':<20} | {ks['load_time']:.3f}s{'':<10} | {kn['load_time']:.3f}s")
    print(f"{'Memory Overhead':<20} | {ks['load_mem']:.2f} MB{'':<8} | {kn['load_mem']:.2f} MB")
    print(f"{'Seq Throughput':<20} | {ks['seq_tps']:.1f} lines/s{'':<3} | {kn['seq_tps']:.1f} lines/s")
    print(f"{'Conc Throughput':<20} | {ks['conc_tps']:.1f} lines/s{'':<3} | {kn['conc_tps']:.1f} lines/s")
    print(f"{'Conc Speedup':<20} | {ks['conc_speedup']:.2f}x{'':<11} | {kn['conc_speedup']:.2f}x")
    print("="*60)

if __name__ == "__main__":
    main()
