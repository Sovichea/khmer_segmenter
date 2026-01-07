#define _CRT_SECURE_NO_WARNINGS
#include "khmer_rule_engine.h"
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

// --- Memory Arena Implementation ---

#define ARENA_ALIGNMENT 8
#define ALIGN_UP(n) (((n) + ARENA_ALIGNMENT - 1) & ~(ARENA_ALIGNMENT - 1))

void arena_init_static(MemArena* arena, void* buffer, size_t size) {
    if (!arena) return;
    arena->buffer = (unsigned char*)buffer;
    arena->size = size;
    arena->used = 0;
    arena->next = NULL;
    arena->flags = 3; // Static buf + Static struct
}

MemArena* arena_create(size_t initial_size) {
    if (initial_size < 4096) initial_size = 4096;
    MemArena* arena = (MemArena*)malloc(sizeof(MemArena));
    if (!arena) return NULL;
    arena->size = initial_size;
    arena->used = 0;
    arena->buffer = (unsigned char*)malloc(initial_size);
    arena->next = NULL;
    arena->flags = 0;
    return arena;
}

void* arena_alloc(MemArena* arena, size_t size) {
    if (!arena) return malloc(size); // Fallback
    
    size_t aligned_size = ALIGN_UP(size);
    
    // Check if fits in current
    if (arena->used + aligned_size <= arena->size) {
        void* ptr = arena->buffer + arena->used;
        arena->used += aligned_size;
        return ptr;
    }
    
    // Check next blocks 
    MemArena* curr = arena;
    while (curr->next) {
        curr = curr->next;
        if (curr->used + aligned_size <= curr->size) {
            void* ptr = curr->buffer + curr->used;
            curr->used += aligned_size;
            return ptr;
        }
    }
    
    // Create new block
    size_t new_size = arena->size * 2; 
    if (new_size < aligned_size) new_size = aligned_size + 4096;
    
    // Allocated blocks are always Heap Dynamic (flags=0)
    MemArena* new_block = (MemArena*)malloc(sizeof(MemArena));
    if (!new_block) return NULL;
    new_block->buffer = (unsigned char*)malloc(new_size);
    new_block->size = new_size;
    new_block->used = aligned_size;
    new_block->next = NULL;
    new_block->flags = 0;
    
    curr->next = new_block;
    
    return new_block->buffer;
}

char* arena_strdup(MemArena* arena, const char* str) {
    size_t len = strlen(str) + 1;
    char* copy = (char*)arena_alloc(arena, len);
    if (copy) memcpy(copy, str, len);
    return copy;
}

void arena_free(MemArena* arena) {
    MemArena* curr = arena;
    while (curr) {
        MemArena* next = curr->next;
        if (!(curr->flags & 1)) free(curr->buffer); // Free buffer if not static
        
        if (curr->flags & 2) {
             // Static Struct (Head): Do not free 'curr', just move to next
        } else {
             free(curr);
        }
        curr = next;
    }
}

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

void segment_list_add_from_arena(SegmentList* list, const char* str, MemArena* arena) {
    if (list->count >= list->capacity) {
        list->capacity *= 2;
        list->items = (char**)realloc(list->items, sizeof(char*) * list->capacity);
    }
    list->items[list->count++] = arena_strdup(arena, str);
}

void segment_list_free(SegmentList* list) {
    if (list) {
        // Deep free: assume ownership of strings by default (heap mode)
        for (size_t i = 0; i < list->count; i++) {
             free(list->items[i]);
        }
        free(list->items);
        free(list);
    }
}

// --- Rule Engine Definitions ---

struct RuleEngine {
    int dummy; // No state
};

// --- Helpers ---

// Minimal UTF-8 decoder
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
    if (cp >= 0x17D4 && cp <= 0x17DA) return 1;
    if (cp == 0x17DB) return 1;
    if (cp < 0x80 && (ispunct(cp) || isspace(cp))) return 1;
    if (cp == 0xA0) return 1;
    if (cp == 0x2DD) return 1;
    if (cp == 0xAB || cp == 0xBB) return 1;
    if (cp >= 0x2000 && cp <= 0x206F) return 1;
    if (cp >= 0x20A0 && cp <= 0x20CF) return 1;
    return 0; 
}

static int is_invalid_single(const char* s) {
    int cp;
    int len = utf8_decode_re(s, &cp);
    if (!cp) return 0;
    
    // Fix: Only consider Khmer characters as invalid singles
    if (!((cp >= 0x1780 && cp <= 0x17FF) || (cp >= 0x19E0 && cp <= 0x19FF))) return 0;

    if (s[len] != 0) return 0;
    if ((cp >= 0x1780 && cp <= 0x17A2) || (cp >= 0x17A3 && cp <= 0x17B3)) return 0;
    if (isdigit(cp) || (cp >= 0x17E0 && cp <= 0x17E9)) return 0;
    if (is_separator(s)) return 0;
    return 1;
}

RuleEngine* rule_engine_init(const char* rules_path) {
    (void)rules_path;
    RuleEngine* eng = (RuleEngine*)calloc(1, sizeof(RuleEngine));
    return eng;
}

