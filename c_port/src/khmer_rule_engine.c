#define _CRT_SECURE_NO_WARNINGS
#include "khmer_rule_engine.h"
#include "re.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>

// Cross-platform strdup compatibility
#if defined(_WIN32)
    #define STRDUP _strdup
#else
    #define STRDUP strdup
#endif

// --- Segment List Implementation ---

SegmentList* segment_list_create(size_t cap) {
    SegmentList* list = (SegmentList*)malloc(sizeof(SegmentList));
    list->capacity = cap > 0 ? cap : 16;
    list->count = 0;
    list->items = (char**)malloc(sizeof(char*) * list->capacity);
    return list;
}

void segment_list_add(SegmentList* list, const char* str) {
    if (list->count >= list->capacity) {
        list->capacity *= 2;
        list->items = (char**)realloc(list->items, sizeof(char*) * list->capacity);
    }
    list->items[list->count++] = STRDUP(str);
}

void segment_list_free(SegmentList* list) {
    if (list) {
        for (size_t i = 0; i < list->count; i++) {
            free(list->items[i]);
        }
        free(list->items);
        free(list);
    }
}

// --- Rule Engine Definitions ---

typedef enum {
    TRIGGER_EXACT,
    TRIGGER_REGEX,
    TRIGGER_COMPLEXITY
} TriggerType;

typedef enum {
    ACTION_MERGE_NEXT,
    ACTION_MERGE_PREV,
    ACTION_KEEP
} ActionType;

typedef struct {
    char* target; 
    char* check; 
    int expected_bool; 
    int check_exists; 
} RuleCheck;

typedef struct {
    char* name;
    int priority;
    
    TriggerType trigger_type;
    char* trigger_value;
    re_t* trigger_re;
    
    RuleCheck* checks;
    int check_count;
    
    ActionType action;
} Rule;

struct RuleEngine {
    Rule* rules;
    int rule_count;
};

// --- Helpers ---

// Copied from khmer_segmenter.c for consistency (or should be shared in util)
static int utf8_decode_re(const char* str, int* out_codepoint) {
    unsigned char c = (unsigned char)str[0];
    if (c < 0x80) { *out_codepoint = c; return 1; }
    else if ((c & 0xE0) == 0xC0) { 
        if (!str[1]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x1F) << 6) | (str[1] & 0x3F); return 2; 
    }
    else if ((c & 0xF0) == 0xE0) { 
        if (!str[1] || !str[2]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x0F) << 12) | ((str[1] & 0x3F) << 6) | (str[2] & 0x3F); return 3; 
    }
    else if ((c & 0xF8) == 0xF0) { 
        if (!str[1] || !str[2] || !str[3]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x07) << 18) | ((str[1] & 0x3F) << 12) | ((str[2] & 0x3F) << 6) | (str[3] & 0x3F); return 4; 
    }
    *out_codepoint = 0; return 1;
}

static int is_separator(const char* s) {
    int cp;
    utf8_decode_re(s, &cp);
    
    // Check against same rules as khmer_segmenter.c
    if (cp >= 0x17D4 && cp <= 0x17DA) return 1; // Khmer Punct
    if (cp == 0x17DB) return 1; // Khmer Currency
    
    if (cp < 0x80 && (ispunct(cp) || isspace(cp))) return 1; // ASCII
    
    if (cp == 0xAB || cp == 0xBB) return 1; // « »
    if (cp >= 0x2000 && cp <= 0x206F) return 1; // General Punctuation
    if (cp >= 0x20A0 && cp <= 0x20CF) return 1; // Currency Symbols
    
    return 0; 
}

static int is_invalid_single(const char* s) {
    int cp;
    int len = utf8_decode_re(s, &cp);
    if (!cp) return 0;
    
    if (s[len] != 0) return 0; // More than 1 char -> valid cluster/word
    
    // Check if valid base
    if ((cp >= 0x1780 && cp <= 0x17A2) || (cp >= 0x17A3 && cp <= 0x17B3)) return 0; // Valid
    
    // Digits
    if (isdigit(cp) || (cp >= 0x17E0 && cp <= 0x17E9)) return 0;
    
    // Separator
    if (is_separator(s)) return 0;
    
    return 1; // Invalid single
}


