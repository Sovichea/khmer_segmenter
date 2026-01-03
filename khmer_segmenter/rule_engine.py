import json
import os
import re

class RuleBasedEngine:
    def __init__(self, check_invalid_single_func, is_separator_func):
        """
        Initialize the rule engine.
        :param check_invalid_single_func: Function(segment) -> bool. Returns True if segment is an invalid single char.
        :param is_separator_func: Function(segment) -> bool. Returns True if segment is a separator.
        """
        self.check_invalid_single = check_invalid_single_func
        self.is_separator = is_separator_func
        self.rules = self._load_rules()

    def _load_rules(self):
        rule_path = os.path.join(os.path.dirname(__file__), "rules.json")
        try:
            with open(rule_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
                # Sort by priority desc
                rules.sort(key=lambda x: x.get("priority", 0), reverse=True)
                return rules
        except Exception as e:
            print(f"Error loading rules: {e}")
            return []

    def apply_rules(self, segments):
        """
        Apply rules to the list of segments.
        Use a while loop because we merge items which changes indices.
        """
        i = 0
        while i < len(segments):
            seg = segments[i]
            rule_applied = False
            
            for rule in self.rules:
                if self._check_trigger(rule["trigger"], seg):
                    # Trigger matched, check conditions
                    if self._check_conditions(rule.get("checks", []), segments, i):
                        # Apply Action
                        action = rule["action"]
                        if action == "merge_next":
                            if i + 1 < len(segments):
                                # Merge current with next
                                merged = seg + segments[i+1]
                                segments[i] = merged
                                del segments[i+1]
                                # Re-evaluate this index since content changed
                                rule_applied = True
                                break
                        elif action == "merge_prev":
                            if i > 0:
                                # Merge current with prev
                                merged = segments[i-1] + seg
                                segments[i-1] = merged
                                del segments[i]
                                # Decrement i to re-evaluate the prev index (now merged)
                                i -= 1 
                                rule_applied = True
                                break
                        elif action == "keep":
                             # Explicitly keep (exception rule). Stop checking other rules.
                             # Move to next segment
                             i += 1
                             rule_applied = True
                             break
            
            if not rule_applied:
                i += 1
        
        return segments

    def _check_trigger(self, trigger, segment):
        t_type = trigger["type"]
        val = trigger["value"]
        
        if t_type == "exact_match":
            return segment == val
        elif t_type == "regex":
            return bool(re.match(val, segment))
        elif t_type == "complexity_check":
            if val == "is_invalid_single":
                return self.check_invalid_single(segment)
        return False

    def _check_conditions(self, checks, segments, index):
        for check in checks:
            target = check.get("target")
            
            target_seg = None
            if target == "prev":
                if index > 0: target_seg = segments[index-1]
            elif target == "next":
                if index + 1 < len(segments): target_seg = segments[index+1]
            elif target == "context" or target == "current":
                target_seg = segments[index]
            
            # Check existence
            if check.get("exists") is True and target_seg is None:
                return False
            
            if target_seg is None and not check.get("exists", True):
                continue # Allowed to not exist?
                
            if target_seg is not None:
                # Value checks
                c_type = check.get("check") # e.g. "is_separator" or "is_isolated"
                expected = check.get("value")
                
                if c_type == "is_separator":
                    if self.is_separator(target_seg) != expected:
                        return False
                elif c_type == "is_isolated":
                    # Isolated means prev is separator/None AND next is separator/None
                    prev_sep = True
                    if index > 0: prev_sep = self.is_separator(segments[index-1])
                    
                    next_sep = True
                    if index + 1 < len(segments): next_sep = self.is_separator(segments[index+1])
                    
                    is_iso = prev_sep and next_sep
                    if is_iso != expected:
                        return False

        return True
