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
        self.rules = self._load_and_compile_rules()

    def _load_and_compile_rules(self):
        rule_path = os.path.join(os.path.dirname(__file__), "rules.json")
        try:
            with open(rule_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
                
            # Sort by priority desc
            rules.sort(key=lambda x: x.get("priority", 0), reverse=True)
            
            compiled_rules = []
            for rule in rules:
                # Pre-compile trigger regex
                trigger = rule["trigger"]
                if trigger["type"] == "regex":
                    try:
                        trigger["regex_obj"] = re.compile(trigger["value"])
                    except re.error as e:
                        print(f"Error compiling trigger regex for rule '{rule.get('name')}': {e}")
                        continue
                
                # Check for "value" in trigger for exact match optimization
                # (Nothing needed, just keep the detailed object)
                
                compiled_rules.append(rule)
                
            return compiled_rules
            
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
                # 1. Check Trigger
                trigger = rule["trigger"]
                t_type = trigger["type"]
                match = False
                
                if t_type == "exact_match":
                    if seg == trigger["value"]:
                        match = True
                elif t_type == "regex":
                    if trigger["regex_obj"].match(seg):
                        match = True
                elif t_type == "complexity_check":
                    if trigger["value"] == "is_invalid_single":
                        if self.check_invalid_single(seg):
                            match = True
                            
                if not match:
                    continue

                # 2. Check Conditions
                conditions_met = True
                checks = rule.get("checks", [])
                
                if checks: # Only iterate if there are checks
                    for check in checks:
                        target = check.get("target")
                        target_seg = None
                        
                        # Resolve target
                        if target == "prev":
                            if i > 0: target_seg = segments[i-1]
                        elif target == "next":
                            if i + 1 < len(segments): target_seg = segments[i+1]
                        elif target == "context" or target == "current":
                            target_seg = segments[i]
                        
                        # Check existence
                        # Default exists requirement is True if not specified? 
                        # Logic in original: if check.get("exists") is True...
                        must_exist = check.get("exists", False) 
                        if must_exist and target_seg is None:
                            conditions_met = False
                            break
                        
                        if target_seg is None:
                            # If it doesn't exist and we didn't require it, 
                            # check if we strictly required a VALUE check on a potentially non-existent item?
                            # If "exists" is false (default), and item missing, do we pass?
                            # Original logic: if target_seg is None and not check.get("exists", True): continue
                            # If check value is implicitly required, target MUST exist unless "exists": false explicitly allows missing.
                            # Let's simplify: if target missing, condition is met ONLY IF we didn't require existence/value check.
                            # But usually we check value on target.
                            
                            # Let's stick to strict:
                            # If target is None, we can't check value. 
                            # If "check" or "value" keys are present, we imply we need target.
                            if "check" in check or "value" in check:
                                # We needed to check something on it, but it's gone.
                                conditions_met = False
                                break
                            
                            # If no value check (just existence check which was false?), continue
                            continue
                            
                        # Value checks
                        c_type = check.get("check") 
                        expected = check.get("value")
                        
                        if c_type == "is_separator":
                            if self.is_separator(target_seg) != expected:
                                conditions_met = False
                                break
                        elif c_type == "is_isolated":
                            prev_sep = True
                            if i > 0: prev_sep = self.is_separator(segments[i-1])
                            
                            next_sep = True
                            if i + 1 < len(segments): next_sep = self.is_separator(segments[i+1])
                            
                            is_iso = prev_sep and next_sep
                            if is_iso != expected:
                                conditions_met = False
                                break
                    
                    if not conditions_met:
                        continue
                
                # 3. Apply Action
                action = rule["action"]
                if action == "merge_next":
                    if i + 1 < len(segments):
                        segments[i] = seg + segments[i+1]
                        del segments[i+1]
                        rule_applied = True
                        break # Break rule loop, restart at SAME index 'i' (it has new content)
                elif action == "merge_prev":
                    if i > 0:
                        segments[i-1] = segments[i-1] + seg
                        del segments[i]
                        i -= 1 # Shift back to re-evaluate merged content at i-1
                        rule_applied = True
                        break
                elif action == "keep":
                    i += 1
                    rule_applied = True
                    break # Break rule loop, move to next
            
            if not rule_applied:
                i += 1
        
        return segments