// --- Hardcoded Rules Init ---

static void add_rule(RuleEngine* eng, const char* name, int prio, TriggerType ttype, const char* tval, ActionType act) {
    eng->rules = (Rule*)realloc(eng->rules, sizeof(Rule) * (eng->rule_count + 1));
    Rule* r = &eng->rules[eng->rule_count++];
    memset(r, 0, sizeof(Rule));
    r->name = STRDUP(name);
    r->priority = prio;
    r->trigger_type = ttype;
    r->trigger_value = STRDUP(tval);
    r->action = act;
    
    if (ttype == TRIGGER_REGEX) {
        r->trigger_re = re_compile(tval);
        if (!r->trigger_re) printf("Failed to compile regex for rule %s\n", name);
    }
}

static void add_check(RuleEngine* eng, int rule_idx, const char* target, const char* check_type, int expected, int exists) {
    Rule* r = &eng->rules[rule_idx];
    r->checks = (RuleCheck*)realloc(r->checks, sizeof(RuleCheck) * (r->check_count + 1));
    RuleCheck* c = &r->checks[r->check_count++];
    c->target = STRDUP(target);
    c->check = check_type ? STRDUP(check_type) : NULL;
    c->expected_bool = expected;
    c->check_exists = exists;
}

RuleEngine* rule_engine_init(const char* rules_path) {
    (void)rules_path; 
    RuleEngine* eng = (RuleEngine*)calloc(1, sizeof(RuleEngine));
    
    // Rule 0
    add_rule(eng, "Ahsda Exception Keep", 110, TRIGGER_REGEX, "^(ក៏|ដ៏)$", ACTION_KEEP);
    
    // Rule 1
    add_rule(eng, "Prefix OR Merge", 100, TRIGGER_EXACT, "អ", ACTION_MERGE_NEXT);
    add_check(eng, 1, "next", "is_separator", 0, 1);
    
    // Rule 2
    add_rule(eng, "Consonant + Signs Merge Left", 90, TRIGGER_REGEX, "^[\\u1780-\\u17A2][\\u17CB\\u17CE\\u17CF]$", ACTION_MERGE_PREV);
    add_check(eng, 2, "prev", NULL, 0, 1); 
    
    // Rule 3
    add_rule(eng, "Consonant + Samyok Sannya Merge Next", 90, TRIGGER_REGEX, "^[\\u1780-\\u17A2]\\u17D0$", ACTION_MERGE_NEXT);
    add_check(eng, 3, "next", NULL, 0, 1);

    // Rule 4
    add_rule(eng, "Consonant + Robat Merge Prev", 90, TRIGGER_REGEX, "^[\\u1780-\\u17A2]\\u17CC$", ACTION_MERGE_PREV);
    add_check(eng, 4, "prev", NULL, 0, 1);
    
    // Rule 5
    add_rule(eng, "Invalid Single Consonant Cleanup", 10, TRIGGER_COMPLEXITY, "is_invalid_single", ACTION_MERGE_PREV);
    add_check(eng, 5, "context", "is_isolated", 0, 0); 
    add_check(eng, 5, "prev", "is_separator", 0, 1);
    
    return eng;
}

// --- Application Logic ---

static int evaluate_check(RuleEngine* eng, RuleCheck* check, SegmentList* segs, int i) {
    (void)eng; // Suppress unused var warning
    char* target_seg = NULL;
    int target_idx = -1;
    
    if (strcmp(check->target, "prev") == 0) target_idx = i - 1;
    else if (strcmp(check->target, "next") == 0) target_idx = i + 1;
    else if (strcmp(check->target, "context") == 0 || strcmp(check->target, "current") == 0) target_idx = i;
    
    if (target_idx >= 0 && target_idx < (int)segs->count) {
        target_seg = segs->items[target_idx];
    }
    
    if (check->check_exists && !target_seg) return 0;
    if (!target_seg) {
         if (check->check) return 0; 
         return 1;
    }
    
    if (check->check) {
        int val = 0;
        if (strcmp(check->check, "is_separator") == 0) {
            val = is_separator(target_seg);
        } else if (strcmp(check->check, "is_isolated") == 0) {
            int p_sep = 1; 
            if (i > 0) p_sep = is_separator(segs->items[i-1]);
            int n_sep = 1;
            if (i + 1 < (int)segs->count) n_sep = is_separator(segs->items[i+1]);
            val = p_sep && n_sep;
        }
        
        if (val != check->expected_bool) return 0;
    }
    
    return 1;
}

