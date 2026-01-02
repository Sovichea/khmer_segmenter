import sys
import os
import re
import json
import khmernltk
from collections import Counter
from tqdm import tqdm
import argparse

# Add parent directory to path to import khmer_segmenter package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from khmer_segmenter import KhmerSegmenter

def load_dictionary(dict_path):
    """Loads dictionary words into a set for fast lookup."""
    with open(dict_path, "r", encoding="utf-8") as f:
        # Read words, strip whitespace, and create a set
        words = set(line.strip() for line in f if line.strip())
    return words

def process_corpus(corpus_paths, dict_words_path, output_path, limit=None, engine="khmernltk"):
    """
    Reads corpus, tokenizes, counts words found in dictionary.
    """
    # Load dictionary of valid words
    print(f"Loading dictionary from {dict_words_path}...")
    valid_words = load_dictionary(dict_words_path)
    print(f"Loaded {len(valid_words)} words from dictionary.")
    
    # Initialize internal segmenter if selected
    internal_segmenter = None
    if engine == "internal":
        print("Initializing internal KhmerSegmenter...")
        freq_path = os.path.join(os.path.dirname(dict_words_path), "khmer_word_frequencies.json")
        internal_segmenter = KhmerSegmenter(dict_words_path, freq_path) 

    word_counts = Counter()
    
    total_lines = 0
    # Pre-count lines for progress bar
    for path in corpus_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                total_lines += sum(1 for _ in f)
    
    if limit:
        total_lines = min(total_lines, limit)

    processed_lines = 0
    with tqdm(total=total_lines, desc="Processing Corpus") as pbar:
        for corpus_path in corpus_paths:
            if not os.path.exists(corpus_path):
                print(f"Warning: Corpus file not found: {corpus_path}")
                continue
                
            with open(corpus_path, "r", encoding="utf-8") as f:
                for line in f:
                    if limit and processed_lines >= limit:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue

                    if engine == "khmernltk":
                        # Use khmernltk for tokenization
                        try:
                            # word_tokenize returns a list of strings
                            tokens = khmernltk.word_tokenize(line)
                        except Exception as e:
                            # Skip lines that cause errors (though khmernltk is usually robust)
                            continue
                    elif engine == "internal":
                        tokens = internal_segmenter.segment(line)
                    else:
                        raise ValueError(f"Unknown engine: {engine}")

                    # Filter tokens: must be in our dictionary
                    for token in tokens:
                        if token in valid_words:
                            word_counts[token] += 1
                    
                    processed_lines += 1
                    pbar.update(1)
            
            if limit and processed_lines >= limit:
                break

    # Format output as JSON dictionary
    # We want a format like: {"word": frequency, ...}
    
    # Sort by frequency descending for readability (optional)
    sorted_words = dict(sorted(word_counts.items(), key=lambda item: item[1], reverse=True))

    print(f"Saving frequencies to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_words, f, ensure_ascii=False, indent=4)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Khmer word frequencies from corpus.")
    
    # default paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    default_data_dir = os.path.join(project_root, 'data')

    parser.add_argument("--corpus", nargs="+", default=[
        os.path.join(default_data_dir, "khmer_wiki_corpus.txt"), 
        os.path.join(default_data_dir, "khmer_folktales_extracted.txt")
    ], help="Path(s) to corpus text file(s)")
    
    parser.add_argument("--dict", default=os.path.join(default_data_dir, "khmer_dictionary_words.txt"), help="Path to dictionary file (line separated)")
    parser.add_argument("--output", default=os.path.join(default_data_dir, "khmer_word_frequencies.json"), help="Output JSON path")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of lines to process (for testing)")
    parser.add_argument("--engine", choices=["khmernltk", "internal"], default="khmernltk", help="Segmentation engine to use (khmernltk or internal)")

    args = parser.parse_args()

    process_corpus(args.corpus, args.dict, args.output, args.limit, args.engine)
