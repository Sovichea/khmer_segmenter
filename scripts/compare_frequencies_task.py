import json
import sys
from pathlib import Path

def compare_frequencies(new_path, backup_path, top_n=5000):
    print(f"Comparing top {top_n} words...")
    
    with open(new_path, 'r', encoding='utf-8') as f:
        new_freq = json.load(f)
    
    with open(backup_path, 'r', encoding='utf-8') as f:
        backup_freq = json.load(f)
        
    print(f"New Total Words: {len(new_freq)}")
    print(f"Backup Total Words: {len(backup_freq)}")
    
    # Get top N keys
    new_top = list(new_freq.keys())[:top_n]
    backup_top = list(backup_freq.keys())[:top_n]
    
    # Intersection
    common = set(new_top) & set(backup_top)
    overlap = len(common) / top_n * 100
    
    print(f"Overlap in Top {top_n}: {len(common)}/{top_n} ({overlap:.2f}%)")
    
    # Show some missing/new
    new_only = set(new_top) - set(backup_top)
    backup_only = set(backup_top) - set(new_top)
    
    print("\nWords in New Top 50 but not in Backup Top 50 (Sample):")
    print(list(new_only)[:20])
    
    print("\nWords in Backup Top 50 but not in New Top 50 (Sample):")
    print(list(backup_only)[:20])
    
    # Correlation of counts for common words
    print("\nChecking count correlation for top 10 common words:")
    for w in list(common)[:10]:
        print(f"  {w}: New={new_freq[w]}, Backup={backup_freq[w]}")

if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parents[1] / "src" / "khmer_segmenter" / "dictionary_data"
    new_path = data_dir / "khmer_word_frequencies.json"
    backup_path = data_dir / "khmer_word_frequencies.backup.json"
    if not new_path.is_file():
        sys.exit(f"frequency file not found: {new_path}")
    if not backup_path.is_file():
        sys.exit(
            f"backup frequency file not found: {backup_path}\n"
            "Save a previous model beside it before comparing."
        )
    compare_frequencies(str(new_path), str(backup_path), 5000)
