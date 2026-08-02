"""Khmer Unicode normalization."""

class KhmerNormalizer:
    def __init__(self):
        # Khmer Character Ranges
        self.CONSONANTS = set(range(0x1780, 0x17A3)) # Ka .. A
        self.INDEP_VOWELS = set(range(0x17A3, 0x17B4)) # In .. Au
        self.DEP_VOWELS = set(range(0x17B6, 0x17C6)) # Aa .. Au  (Excluding signs)
        self.SIGNS = set(range(0x17C6, 0x17D4)) # Nikahit .. Viriam + Others (17D3)
        self.REGISTERS = {0x17C9, 0x17CA} # Muusikatoan, Triisap (Subset of SIGNS range but distinct behavior)
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
        if code in self.REGISTERS:
            return 'REGISTER'
        if code in self.DEP_VOWELS:
            return 'VOWEL'
        if code in self.SIGNS or code == 0x17DD: # 17DD is Atthacan
            return 'SIGN'
        return 'OTHER'

    def normalize(self, text):
        """
        Normalizes Khmer text by:
        1. Fixing composite vowels (merging split vowels).
        2. Reordering clusters (Base + Subscripts + Registers + Vowels + Signs).
        """
        return self.normalize_with_mapping(text)[0]

    def normalize_with_mapping(self, text):
        """Return normalized text and one original-source range per output character."""
        if not text:
            return "", ()

        prepared = []
        i = 0
        while i < len(text):
            char = text[i]
            if char in {'\u200b', '\u200c', '\u200d'}:
                i += 1
                continue
            if char == '\u17c1' and i + 1 < len(text):
                replacement = {'\u17b8': '\u17be', '\u17b6': '\u17c4'}.get(text[i + 1])
                if replacement is not None:
                    prepared.append((replacement, i, i + 2))
                    i += 2
                    continue
            prepared.append((char, i, i + 1))
            i += 1

        result = []
        current_cluster = []
        i = 0
        n = len(prepared)

        while i < n:
            char, start, end = prepared[i]
            ctype = self._get_char_type(char)

            if ctype == 'BASE':
                if current_cluster:
                    result.extend(self._sort_cluster_units(current_cluster))
                    current_cluster = []
                current_cluster.append((char, start, end))
                i += 1
            elif ctype == 'COENG':
                if i + 1 < n:
                    next_char, _, next_end = prepared[i + 1]
                    next_type = self._get_char_type(next_char)
                    if next_type == 'BASE':
                        current_cluster.append((char + next_char, start, next_end))
                        i += 2
                        continue
                current_cluster.append((char, start, end))
                i += 1
            elif ctype in ['VOWEL', 'SIGN', 'REGISTER']:
                if current_cluster:
                    current_cluster.append((char, start, end))
                else:
                    result.append((char, start, end))
                i += 1
            else:
                if current_cluster:
                    result.extend(self._sort_cluster_units(current_cluster))
                    current_cluster = []
                result.append((char, start, end))
                i += 1

        if current_cluster:
            result.extend(self._sort_cluster_units(current_cluster))

        normalized = "".join(unit[0] for unit in result)
        mapping = tuple(
            (start, end)
            for value, start, end in result
            for _ in value
        )
        return normalized, mapping

    def _sort_cluster_units(self, parts):
        if not parts:
            return []
        base = parts[0]
        modifiers = parts[1:]

        def sort_key(unit):
            item = unit[0]
            if item.startswith('\u17D2'):
                if len(item) == 2:
                    return 2 if ord(item[1]) == self.RO else 1
                return 1.5
            code = ord(item[0])
            if code in self.REGISTERS:
                return 2.5
            if code in self.DEP_VOWELS:
                return 3
            if code in self.SIGNS or code == 0x17DD:
                return 4
            return 5

        return [base, *sorted(modifiers, key=sort_key)]

    def _sort_cluster(self, parts):
        """
        Sorts the parts of a cluster (Base + [modifiers]).
        Order:
        1. Base (First item, usually already first)
        2. Sub-Consonants (Type 1: Non-Ro)
        3. Sub-Consonants (Type 2: Ro \u17D2\u179A)
        4. Registers (Muusikatoan/Triisap)
        5. Dependent Vowels
        6. Signs
        """
        if not parts:
            return ""
        
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
            
            if code in self.REGISTERS:
                return 2.5 # After Subscripts, BEFORE Vowels
                
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

    # Test 4: Register Shifter Reordering
    # User Examples: ម្លេ៉ះ, បុ៉ណ្ណោះ, ហា៊ន, មា៉វ, បូ៊
    
    # ម្លេ៉ះ: Mlo + E + Muusikatoan + Reahmuk -> Mlo + Muusikatoan + E + Reahmuk
    input_mleh = '\u1798\u17D2\u179B\u17C1\u17C9\u17C7' 
    out_mleh = norm.normalize(input_mleh)
    print(f"Test 4.1 (Mleh): {[hex(ord(c)) for c in input_mleh]} -> {[hex(ord(c)) for c in out_mleh]}")
    # Expected: 1798 17D2 179B 17C9 17C1 17C7 (E moves after Muusikatoan)

    # បុ៉ណ្ណោះ: Bo + U + Muusikatoan + Nno ...
    input_ponnoh = '\u1794\u17BB\u17C9\u178E\u17D2\u178E\u17C4\u17C7'
    out_ponnoh = norm.normalize(input_ponnoh)
    print(f"Test 4.2 (Ponnoh): {[hex(ord(c)) for c in input_ponnoh]} -> {[hex(ord(c)) for c in out_ponnoh]}")
    # Expected: 1794 (Bo) + 17C9 (Muu) + 17BB (U) ...

    # ហា៊ន: Ho + Aa + Triisap + No
    input_han = '\u17A0\u17B6\u17CA\u1793'
    out_han = norm.normalize(input_han)
    print(f"Test 4.3 (Han): {[hex(ord(c)) for c in input_han]} -> {[hex(ord(c)) for c in out_han]}")
    # Expected: 17A0 (Ho) + 17CA (Tri) + 17B6 (Aa) + 1793 (No)

    # បូ៊: Bo + Oo + Triisap
    input_bou = '\u1794\u17BC\u17CA'
    out_bou = norm.normalize(input_bou)
    print(f"Test 4.4 (Bou): {[hex(ord(c)) for c in input_bou]} -> {[hex(ord(c)) for c in out_bou]}")
    # Expected: 1794 (Bo) + 17CA (Tri) + 17BC (Oo)
