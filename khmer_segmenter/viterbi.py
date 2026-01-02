import os
import math
import json

class KhmerSegmenter:
    def __init__(self, dictionary_path, frequency_path="khmer_word_frequencies.json"):
        """
        Initialize the segmenter by loading the dictionary and word frequencies.
        """
        self.words = set()
        self.max_word_length = 0
        # Valid single-character words (Consonants and Independent Vowels)
        self.valid_single_words = set([
            'ក', 'ខ', 'គ', 'ង', 'ច', 'ឆ', 'ញ', 'ដ', 'ត', 'ទ', 'ព', 'រ', 'ល', 'ស', 'ឡ', # Consonants
            'ឬ', 'ឮ', 'ឪ', 'ឯ', 'ឱ', 'ឦ', 'ឧ', 'ឳ' # Independent Vowels
        ])
        
        # Word Costs
        self.word_costs = {}
        self.default_cost = 10.0 # High cost for dictionary words without frequency
        self.unknown_cost = 20.0 # Very high cost for unknown chunks
        
        self._load_dictionary(dictionary_path)
        self._load_frequencies(frequency_path)

    def _load_dictionary(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Dictionary not found at {path}")
            
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    # Filter out single-character words that are NOT valid single consonants
                    if len(word) == 1 and word not in self.valid_single_words:
                        continue
                        
                    self.words.add(word)
                    if len(word) > self.max_word_length:
                        self.max_word_length = len(word)
        # Filter out compound words containing "ឬ" (or) to force splitting
        # e.g. "ឬហៅ" -> remove if "ហៅ" is invalid? No, if "ហៅ" IS valid.
        # "មែនឬទេ" -> remove if "មែន" and "ទេ" are valid.
        words_to_remove = set()
        for word in self.words:
            if "ឬ" in word and len(word) > 1:
                # Case 1: Starts with ឬ (e.g. ឬហៅ)
                if word.startswith("ឬ"):
                    suffix = word[1:]
                    if suffix in self.words:
                        words_to_remove.add(word)
                # Case 2: Ends with ឬ (e.g. មកឬ)
                elif word.endswith("ឬ"):
                    prefix = word[:-1]
                    if prefix in self.words:
                        words_to_remove.add(word)
                # Case 3: Middle (e.g. មែនឬទេ)
                else:
                    parts = word.split("ឬ")
                    # If all parts are valid words (or empty strings from consecutive ORs), remove it
                    if all((p in self.words or p == "") for p in parts):
                         words_to_remove.add(word)
            
            # Filter out words starting with Coeng (\u17D2) - these are invalid start of words
            if word.startswith('\u17D2'):
                words_to_remove.add(word)

        # Manually exclude specific fragments that cause over-segmentation
        words_to_remove.add('ត្តិ')

        if words_to_remove:
            print(f"Removing {len(words_to_remove)} invalid words (compound ORs, start-with-Coeng) to enforce splitting.")
            self.words -= words_to_remove

        # Re-calculate max_word_length after removal
        self.max_word_length = 0
        for word in self.words:
             if len(word) > self.max_word_length:
                 self.max_word_length = len(word)
                 
        print(f"Loaded {len(self.words)} words. Max length: {self.max_word_length}")

    def _load_frequencies(self, path):
        if not os.path.exists(path):
            print(f"Frequency file not found at {path}. Using default costs.")
            return

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # We will apply a minimum frequency floor to all words.
        # This treats "unseen dictionary words" and "rare corpus words" equally.
        min_freq_floor = 5.0
        
        # Calculate total tokens with the floor applied (approximation is fine, 
        # but to be strict we should sum the effective counts)
        # Note: self.words might contain words not in data. The total token count 
        # should conceptually include the "unseen but assumed 5" counts, but 
        # usually simpler smoothing just sums observed tokens + smoothing factor.
        # Let's simple sum the observed counts for the denominator, 
        # or better: sum the *effective* counts.
        
        effective_counts = {}
        total_tokens = 0
        
        for word, count in data.items():
            eff = max(count, min_freq_floor)
            effective_counts[word] = eff
            total_tokens += eff
            
        if total_tokens > 0:
            min_prob = min_freq_floor / total_tokens
            self.default_cost = -math.log10(min_prob)
            self.unknown_cost = self.default_cost + 5.0 

            for word, count in effective_counts.items():
                prob = count / total_tokens
                if prob > 0:
                    self.word_costs[word] = -math.log10(prob)
        
        print(f"Loaded frequencies for {len(self.word_costs)} words.")
        print(f"Default cost: {self.default_cost:.2f} (freq floor={min_freq_floor}), Unknown cost: {self.unknown_cost:.2f}")

    def get_word_cost(self, word):
        if word in self.word_costs:
            return self.word_costs[word]
        if word in self.words:
            return self.default_cost
        return self.unknown_cost



    def _is_khmer_char(self, char):
        code = ord(char)
        return 0x1780 <= code <= 0x17FF or 0x19E0 <= code <= 0x19FF

    def _get_khmer_cluster_length(self, text, start_index):
        """
        Returns the length of the Khmer consonant cluster starting at start_index.
        Cluster = Base Consonant + [Coeng + Subscript Consonant]* + [Vowels/Signs]*
        """
        n = len(text)
        if start_index >= n:
            return 0
            
        i = start_index
        char = text[i]
        code = ord(char)
        
        # 1. Must start with Base Consonant or Independent Vowel
        # Consonants: 0x1780 - 0x17A2
        # Indep Vowels: 0x17A3 - 0x17B3
        if not (0x1780 <= code <= 0x17B3):
            # Not a cluster start (could be symbol, number, or non-khmer)
            # If it's a coeng or vowel at the start, it's invalid/broken, but we treat as length 1
            return 1

        i += 1
        
        while i < n:
            char = text[i]
            code = ord(char)
            
            # Check for Coeng (Subscript)
            if code == 0x17D2: 
                # Next char must be a consonant to form a valid subscript
                if i + 1 < n and (0x1780 <= ord(text[i+1]) <= 0x17A2):
                    i += 2
                    continue
                else:
                    # Trailing coeng or invalid
                    break
            
            # Check for Vowels and Signs (Dependent Vowels, Diacritics)
            # Dependent Vowels: 0x17B6 - 0x17C5
            # Signs: 0x17C6 - 0x17D1, 0x17D3, 0x17DD
            if (0x17B6 <= code <= 0x17D1) or code == 0x17D3 or code == 0x17DD:
                i += 1
                continue
                
            # End of cluster
            break
            
        return i - start_index
    
    def _is_digit(self, text):
        if len(text) != 1:
             # If it's a long string, check if it's ALL digits?
             # For segmentation logic, we usually check single chars or assume number detection handled elsewhere.
             # But for post-processing check "not self._is_digit(s)", we want to know if the segment is a number.
             # So we should return True only if ALL chars are digits.
             return all(self._is_digit(c) for c in text)
             
        char = text[0]
        code = ord(char)
        # ASCII 0-9 (0x30-0x39) or Khmer 0-9 (0x17E0-0x17E9)
        return (0x30 <= code <= 0x39) or (0x17E0 <= code <= 0x17E9)

    def _get_number_length(self, text, start_index):
        """
        Returns length of a number sequence.
        Supports 1,234.56 and 1.234,56 formats.
        """
        n = len(text)
        i = start_index
        
        if not self._is_digit(text[i]):
            return 0
            
        i += 1
        while i < n:
            char = text[i]
            if self._is_digit(char):
                i += 1
                continue
            
            # Check for separators (comma or dot)
            if char in [',', '.']:
                if i + 1 < n and self._is_digit(text[i+1]):
                    i += 2 # Consume separator and next digit
                    continue
                else:
                    break
            else:
                break
                
        return i - start_index
    
    def _is_separator(self, char):
        # Check for standard punctuation and Khmer punctuation
        # Explicitly exclude repetition symbol (ៗ - \u17D7) so it can be 'snapped' to previous word
        try:
            code = ord(char)
            # Khmer Punctuation (excluding ៗ)
            # \u17D4 (។), \u17D5 (៕), \u17D6 (៖)
            if 0x17D4 <= code <= 0x17DA and code != 0x17D7:
                return True
            # ASCII/General punctuation AND SPACE (' ')
            if char in set('!?.,;:"\'()[]{}- «»'):
                return True
            return False
        except:
            return False
    

    def segment(self, text):
        """
        Segment the text using Viterbi Algorithm (Minimize Cost / Maximize Probability).
        """
        # 1. Strip ZWS
        text = text.replace('\u200b', '')
        
        n = len(text)
        if n == 0:
            return []

        # dp[i] stores the best (cost, last_word_start_index) to reach index i
        # We initialize with infinity
        dp = [(float('inf'), -1)] * (n + 1)
        dp[0] = (0.0, -1) 

        for i in range(n):
            if dp[i][0] == float('inf'): continue
            
            # Constraint Check & Fallback
            # If we violate Khmer constraints, we MUST NOT start a normal word/cluster segment.
            # However, to avoid crashing on dirty text (typos), we allow a single-char "repair" step.
            
            force_repair = False
            
            # 1. Previous char was Coeng (\u17D2).
            # This obligates attachment. If we are here, it means we didn't attach.
            # We strictly enforce attachment IF the current char is a valid subscript candidate (Consonant).
            # If current char is NOT a consonant (e.g. space, punctuation), the Coeng matches nothing.
            if i > 0 and text[i-1] == '\u17D2':
                # Check if valid subscript (Consonant)
                if '\u1780' <= text[i] <= '\u17A2':
                    continue # Valid consonant shoud have been attached. Block split.
                else:
                    force_repair = True # Stray Coeng. Force single-char consumption of current char.
            
            # 2. Current char is Dependent Vowel.
            # Must attach to previous. If we start here, it's isolated.
            if '\u17B6' <= text[i] <= '\u17C5':
                force_repair = True

            if force_repair:
                # RECOVERY MODE: Consume 1 character as "Invalid/Unknown" with high penalty
                # This ensures we don't crash on " ា" or "ក្ "
                next_idx = i + 1
                new_cost = dp[i][0] + self.unknown_cost + 50.0 # Huge penalty
                if next_idx <= n:
                    if new_cost < dp[next_idx][0]:
                        dp[next_idx] = (new_cost, i)
                continue # Skip normal processing


            # 1. Number / Digit Grouping
            if self._is_digit(text[i]):
                num_len = self._get_number_length(text, i)
                next_idx = i + num_len
                # Numbers are treated as low cost tokens (e.g., cost 1.0 or similar to frequent word)
                # To maintain consistency with probability model, assign a low cost.
                step_cost = 1.0 
                if dp[i][0] + step_cost < dp[next_idx][0]:
                    dp[next_idx] = (dp[i][0] + step_cost, i)
            
            # 2. Try to match words from the dictionary
            end_limit = min(n, i + self.max_word_length)
            
            for j in range(i + 1, end_limit + 1):
                word = text[i:j]
                if word in self.words:
                    word_cost = self.get_word_cost(word)
                    new_cost = dp[i][0] + word_cost
                    if new_cost < dp[j][0]:
                        dp[j] = (new_cost, i)
            
            # 3. Unknown Cluster/Char Fallback
            if self._is_khmer_char(text[i]):
                cluster_len = self._get_khmer_cluster_length(text, i)
                
                # Default Unknown Cost
                step_cost = self.unknown_cost
                
                # Penalty for Invalid Single Consonants
                if cluster_len == 1:
                    char = text[i]
                    if char not in self.valid_single_words:
                         step_cost += 10.0 # Extra penalty for invalid single char
                
                # NOTE: If the cluster itself forms a word, it is handled in loop #2.
                # This block handles the case where it is NOT a known word (or we want to consider it as unknown)
                # Typically, Loop #2 covers it if it matches. This is fallback.
                # If "word" in loop #2 matches this specific cluster, costs are compared.
                # Usually Dict Word Cost < Unknown Cluster Cost, so Dict wins.
                
            else:
                # Non-Khmer (Symbol, English, etc.)
                cluster_len = 1
                step_cost = self.unknown_cost # Treat as unknown
            
            next_idx = i + cluster_len
            if next_idx <= n:
                 if dp[i][0] + step_cost < dp[next_idx][0]:
                     dp[next_idx] = (dp[i][0] + step_cost, i)

        # Backtrack
        segments = []
        curr = n
        while curr > 0:
            cost, prev = dp[curr]
            if prev == -1: 
                raise ValueError("Could not segment text.")
            segments.append(text[prev:curr])
            curr = prev
            
        raw_segments = segments[::-1]
        
        # Post-processing Pass 1: Snap Invalid Single Consonants to Previous
        # Exclude separators from being snapped
        pass1_segments = []
        for seg in raw_segments:
            # Check if this segment is an invalid independent single char
            is_invalid_single = (len(seg) == 1 
                                 and seg not in self.valid_single_words 
                                 and seg not in self.words 
                                 and not self._is_digit(seg)
                                 and not self._is_separator(seg)) # Don't snap separators
            
            if is_invalid_single and pass1_segments:
                # Check if previous is NOT a separator (though technically we can snap to anything, usually words)
                if not self._is_separator(pass1_segments[-1]):
                    prev = pass1_segments.pop()
                    pass1_segments.append(prev + seg)
                else:
                    pass1_segments.append(seg)
            else:
                pass1_segments.append(seg)
                
        # Post-processing Pass 2: Merge Consecutive Unknowns
        # Separators break the merge chain
        final_segments = []
        unknown_buffer = []
        
        for seg in pass1_segments:
            # Determine if current segment is KNOWN
            is_known = False
            if self._is_digit(seg[0]):
                is_known = True
            elif seg in self.words:
                is_known = True
            elif len(seg) == 1 and seg in self.valid_single_words:
                is_known = True
            elif self._is_separator(seg):
                is_known = True
            
            if is_known:
                if unknown_buffer:
                    final_segments.append("".join(unknown_buffer))
                    unknown_buffer = []
                final_segments.append(seg)
            else:
                unknown_buffer.append(seg)
                
        if unknown_buffer:
            final_segments.append("".join(unknown_buffer))
            
        return final_segments

if __name__ == "__main__":
    import sys
    dict_file = "khmer_dictionary_words.txt"
    freq_file = "khmer_word_frequencies.json"
    
    if len(sys.argv) > 1:
        dict_file = sys.argv[1]
        
    try:
        seg = KhmerSegmenter(dict_file, freq_file)
        # Test
        text = "កងកម្លាំងរក្សាសន្តិសុខ"
        result = seg.segment(text)
        print(f"Input: {text}")
        print(f"Output: {' | '.join(result)}")
        
        text2 = "ខ្ញុំទៅសាលារៀន"
        result2 = seg.segment(text2) # Should segment
        print(f"Input: {text2}")
        print(f"Output: {' | '.join(result2)}")
        
        text3 = "ការអភិវឌ្ឍ"
        result3 = seg.segment(text3)
        print(f"Input: {text3}")
        print(f"Output: {' | '.join(result3)}")

    except FileNotFoundError as e:
        print(e)
