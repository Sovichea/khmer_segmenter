import sys
import os
import time
import timeit
import concurrent.futures

# Force UTF-8 for output
sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from khmer_segmenter import KhmerSegmenter

try:
    from khmernltk import word_tokenize
    HAS_KHMERNLTK = True
except ImportError:
    print("Warning: khmernltk not installed. Benchmarking only against local segmenter.")
    HAS_KHMERNLTK = False
    def word_tokenize(text): return [] 

def run_concurrently(segment_func, text, iterations, workers):
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(segment_func, text) for _ in range(iterations)]
        concurrent.futures.wait(futures)
    end_time = time.time()
    return end_time - start_time

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def get_memory_mb():
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    else:
        # Fallback (roughly just object size, not full RSS) or 0
        return 0.0

def benchmark_suite():
    # Setup
    print(f"Initial Memory: {get_memory_mb():.2f} MB")
    
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'khmer_segmenter', 'dictionary_data')
    dict_path = os.path.join(data_dir, "khmer_dictionary_words.txt")
    freq_path = os.path.join(data_dir, "khmer_word_frequencies.json")
    
    print("Loading KhmerSegmenter...")
    start_load = time.time()
    mem_before_ours = get_memory_mb()
    seg = KhmerSegmenter(dict_path, freq_path)
    mem_after_ours = get_memory_mb()
    print(f"KhmerSegmenter Load Time: {time.time() - start_load:.4f}s")
    print(f"KhmerSegmenter Memory Added: {mem_after_ours - mem_before_ours:.2f} MB")
    
    # New Sentence provided by user
    text = (
        "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។"
        "លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) "
        "បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល "
        "និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។"
    )
    
    # Check khmernltk loading
    if HAS_KHMERNLTK:
        print("\nLoading khmernltk model...")
        mem_before_nltk = get_memory_mb()
        # Force load by tokenizing once
        word_tokenize("test") 
        mem_after_nltk = get_memory_mb()
        print(f"khmernltk Memory Added: {mem_after_nltk - mem_before_nltk:.2f} MB")

    print(f"\n--- Text to Segment (Length: {len(text)}) ---")
    print(text)
    print("-" * 60)

    # 1. Output Comparison
    print("\n--- 1. Segmentation Output ---")
    res_ours = seg.segment(text)
    print(f"KhmerSegmenter:\n{' | '.join(res_ours)}\n")
    
    if HAS_KHMERNLTK:
        res_nltk = word_tokenize(text)
        print(f"khmernltk:\n{' | '.join(res_nltk)}\n")
    
    # 2. Sequential Speed
    ITERATIONS_SEQ = 1000
    print(f"--- 2. Sequential Speed ({ITERATIONS_SEQ} iterations) ---")
    
    start_mem = get_memory_mb()
    t_ours = timeit.timeit(lambda: seg.segment(text), number=ITERATIONS_SEQ)
    end_mem = get_memory_mb()
    print(f"KhmerSegmenter: {t_ours/ITERATIONS_SEQ*1000:.3f}ms per call (Mem Delta: {end_mem-start_mem:.2f} MB)")
    
    if HAS_KHMERNLTK:
        start_mem = get_memory_mb()
        t_nltk = timeit.timeit(lambda: word_tokenize(text), number=ITERATIONS_SEQ)
        end_mem = get_memory_mb()
        print(f"khmernltk:      {t_nltk/ITERATIONS_SEQ*1000:.3f}ms per call (Mem Delta: {end_mem-start_mem:.2f} MB)")
        print(f"Speedup: {t_nltk/t_ours:.2f}x")

    # 3. Concurrent Speed
    WORKERS = 4
    ITERATIONS_CONC = 5000
    print(f"\n--- 3. Concurrent Speed ({WORKERS} workers, {ITERATIONS_CONC} total calls) ---")
    
    # Ours
    start_mem = get_memory_mb()
    time_ours_conc = run_concurrently(seg.segment, text, ITERATIONS_CONC, WORKERS)
    end_mem = get_memory_mb()
    tps_ours = ITERATIONS_CONC / time_ours_conc
    print(f"KhmerSegmenter: {tps_ours:.2f} calls/sec (Mem Delta during run: {end_mem-start_mem:.2f} MB)")
    
    # NLTK
    if HAS_KHMERNLTK:
        try:
            start_mem = get_memory_mb()
            time_nltk_conc = run_concurrently(word_tokenize, text, ITERATIONS_CONC, WORKERS)
            end_mem = get_memory_mb()
            tps_nltk = ITERATIONS_CONC / time_nltk_conc
            print(f"khmernltk:      {tps_nltk:.2f} calls/sec (Mem Delta during run: {end_mem-start_mem:.2f} MB)")
            print(f"Throughput Advantage: {tps_ours/tps_nltk:.2f}x")
        except Exception as e:
            print(f"khmernltk concurrent failed: {e}")

    # 4. Macro Benchmark (File Throughput)
    print("\n--- 4. Macro Benchmark (File Throughput) ---")
    corpus_path = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'khmer_wiki_corpus.txt')
    
    if os.path.exists(corpus_path):
        with open(corpus_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            # Limit to 50k lines for quick benchmark if too large
            if len(lines) > 50000:
                lines = lines[:50000]
        
        print(f"Loaded {len(lines)} lines from corpus.")
        
        # Define batch processing function
        def process_lines(seg_func, lines):
            for line in lines:
                seg_func(line)
                
        # KhmerSegmenter Macro
        print("Benchmarking KhmerSegmenter (Macro)...")
        start_mem = get_memory_mb()
        start_time = time.time()
        process_lines(seg.segment, lines)
        duration = time.time() - start_time
        end_mem = get_memory_mb()
        
        tps_ours_macro = len(lines) / duration
        print(f"KhmerSegmenter: {tps_ours_macro:.2f} lines/sec (Time: {duration:.2f}s, Mem Delta: {end_mem-start_mem:.2f} MB)")
        
        # khmernltk Macro
        if HAS_KHMERNLTK:
            print("Benchmarking khmernltk (Macro)...")
            start_mem = get_memory_mb()
            start_time = time.time()
            process_lines(word_tokenize, lines)
            duration = time.time() - start_time
            end_mem = get_memory_mb()
            
            tps_nltk_macro = len(lines) / duration
            print(f"khmernltk:      {tps_nltk_macro:.2f} lines/sec (Time: {duration:.2f}s, Mem Delta: {end_mem-start_mem:.2f} MB)")
            print(f"Throughput Advantage: {tps_ours_macro/tps_nltk_macro:.2f}x")
    else:
        print(f"Corpus not found at {corpus_path}. Skipping macro benchmark.")

if __name__ == "__main__":
    benchmark_suite()