void rule_engine_apply(RuleEngine* eng, SegmentList* segments) {
    if (!eng || !segments) return;
    
    int i = 0;
    while (i < (int)segments->count) {
        char* seg = segments->items[i];
        int rule_applied = 0;
        
        for (int r = 0; r < eng->rule_count; r++) {
            Rule* rule = &eng->rules[r];
            
            // 1. Trigger
            int match = 0;
            if (rule->trigger_type == TRIGGER_EXACT) {
                if (strcmp(seg, rule->trigger_value) == 0) match = 1;
            } else if (rule->trigger_type == TRIGGER_REGEX) {
                if (re_matchp(rule->trigger_re, seg)) match = 1;
            } else if (rule->trigger_type == TRIGGER_COMPLEXITY) {
                if (strcmp(rule->trigger_value, "is_invalid_single") == 0) {
                    if (is_invalid_single(seg)) match = 1;
                }
            }
            
            if (!match) continue;
            
            // 2. Checks
            int conditions_met = 1;
            for (int c = 0; c < rule->check_count; c++) {
                if (!evaluate_check(eng, &rule->checks[c], segments, i)) {
                    conditions_met = 0;
                    break;
                }
            }
            if (!conditions_met) continue;
            
            // 3. Action
            if (rule->action == ACTION_MERGE_NEXT) {
                if (i + 1 < (int)segments->count) {
                    char* next = segments->items[i+1];
                    size_t new_len = strlen(seg) + strlen(next) + 1;
                    char* new_seg = (char*)malloc(new_len);
                    strcpy(new_seg, seg);
                    strcat(new_seg, next);
                    
                    free(segments->items[i]);
                    segments->items[i] = new_seg;
                    
                    free(segments->items[i+1]);
                    for (int k = i + 1; k < (int)segments->count - 1; k++) {
                        segments->items[k] = segments->items[k+1];
                    }
                    segments->count--;
                    
                    rule_applied = 1;
                    break; 
                }
            }
            else if (rule->action == ACTION_MERGE_PREV) {
                 if (i > 0) {
                    char* prev = segments->items[i-1];
                    size_t new_len = strlen(prev) + strlen(seg) + 1;
                    char* new_seg = (char*)malloc(new_len);
                    strcpy(new_seg, prev);
                    strcat(new_seg, seg);
                    
                    free(segments->items[i-1]);
                    segments->items[i-1] = new_seg;
                    
                    free(segments->items[i]);
                    for (int k = i; k < (int)segments->count - 1; k++) {
                        segments->items[k] = segments->items[k+1];
                    }
                    segments->count--;
                    
                    i--; 
                    rule_applied = 1;
                    break;
                 }
            }
            else if (rule->action == ACTION_KEEP) {
                 rule_applied = 1; 
                 i++;
                 break; 
            }
        }
        
        if (!rule_applied) i++;
    }
}

void rule_engine_free(RuleEngine* eng) {
    if (eng) {
        for (int i=0; i<eng->rule_count; i++) {
            free(eng->rules[i].name);
            free(eng->rules[i].trigger_value);
            if(eng->rules[i].trigger_re) re_free(eng->rules[i].trigger_re);
            for(int c=0; c<eng->rules[i].check_count; c++) {
                free(eng->rules[i].checks[c].target);
                if(eng->rules[i].checks[c].check) free(eng->rules[i].checks[c].check);
            }
            free(eng->rules[i].checks);
        }
        free(eng->rules);
        free(eng);
    }
}