void rule_engine_apply(RuleEngine* eng, SegmentList* segments, MemArena* arena) {
    if (!eng || !segments) return;
    
    int i = 0;
    while (i < (int)segments->count) {
        char* seg = segments->items[i];
        size_t len = strlen(seg);
        unsigned char* txt = (unsigned char*)seg;
        int rule_applied = 0;

        // Rule 0: "Ahsda Exception Keep"
        if (len == 6) {
            if (txt[3] == 0xE1 && txt[4] == 0x9F && txt[5] == 0x8F) { // U+17CF (Ahsda)
                if (txt[0] == 0xE1 && txt[1] == 0x9E && (txt[2] == 0x80 || txt[2] == 0x8A)) { // KA or DA
                    i++;
                    continue;
                }
            }
        }

        // Rule 1: "Prefix OR Merge"
        if (len == 3 && txt[0] == 0xE1 && txt[1] == 0x9E && txt[2] == 0xA2) {
             if (i + 1 < (int)segments->count && !is_separator(segments->items[i+1])) {
                 char* next = segments->items[i+1];
                 size_t new_len = len + strlen(next) + 1;
                 char* new_seg;
                 
                 if (arena) new_seg = (char*)arena_alloc(arena, new_len);
                 else new_seg = (char*)malloc(new_len);
                 
                 strcpy(new_seg, seg);
                 strcat(new_seg, next);
                 
                 if (!arena) free(segments->items[i]);
                 segments->items[i] = new_seg;
                 
                 if (!arena) free(segments->items[i+1]);
                 for (int k = i + 1; k < (int)segments->count - 1; k++) {
                     segments->items[k] = segments->items[k+1];
                 }
                 segments->count--;
                 rule_applied = 1;
             }
        }
        
        if (rule_applied) continue;

        // Rule 2 & 4: Suffix Checks (Signs Merge Left)
        if (len == 6) {
             if (txt[0] == 0xE1 && txt[1] == 0x9E && txt[2] >= 0x80 && txt[2] <= 0xA2) {
                 unsigned char* suffix = txt + 3;
                 int is_suffix_match = 0;
                 if (suffix[0] == 0xE1 && suffix[1] == 0x9F) {
                     unsigned char s3 = suffix[2];
                     if (s3 == 0x8B || s3 == 0x8E || s3 == 0x8F || s3 == 0x8C) {
                         is_suffix_match = 1;
                     }
                 }
                 
                 if (is_suffix_match) {
                     if (i > 0) {
                        char* prev = segments->items[i-1];
                        size_t new_len = strlen(prev) + len + 1;
                        char* new_seg;
                        
                        if (arena) new_seg = (char*)arena_alloc(arena, new_len);
                        else new_seg = (char*)malloc(new_len);
                        
                        strcpy(new_seg, prev);
                        strcat(new_seg, seg);
                        
                        if (!arena) free(segments->items[i-1]);
                        segments->items[i-1] = new_seg;
                        
                        if (!arena) free(segments->items[i]);
                        for (int k = i; k < (int)segments->count - 1; k++) {
                            segments->items[k] = segments->items[k+1];
                        }
                        segments->count--;
                        i--;
                        rule_applied = 1;
                     }
                 }
             }
        }
        
        if (rule_applied) continue;

        // Rule 3: Samyok Sannya (Merge Next)
        if (len == 6) {
             if (txt[0] == 0xE1 && txt[1] == 0x9E && txt[2] >= 0x80 && txt[2] <= 0xA2) {
                 if (txt[3] == 0xE1 && txt[4] == 0x9F && txt[5] == 0x90) {
                     if (i + 1 < (int)segments->count) {
                         char* next = segments->items[i+1];
                         size_t new_len = len + strlen(next) + 1;
                         char* new_seg;
                         
                         if (arena) new_seg = (char*)arena_alloc(arena, new_len);
                         else new_seg = (char*)malloc(new_len);
                         
                         strcpy(new_seg, seg);
                         strcat(new_seg, next);
                         
                         if (!arena) free(segments->items[i]);
                         segments->items[i] = new_seg;
                         
                         if (!arena) free(segments->items[i+1]);
                         for (int k = i + 1; k < (int)segments->count - 1; k++) {
                             segments->items[k] = segments->items[k+1];
                         }
                         segments->count--;
                         rule_applied = 1;
                     }
                 }
             }
        }
        
        if (rule_applied) continue;

        // Rule 5: Invalid Single Consonant Cleanup
        if (is_invalid_single(seg)) {
            int p_sep = 1; 
            if (i > 0) p_sep = is_separator(segments->items[i-1]);
            
            if (!p_sep) { 
                 if (i > 0) {
                    char* prev = segments->items[i-1];
                    size_t new_len = strlen(prev) + len + 1;
                    char* new_seg;
                    
                    if (arena) new_seg = (char*)arena_alloc(arena, new_len);
                    else new_seg = (char*)malloc(new_len);
                    
                    strcpy(new_seg, prev);
                    strcat(new_seg, seg);
                    
                    if (!arena) free(segments->items[i-1]);
                    segments->items[i-1] = new_seg;
                    
                    if (!arena) free(segments->items[i]);
                    for (int k = i; k < (int)segments->count - 1; k++) {
                        segments->items[k] = segments->items[k+1];
                    }
                    segments->count--;
                    i--;
                    rule_applied = 1;
                 }
            }
        }
        
        if (!rule_applied) i++;
    }
}

void rule_engine_free(RuleEngine* eng) {
    if (eng) {
        free(eng);
    }
}
