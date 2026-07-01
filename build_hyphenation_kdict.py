import struct
import math
import os

def djb2_hash(s):
    h = 5381
    for char in s.encode('utf-8'):
        h = ((h << 5) + h) + char
        h &= 0xFFFFFFFF
    return h

def next_power_of_two(n):
    if n <= 0: return 1
    return 1 << (n - 1).bit_length()

def build_hyphenation_kdict():
    input_txt = 'khmer_segmenter/dictionary_data/khmer_dictionary_hyphenation_pairs.txt'
    output_bin = 'port/common/khmer_hyphenation.kdict'
    
    # 1. Load pairs
    pairs = {}
    with open(input_txt, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                word, hyphenated = line.strip().split('\t')
                # Optional: convert '-' to Zero Width Space '\u200b' if you want it directly usable by word processors
                # Or keep '-' so your editor can replace it itself. We'll use \u200b for standard behavior.
                pairs[word] = hyphenated.replace('-', '\u200b')
                
    num_entries = len(pairs)
    table_size = next_power_of_two(int(num_entries / 0.70))
    
    print(f"Building Hyphenation Binary Dict:")
    print(f"Entries: {num_entries}, Table Size: {table_size} (Power of 2)")

    # 2. Build String Pool
    string_pool = bytearray(b'\x00')
    word_offsets = {}
    
    # Store all strings (keys and values)
    for word, hyphenated in sorted(pairs.items()):
        word_offsets[word] = {'key_offset': len(string_pool)}
        string_pool.extend(word.encode('utf-8') + b'\x00')
        
        word_offsets[word]['val_offset'] = len(string_pool)
        string_pool.extend(hyphenated.encode('utf-8') + b'\x00')

    # 3. Build Hash Table (Open Addressing, Linear Probing)
    # Format: [key_offset: uint32, val_offset: uint32]
    table = [(0, 0)] * table_size
    
    for word, offsets in word_offsets.items():
        idx = djb2_hash(word) & (table_size - 1)
        # Find empty slot
        while table[idx][0] != 0:
            idx = (idx + 1) & (table_size - 1)
        table[idx] = (offsets['key_offset'], offsets['val_offset'])

    # 4. Write Binary File
    with open(output_bin, 'wb') as f:
        # Header (32 bytes)
        f.write(b'KHYP') # Magic (Khmer Hyphenation)
        f.write(struct.pack('<I', 1)) # Version
        f.write(struct.pack('<I', num_entries))
        f.write(struct.pack('<I', table_size))
        f.write(struct.pack('<IIII', 0, 0, 0, 0)) # Padding
        
        # Table
        for key_off, val_off in table:
            f.write(struct.pack('<II', key_off, val_off))
            
        # String Pool
        f.write(string_pool)
        
    print(f"Successfully generated binary dictionary at {output_bin} ({os.path.getsize(output_bin)/1024:.2f} KB)")

if __name__ == '__main__':
    build_hyphenation_kdict()
