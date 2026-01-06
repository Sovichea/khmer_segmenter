import sys
import os
import argparse
from typing import List

# Add parent directory to path to import khmer_segmenter package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from khmer_segmenter import KhmerSegmenter

def create_segmenter():
    # Setup paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    default_data_dir = os.path.join(project_root, 'data')
    
    dict_path = os.path.join(default_data_dir, "khmer_dictionary_words.txt")
    freq_path = os.path.join(default_data_dir, "khmer_word_frequencies.json")

    print(f"Loading segmenter from {dict_path}...")
    return KhmerSegmenter(dict_path, freq_path)

def test_segmentation():
    segmenter = create_segmenter()
    print("Segmenter loaded.")

    test_cases = [
        "សួស្តីពិភពលោក",
        "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា",
        "ការអប់រំគឺសំខាន់ណាស់",
        "សាលារៀនយើង",
        "ញ៉ាំបាយនៅ?",
        "ផ"
    ]

    print("\n--- Running Test Cases ---")
    for text in test_cases:
        words = segmenter.segment(text)
        print(f"Input:  {text}")
        print(f"Output: {' | '.join(words)}")
        print("-" * 20)

def batch_process(corpus_file, limit):
    segmenter = create_segmenter()
    
    output_file = "segmentation_results.txt"
    print(f"Processing {corpus_file} to {output_file}...")
    
    count = 0
    with open(corpus_file, "r", encoding="utf-8") as f_in, open(output_file, "w", encoding="utf-8") as f_out:
        for line in f_in:
            if limit and count >= limit:
                break
            
            line = line.strip()
            if not line:
                continue
                
            words = segmenter.segment(line)
            f_out.write(f"Original:  {line}\n")
            f_out.write(f"Segmented: {' | '.join(words)}\n")
            f_out.write("-" * 40 + "\n")
            count += 1
            if count % 1000 == 0:
                print(f"Processed {count} lines...")

    print(f"Done. Processed {count} lines.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Khmer Viterbi Segmenter")
    parser.add_argument("-s", "--source", help="Optional path to corpus file for batch processing")
    parser.add_argument("-l", "--limit", type=int, default=1000, help="Limit number of lines for batch processing (default 1000)")
    parser.add_argument("-t", "--text", help="Raw text to segment (deprecated favor positional args)")
    parser.add_argument("input_text", nargs="*", help="Raw text to segment")
    
    args = parser.parse_args()
    
    if args.source:
        batch_process(args.source, args.limit)
    else:
        # Prefer positional args, fallback to --text
        text_to_process = " ".join(args.input_text) if args.input_text else args.text

        if text_to_process:
            segmenter = create_segmenter()
            
            # print(f"DEBUG: Input Text Codepoints: {[hex(ord(c)) for c in text_to_process]}")
            
            words = segmenter.segment(text_to_process)
            print(f"Input:  {text_to_process}")
            print(f"Output: {' | '.join(words)}")
        else:
            test_segmentation()
