#!/usr/bin/env python3
"""
Generate binary frequency file from JSON for fast C loading.

Binary format:
  [word_count: uint32_t (4 bytes)]
  For each word:
    [word_length: uint16_t (2 bytes)]
    [word_bytes: variable UTF-8]
    [cost: float32 (4 bytes)]
"""

import json
import math
import struct
import os
import sys

def generate_binary_frequencies(json_path, output_path):
    """Convert JSON frequency file to binary format."""
    
    print(f"Loading frequencies from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Apply minimum frequency floor (matching Python implementation)
    min_freq_floor = 5.0
    effective_counts = {}
    total_tokens = 0
    
    for word, count in data.items():
        eff = max(count, min_freq_floor)
        effective_counts[word] = eff
        total_tokens += eff
    
    print(f"Total words: {len(effective_counts)}")
    print(f"Total tokens: {total_tokens}")
    
    # Calculate costs
    word_costs = {}
    for word, count in effective_counts.items():
        prob = count / total_tokens
        if prob > 0:
            cost = -math.log10(prob)
            word_costs[word] = cost
    
    # Calculate default and unknown costs (matching Python logic)
    min_prob = min_freq_floor / total_tokens
    default_cost = -math.log10(min_prob)
    unknown_cost = default_cost + 5.0
    
    print(f"Default cost: {default_cost:.2f}")
    print(f"Unknown cost: {unknown_cost:.2f}")
    
    # Write binary file
    print(f"Writing binary file to {output_path}...")
    with open(output_path, 'wb') as f:
        # Write header: word count
        f.write(struct.pack('<I', len(word_costs)))
        
        # Write each word entry
        for word, cost in sorted(word_costs.items()):  # Sort for deterministic output
            word_bytes = word.encode('utf-8')
            word_len = len(word_bytes)
            
            if word_len > 65535:
                print(f"Warning: Skipping word '{word[:20]}...' (length {word_len} exceeds uint16 max)")
                continue
            
            # Write: [length: uint16][bytes][cost: float32]
            f.write(struct.pack('<H', word_len))
            f.write(word_bytes)
            f.write(struct.pack('<f', cost))
    
    print(f"Binary file written successfully!")
    print(f"File size: {os.path.getsize(output_path) / 1024:.2f} KB")

def main():
    # Default paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    json_path = os.path.join(project_root, 'data', 'khmer_word_frequencies.json')
    output_path = os.path.join(project_root, 'data', 'khmer_frequencies.bin')
    
    # Allow command-line overrides
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    
    if not os.path.exists(json_path):
        print(f"Error: Input file not found: {json_path}")
        sys.exit(1)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    generate_binary_frequencies(json_path, output_path)

if __name__ == '__main__':
    main()
