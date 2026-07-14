import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from khmer_segmenter.viterbi import KhmerSegmenter

def generate_hyphenation_pairs():
    dict_path = 'khmer_segmenter/dictionary_data/khmer_dictionary_official_2022_words.txt'
    freq_path = 'khmer_segmenter/dictionary_data/khmer_word_frequencies.json'
    full_dict_path = 'khmer_segmenter/dictionary_data/khmer_dictionary_words.txt'
    
    seg = KhmerSegmenter(full_dict_path, freq_path)
    
    with open(dict_path, 'r', encoding='utf-8') as f:
        words = [line.strip() for line in f if line.strip()]
        
    output_path = 'khmer_segmenter/dictionary_data/khmer_dictionary_hyphenation_pairs.txt'
    
    print(f"Processing {len(words)} words...")
    start_time = time.time()
    
    count = 0
    with open(output_path, 'w', encoding='utf-8') as f:
        for word in words:
            # Skip short words to prevent weird syllabic/letter splits like សា-លា or កង -> ក-ង
            if len(word) < 6:
                continue
                
            # Temporarily remove word so segmenter is forced to find sub-words
            if word in seg.words:
                seg.words.remove(word)
                
            meta = seg.segment_with_metadata(word, disable_post_processing=True)
            
            # Add back
            seg.words.add(word)
            
            # Check if it was split purely into known dictionary sub-words
            is_valid_split = all(t['known'] or t['type'] in ['number', 'separator'] for t in meta) and len(meta) > 1
            
            if is_valid_split:
                hyphenated = '-'.join([t['text'] for t in meta])
                f.write(f'{word}\t{hyphenated}\n')
                count += 1
                
    print(f"Done! Generated {count} hyphenation pairs in {time.time() - start_time:.2f} seconds.")
    print(f"Output saved to {output_path}")

if __name__ == '__main__':
    generate_hyphenation_pairs()
