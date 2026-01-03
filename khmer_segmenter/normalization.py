
import re

class KhmerNormalizer:
    def __init__(self):
        # Khmer Character Ranges
        self.CONSONANTS = set(range(0x1780, 0x17A3)) # Ka .. A
        self.INDEP_VOWELS = set(range(0x17A3, 0x17B4)) # In .. Au
        self.DEP_VOWELS = set(range(0x17B6, 0x17C6)) # Aa .. Au  (Excluding signs)
        self.SIGNS = set(range(0x17C6, 0x17D4)) # Nikahit .. Viriam + Others (17D3)
        self.COENG = 0x17D2
        self.RO = 0x179A
        
        # Composite Vowels Map (Split components -> Combined)
        # e.g. E (17C1) + I (17B8) -> OE (17BE)
        self.composites = {
            ('\u17C1', '\u17B8'): '\u17BE',
            ('\u17C1', '\u17B6'): '\u17C4', # E + AA -> AU
        }

    def _get_char_type(self, char):
        code = ord(char)
        if code in self.CONSONANTS or code in self.INDEP_VOWELS:
            return 'BASE'
        if code == self.COENG:
            return 'COENG'
        if code in self.DEP_VOWELS:
            return 'VOWEL'
        if code in self.SIGNS or code == 0x17DD: # 17DD is Atthacan
            return 'SIGN'
        return 'OTHER'

    def normalize(self, text):
        """
        Normalizes Khmer text by:
        1. Fixing composite vowels (merging split vowels).
        2. Reordering clusters (Base + Subscripts + Vowels + Signs).
        """
        if not text:
            return ""
            
        # Step 1: Fix Composites (Simple string replacement loop)
        # We invoke this before cluster processing to ensure units are correct.
        # Check standard splits
        text = text.replace('\u17C1\u17B8', '\u17BE') # e + i -> oe
        text = text.replace('\u17C1\u17B6', '\u17C4') # e + aa -> au
        
        # Step 2: Cluster processing
        # We need to identify clusters. A cluster starts with a BASE or INDEP_VOWEL.
        # But wait, what if text starts with broken vowels? We treat them as 'OTHER'.
        
        # We can iterate and build clusters.
        result = []
        current_cluster = []
        
        i = 0
        n = len(text)
        
        while i < n:
            char = text[i]
            ctype = self._get_char_type(char)
            
            if ctype == 'BASE':
                # Start of new cluster. Flush previous.
                if current_cluster:
                    result.append(self._sort_cluster(current_cluster))
                    current_cluster = []
                current_cluster.append(char)
                i += 1
            elif ctype == 'COENG':
                # Coeng consumes next char if valid consonant
                if i + 1 < n:
                    next_char = text[i+1]
                    next_type = self._get_char_type(next_char)
                    if next_type == 'BASE': # Consonants are BASE
                        # It is a subscript unit
                        current_cluster.append(char + next_char)
                        i += 2
                        continue
                    else:
                        # Stray Coeng? Or Coeng + Vowel (Invalid but exists)?
                        # Treat as single char
                        current_cluster.append(char)
                        i += 1
                else:
                    # Trailing Coeng
                    current_cluster.append(char)
                    i += 1
            elif ctype in ['VOWEL', 'SIGN']:
                # Append to current cluster if exists, else treat as isolated
                if current_cluster:
                     current_cluster.append(char)
                else:
                     result.append(char) # Isolated vowel/sign
                i += 1
            else:
                # Other (Space, Punc, English). Flush cluster.
                if current_cluster:
                    result.append(self._sort_cluster(current_cluster))
                    current_cluster = []
                result.append(char)
                i += 1
                
        if current_cluster:
            result.append(self._sort_cluster(current_cluster))
            
        return "".join(result)

    def _sort_cluster(self, parts):
        """
        Sorts the parts of a cluster (Base + [modifiers]).
        Order:
        1. Base (First item, usually already first)
        2. Sub-Consonants (Type 1: Non-Ro)
        3. Sub-Consonants (Type 2: Ro \u17D2\u179A)
        4. Dependent Vowels
        5. Signs
        """
        if not parts: return ""
        
        base = parts[0]
        modifiers = parts[1:]
        
        def sort_key(item):
            # Assign priority
            if item.startswith('\u17D2'): # Subscript
                if len(item) == 2:
                    sub_con = item[1]
                    if ord(sub_con) == self.RO:
                         return 2 # Ro Subscript
                    return 1 # Non-Ro Subscript
                return 1.5 # Stray Coeng?
            
            # Use char code for Vowels/Signs to keep stable 'standard' order if multiple?
            # Or define specific category priority.
            code = ord(item[0])
            if code in self.DEP_VOWELS:
                return 3
            if code in self.SIGNS or code == 0x17DD:
                return 4
                
            return 5 # Other/Unknown
            
        # Stable sort modifiers
        sorted_modifiers = sorted(modifiers, key=sort_key)
        
        return base + "".join(sorted_modifiers)

if __name__ == "__main__":
    # Quick Test
    norm = KhmerNormalizer()
    
    # Test 1: Wrong Order Subscript (Ro before Ta)
    # Correct: Ta (\u17D2\u178F) then Ro (\u17D2\u179A)
    # Input: Base + Ro + Ta
    # \u1780 (Ka) + \u17D2\u179A (Coeng Ro) + \u17D2\u178F (Coeng Ta)
    input1 = chr(0x1780) + chr(0x17D2) + chr(0x179A) + chr(0x17D2) + chr(0x178F)
    out1 = norm.normalize(input1)
    print(f"Test 1 (Ro-Ta swap): {[hex(ord(c)) for c in input1]} -> {[hex(ord(c)) for c in out1]}")
    
    # Test 2: Vowel before Subscript
    # Input: Ka + Aa (\u17B6) + Coeng Ta
    input2 = chr(0x1780) + chr(0x17B6) + chr(0x17D2) + chr(0x178F)
    out2 = norm.normalize(input2)
    print(f"Test 2 (Vowel-Sub swap): {[hex(ord(c)) for c in input2]} -> {[hex(ord(c)) for c in out2]}")
    
    # Test 3: Composite Fix (E + I -> OE)
    # Input: Ka + E + I
    input3 = chr(0x1780) + chr(0x17C1) + chr(0x17B8)
    out3 = norm.normalize(input3)
    print(f"Test 3 (Composite): {[hex(ord(c)) for c in input3]} -> {[hex(ord(c)) for c in out3]}")
