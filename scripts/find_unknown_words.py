import sys
import os
import re
import argparse
from typing import List, Set, Dict, Any
from collections import Counter, defaultdict
import concurrent.futures

# Add parent directory to path to import khmer_segmenter package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from khmer_segmenter import KhmerSegmenter

def is_unknown(word: str, segmenter: KhmerSegmenter, prev_token: str = None, next_token: str = None) -> bool:
    """
    Determines if a segmented token is considered 'unknown'.
    """
    # 1. Check if in dictionary
    if word in segmenter.words:
        return False
        
    # 2. Check if it's a valid single char
    if len(word) == 1:
        if segmenter._is_valid_single_base_char(word):
            return False
        
        # Check context: If surrounded by separators/spaces, consider it valid (isolated char)
        # Check Prev
        is_prev_sep = False
        if prev_token is None: # Start of line
            is_prev_sep = True
        elif not prev_token.strip(): # Whitespace
            is_prev_sep = True
        elif segmenter._is_separator(prev_token):
            is_prev_sep = True
            
        # Check Next
        is_next_sep = False
        if next_token is None: # End of line
            is_next_sep = True
        elif not next_token.strip(): # Whitespace
            is_next_sep = True
        elif segmenter._is_separator(next_token):
            is_next_sep = True
            
        if is_prev_sep and is_next_sep:
            return False

    # 3. Check if digit (simple)
    if segmenter._is_digit(word):
        return False
        
    # Check if complex number (digits with punctuation like 1.5, 1,000, 1 000)
    # Allows Arabic and Khmer digits, mixed with . , or whitespace
    if re.match(r'^[\d\u17E0-\u17E9]+([.,\s]+[\d\u17E0-\u17E9]+)*$', word):
        return False
        
    # 4. Check if separator/punctuation
    if segmenter._is_separator(word):
        return False

    # 5. Check if it's just whitespace or empty
    if not word.strip():
        return False

    # 6. Ignore Latin words (English, etc.)
    for char in word:
        code = ord(char)
        if (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
            return False
            
    # 7. Ignore pure numbers (Arabic or Khmer digits mixed)
    # _is_digit might already cover this, but let's be safe for mixed "123"
    # Actually _is_digit handles recursion for strings.
    
    # 8. Ignore Symbols/Signs that are not valid Khmer words
    has_khmer = False
    for char in word:
        if segmenter._is_khmer_char(char):
            has_khmer = True
            break
            
    if not has_khmer:
        return False

    return True

def process_segmented_file(input_file: str, segmenter: KhmerSegmenter) -> Dict[str, Dict[str, Any]]:
    # Dictionary to store count and contexts for each unknown word
    # Structure: { word: { 'count': int, 'contexts': List[str] } }
    unknown_stats = defaultdict(lambda: {'count': 0, 'contexts': []})
    
    print(f"Processing segmented results from {input_file}...")
    
    line_count = 0
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith("Segmented: "):
                continue
            
            # Extract content after "Segmented: "
            content = line[len("Segmented: "):].strip()
            if not content:
                continue
                
            # Split by " | "
            words = content.split(" | ")
            
            for i, w in enumerate(words):
                prev_token = words[i-1] if i > 0 else None
                next_token = words[i+1] if i + 1 < len(words) else None
                
                if is_unknown(w, segmenter, prev_token, next_token):
                    stats = unknown_stats[w]
                    stats['count'] += 1
                    
                    # Store up to 10 context examples
                    if len(stats['contexts']) < 10:
                        # Extract context: 2 before, 2 after
                        start = max(0, i - 2)
                        end = min(len(words), i + 3) # i+3 because exclusive upper bound
                        
                        context_tokens = words[start:end]
                        # Mark the unknown word with brackets for visibility
                        formatted_tokens = []
                        for idx, token in enumerate(context_tokens):
                            actual_index_in_words = start + idx
                            if actual_index_in_words == i:
                                formatted_tokens.append(f"[{token}]")
                            else:
                                formatted_tokens.append(token)
                        
                        context_str = " | ".join(formatted_tokens)
                        stats['contexts'].append(context_str)
            
            line_count += 1
            if line_count % 1000 == 0:
                print(f"  Processed {line_count} segmented lines...", end='\r')
                
    print(f"\n  Finished {input_file}.")
    return unknown_stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find unknown words in segmented output")
    parser.add_argument("--input", "-i", required=True, help="Input segmentation results file")
    parser.add_argument("--output", "-o", default="unknown_words_from_results.txt", help="Output file path")
    args = parser.parse_args()
    
    # Setup paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    default_data_dir = os.path.join(project_root, 'data')
    
    dict_path = os.path.join(default_data_dir, "khmer_dictionary_words.txt")
    freq_path = os.path.join(default_data_dir, "khmer_word_frequencies.json")

    print(f"Loading segmenter resources from {default_data_dir}...")
    segmenter = KhmerSegmenter(dict_path, freq_path)
    
    input_path = args.input
    if not os.path.exists(input_path):
        # Try relative to data dir
        temp_path = os.path.join(default_data_dir, input_path)
        if os.path.exists(temp_path):
            input_path = temp_path
        else:
            print(f"Error: Input file found at {input_path}")
            sys.exit(1)
            
    total_unknown_stats = process_segmented_file(input_path, segmenter)

    print(f"Total unique unknown words found: {len(total_unknown_stats)}")
    
    # Output path
    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(default_data_dir, output_path)

    print(f"Writing results to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        # Sort by frequency desc
        # item is (word, dict)
        sorted_unknowns = sorted(total_unknown_stats.items(), key=lambda item: item[1]['count'], reverse=True)
        
        for word, stats in sorted_unknowns:
            f.write(f"Unknown Word: {word}\t(Count: {stats['count']})\n")
            for ctx in stats['contexts']:
                f.write(f"    ... | {ctx} | ...\n")
            f.write("\n" + "-"*40 + "\n")
            
    print("Done.")
