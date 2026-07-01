import os
import json
import argparse
import sys

# Start of Imports
# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from khmer_segmenter import KhmerSegmenter
    from khmer_segmenter.normalization import KhmerNormalizer
except ImportError:
    print("Error: Could not import khmer_segmenter package. Run from project root or ensure package is accessible.")
    sys.exit(1)

def strip_control_chars(text):
    return text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def derive_compound_frequency(word, known_frequencies, segmenter):
    """
    Derive frequency for a compound word.
    Heuristic: Min(frequency of components).
    """
    # Use the segmenter to split the word.
    # Note: The segmenter might NOT split it perfectly if the word itself is new and not in its internal dict.
    # But we want to see if it consists of EXISTING dictionary words.
    # So we should populate segmenter with the OLD dictionary (missing this new word) - which is what it has loaded currently if we didn't add it yet.
    # Wait, if we run this script, we expect 'khmer_dictionary_words.txt' ALREADY has the new word?
    # No, usually we run this AFTER adding the word.
    # If the word is in the segmenter's dictionary, it won't split it (it will match the whole word).
    # We want to force split it.
    
    # Strategy: Remove the word from segmenter's dictionary temporarily if present.
    original_words = segmenter.words.copy()
    if word in segmenter.words:
        segmenter.words.remove(word)
        segmenter.max_word_length = 0 # Re-calc max length? Too expensive. Just assume it's fine.
        # Actually, removing one word shouldn't break max_word_length unless it was the ONLY long word.
        
    segments = segmenter.segment(word)
    
    # Restore
    segmenter.words = original_words
    
    # Check if segments are valid known words
    # If any segment is unknown, we can't derive confident frequency (maybe 0 or default).
    # If all segments are known:
    
    valid_components = True
    component_freqs = []
    
    for seg in segments:
        # Check if segment is in frequencies
        if seg in known_frequencies:
            component_freqs.append(known_frequencies[seg])
        elif seg in segmenter.words:
             # Known word but no frequency (rare)?
             # Assign default floor
             component_freqs.append(5) # Default floor
        else:
            # Unknown component.
            # Maybe it's a number or symbol?
            if segmenter._is_digit(seg) or segmenter._is_separator(seg):
                continue # Ignore non-words for frequency calc
            else:
                valid_components = False
                break
                
    if valid_components and component_freqs:
        # Heuristic: Min frequency of components
        # Rationale: The compound phrase cannot appear more often than its rarest part.
        # (Actually probability theory says P(AB) = P(A|B)P(B). If independent P(A)P(B).
        # But for 'frequency count', if A appears 100 times and B appears 5 times, 'AB' appears at most 5 times.)
        derived_freq = min(component_freqs)
        print(f"    > Derived frequency for '{word}' from components {segments}: {derived_freq}")
        return derived_freq
        
    return None

def main():
    parser = argparse.ArgumentParser(description="Incrementally update frequencies for new dictionary words")
    parser.add_argument("--dict", required=True, help="Path to dictionary text file")
    parser.add_argument("--freq", required=True, help="Path to existing frequency JSON")
    parser.add_argument("--unknown-freq", required=True, help="Path to unknown word frequency JSON")
    parser.add_argument("--output", help="Path to save updated frequency JSON (default: overwrite input)")
    
    args = parser.parse_args()
    
    dict_path = args.dict
    freq_path = args.freq
    unknown_freq_path = args.unknown_freq
    output_path = args.output if args.output else freq_path
    
    print(f"[*] Starting Incremental Update...")
    print(f"  > Dictionary: {dict_path}")
    print(f"  > Frequencies: {freq_path}")
    print(f"  > Unknowns: {unknown_freq_path}")
    
    # 1. Load Data
    current_freqs = load_json(freq_path)
    unknown_freqs = load_json(unknown_freq_path)
    
    # Load Dictionary Words
    dict_words = set()
    with open(dict_path, 'r', encoding='utf-8') as f:
        for line in f:
            w = strip_control_chars(line.strip())
            if w: dict_words.add(w)
            
    print(f"  > Loaded {len(dict_words)} dictionary words.")
    print(f"  > Loaded {len(current_freqs)} existing frequencies.")
    
    # 2. Identify New Words
    # Words in Dict but NOT in Current Frequencies
    new_words = []
    for w in dict_words:
        if w not in current_freqs:
            new_words.append(w)
            
    if not new_words:
        print("[*] No new words found. Frequencies are up to date.")
        return
        
    print(f"[*] Found {len(new_words)} new words to update.")
    
    # Initialize Segmenter for compound derivation
    # We pass the CURRENT dict (which includes the new words)
    # But we rely on 'derive_compound_frequency' to handle the split by temporarily removing the word.
    try:
        segmenter = KhmerSegmenter(dict_path, freq_path)
    except Exception as e:
        print(f"Warning: Could not initialize segmenter: {e}. Compound derivation might fail.")
        segmenter = None

    updated_count = 0
    derived_count = 0
    default_count = 0
    
    for w in new_words:
        freq = 0
        
        # Strategy A: Check Unknown Frequencies
        if w in unknown_freqs:
            # Handle new structure vs old structure compatibility if needed, 
            # but we know we just changed it.
            # New structure: { word: { 'count': N, 'examples': [...] } }
            # Old/Simple structure: { word: N }
            val = unknown_freqs[w]
            if isinstance(val, dict) and 'count' in val:
                freq = val['count']
            else:
                freq = val # Fallback if user uses old format
                
            # print(f"  > Found '{w}' in unknown list. Freq: {freq}")
            updated_count += 1
            
        # Strategy B: Derive Compound Frequency
        elif segmenter:
            # Check if it looks like a compound
            d_freq = derive_compound_frequency(w, current_freqs, segmenter)
            if d_freq is not None:
                freq = d_freq
                derived_count += 1
            else:
                # Default
                freq = 5 # Default floor
                default_count += 1
        else:
            freq = 5
            default_count += 1
            
        current_freqs[w] = freq
        
    print(f"[*] Update Complete.")
    print(f"  > From Unknown List: {updated_count}")
    print(f"  > Derived Compound: {derived_count}")
    print(f"  > Default Floor: {default_count}")
    
    # 3. Save
    save_json(current_freqs, output_path)
    print(f"[*] Saved updated frequencies to {output_path}")

if __name__ == "__main__":
    main()
