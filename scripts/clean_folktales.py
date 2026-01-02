import os
import re

def clean_folktales(input_path, output_path):
    print(f"Cleaning {input_path}...")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    cleaned_stories = []
    current_story_lines = []
    
    # Keywords/Regex for metadata lines to remove
    # 1. File markers: --- File: ...
    # 2. Bibliographic info: contains "ទំព័រ" (Page), "ឆ្នាំ" (Year), "លេខ" (No.), "បណ្ណាល័យ" (Library)
    # 3. Collection headers: "ប្រជុំ​រឿង​ព្រេង​ខ្មែរ"
    
    metadata_indicators = [
        "--- File:",
        "ទស្សនាវដ្ដី",
        "បណ្ណាល័យ",
        "ប្រជុំ​រឿង​ព្រេង​ខ្មែរ",
        "អ្នក​រៀបរៀង",
        "ច្បាប់​សរសេរ​ដៃ"
    ]
    
    # Also lines that are mostly just "1- ... page ..."
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line marks start of new file/story
        if line.startswith("--- File:"):
            # If we have accumulated lines for a previous story, add them
            if current_story_lines:
                cleaned_stories.append("\n".join(current_story_lines))
                current_story_lines = []
            continue # Skip the file marker line itself
            
        # Check for other metadata
        is_metadata = False
        for indicator in metadata_indicators:
            if indicator in line:
                is_metadata = True
                break
        
        if is_metadata:
            continue
            
        # Special check for volume/page lines that might miss indicators but look like "Book 1 Page 1-3"
        # Identifying lines that are PURELY source info vs Title lines
        # But based on inspection, most source lines have "ទំព័រ" (Page).
        
        current_story_lines.append(line)
        
    # Append the last story
    if current_story_lines:
        cleaned_stories.append("\n".join(current_story_lines))
        
    # Write output
    # Separate stories with TWO newlines as requested ("separate each story with newlines")
    # Using \n\n\n for clear visual separation
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(cleaned_stories))
        
    print(f"Cleaned {len(cleaned_stories)} stories.")
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    data_dir = os.path.join(project_root, 'data')
    
    input_file = os.path.join(data_dir, "khmer_folktales_extracted.txt")
    output_file = os.path.join(data_dir, "khmer_folktales_cleaned.txt")
    
    clean_folktales(input_file, output_file)
