#define _CRT_SECURE_NO_WARNINGS
#include "khmer_segmenter.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <stdint.h>

// Cross-platform strdup compatibility
#if defined(_WIN32)
    #define STRDUP _strdup
#else
    #define STRDUP strdup
#endif

// ============================================================================
// Internal Data Structures (Baked Binary Dictionary)
// ============================================================================

#pragma pack(push, 1)

typedef struct {
    char magic[4];          // "KDIC"
    uint32_t version;       // 1
    uint32_t num_entries;
    uint32_t table_size;
    float default_cost;
    float unknown_cost;
    uint32_t max_word_length;
    uint32_t padding;
} KDictHeader;

typedef struct {
    uint32_t name_offset; // Offset into string pool (0 = Empty)
    float cost;
} KDictEntry;

#pragma pack(pop)

// DJB2 Hash (must match Python script)
static uint32_t djb2_hash(const char* str) {
    uint32_t hash = 5381;
    int c;
    while ((c = *(unsigned char*)str++))
        hash = ((hash << 5) + hash) + c; 
    return hash;
}

static uint32_t djb2_hash_len(const char* str, size_t len) {
    uint32_t hash = 5381;
    for (size_t i = 0; i < len; i++) {
        hash = ((hash << 5) + hash) + (unsigned char)str[i];
    }
    return hash;
}

// ============================================================================
// UTF-8 Helper Utils
// ============================================================================

static int utf8_decode(const char* str, int* out_codepoint) {
    unsigned char c = (unsigned char)str[0];
    if (c < 0x80) {
        *out_codepoint = c;
        return 1;
    } else if ((c & 0xE0) == 0xC0) {
        if (!str[1]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x1F) << 6) | (str[1] & 0x3F);
        return 2;
    } else if ((c & 0xF0) == 0xE0) {
        if (!str[1] || !str[2]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x0F) << 12) | ((str[1] & 0x3F) << 6) | (str[2] & 0x3F);
        return 3;
    } else if ((c & 0xF8) == 0xF0) {
        if (!str[1] || !str[2] || !str[3]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x07) << 18) | ((str[1] & 0x3F) << 12) | ((str[2] & 0x3F) << 6) | (str[3] & 0x3F);
        return 4;
    }
    *out_codepoint = 0;
    return 1; 
}

// ============================================================================
// Segmenter Logic
// ============================================================================

#include "khmer_normalization.h"
#include "khmer_rule_engine.h"
#include "khmer_segmenter_config.h"

struct KhmerSegmenter {
    // Binary Blob Management
    void* blob_data;
    size_t blob_size;
    
    // Pointers into blob (Cached for speed)
    KDictHeader* header;
    KDictEntry* table;
    char* string_pool;
    uint32_t table_mask; // size - 1 (assuming power of 2)
    
    // Runtime modules
    RuleEngine* rule_engine;
    SegmenterConfig config;
};

// --- Helper Functions ---

static int is_khmer_char(int cp) {
    return (cp >= 0x1780 && cp <= 0x17FF) || (cp >= 0x19E0 && cp <= 0x19FF);
}

static int is_digit_cp(int cp) {
    // 0-9
    if (cp >= 0x30 && cp <= 0x39) return 1;
    // Khmer Digits
    if (cp >= 0x17E0 && cp <= 0x17E9) return 1;
    return 0;
}

static int is_separator_cp(int cp) {
    // Khmer Punctuation
    if (cp >= 0x17D4 && cp <= 0x17DA) return 1;
    // Khmer Currency
    if (cp == 0x17DB) return 1;

    // Basic ASCII Punctuation & Space
    if (cp < 0x80 && (ispunct(cp) || isspace(cp))) return 1;
    
    // Additional separators
    if (cp == 0xA0) return 1; // Non-breaking space
    if (cp == 0x2DD) return 1; // Double acute accent
    
    // Latin-1 Supplement Punctuation (Guillemets « » and others)
    // 0xAB: «, 0xBB: »
    if (cp == 0xAB || cp == 0xBB) return 1;
    
    // General Punctuation (0x2000-0x206F)
    // Includes various spaces, dashes, quotes, bullets
    if (cp >= 0x2000 && cp <= 0x206F) return 1;
    
    // Currency Symbols (0x20A0-0x20CF)
    if (cp >= 0x20A0 && cp <= 0x20CF) return 1;

    return 0;
}

static int is_valid_single_base_char(int cp) {
    // Consonants: 0x1780 - 0x17A2
    if (cp >= 0x1780 && cp <= 0x17A2) return 1;
    // Independent Vowels: 0x17A3 - 0x17B3
    if (cp >= 0x17A3 && cp <= 0x17B3) return 1;
    return 0;
}

static int get_khmer_cluster_length(const char* text, size_t n, size_t start_idx, size_t* out_bytes) {
    size_t i = start_idx;
    if (i >= n) return 0;

    int cp;
    int len = utf8_decode(text + i, &cp);
    
    // Must start with Base or Indep Vowel
    if (!(cp >= 0x1780 && cp <= 0x17B3)) {
        *out_bytes = len;
        // If it's a coeng/vowel at start, invalid but consume 1 char
        return 1; 
    }
    
    i += len;
    
    // Look ahead for Subscripts and Vowels
    while (i < n) {
        int next_cp;
        int next_len = utf8_decode(text + i, &next_cp);
        
        // Coeng (0x17D2) handling
        if (next_cp == 0x17D2) {
            // Check next next
            if (i + next_len < n) {
                int sub_cp;
                int sub_len = utf8_decode(text + i + next_len, &sub_cp);
                if (sub_cp >= 0x1780 && sub_cp <= 0x17A2) {
                    i += next_len + sub_len;
                    continue;
                }
            }
            break; // Trailing coeng or invalid
        }
        
        // Vowels/Signs
        // 0x17B6 - 0x17D1, 0x17D3, 0x17DD
        if ((next_cp >= 0x17B6 && next_cp <= 0x17D1) || next_cp == 0x17D3 || next_cp == 0x17DD) {
             i += next_len;
             continue;
        }
        
        break;
    }
    
    *out_bytes = i - start_idx;
    return 1;
}

static size_t get_number_length(const char* text, size_t n, size_t start_idx) {
    size_t i = start_idx;
    int cp;
    int len = utf8_decode(text + i, &cp);
    
    // Must start with digit
    if (!is_digit_cp(cp)) return 0;
    
    i += len;
    while (i < n) {
        int next_cp;
        int next_len = utf8_decode(text + i, &next_cp);
        
        if (is_digit_cp(next_cp)) {
            i += next_len;
            continue;
        }
        
        // Separators: , . Space
        // Must be followed by digit
        if (next_cp == ',' || next_cp == '.' || next_cp == ' ') {
            if (i + next_len < n) {
                int f_cp;
                int f_len = utf8_decode(text + i + next_len, &f_cp);
                if (is_digit_cp(f_cp)) {
                    i += next_len + f_len; // Consume SEP + DIGIT
                    continue;
                }
            }
        }
        
        break;
    }
    return i - start_idx;
}

// --- Acronym Detection ---

static int is_acronym_start(const char* text, size_t n, size_t index) {
    // Need at least 2 chars: Cluster + .
    if (index + 1 >= n) return 0;
    
    // Must start with Khmer Consonant or Independent Vowel
    int cp;
    utf8_decode(text + index, &cp);
    if (!(cp >= 0x1780 && cp <= 0x17B3)) return 0;
    
    // Get cluster length
    size_t cluster_bytes;
    if (!get_khmer_cluster_length(text, n, index, &cluster_bytes)) return 0;
    
    // Check if char AFTER cluster is dot
    size_t dot_index = index + cluster_bytes;
    if (dot_index < n && text[dot_index] == '.') {
        return 1;
    }
    
    return 0;
}

static size_t get_acronym_length(const char* text, size_t n, size_t start_idx) {
    size_t i = start_idx;
    
    while (i < n) {
        // Must start with Khmer Consonant/Indep Vowel
        int cp;
        utf8_decode(text + i, &cp);
        if (!(cp >= 0x1780 && cp <= 0x17B3)) break;
        
        size_t cluster_bytes;
        if (!get_khmer_cluster_length(text, n, i, &cluster_bytes)) break;
        
        size_t dot_index = i + cluster_bytes;
        if (dot_index < n && text[dot_index] == '.') {
            i = dot_index + 1; // Advance past cluster and dot
            continue;
        } else {
            break;
        }
    }
    
    return i - start_idx;
}

// --- Init & Load ---

static int load_kdict(KhmerSegmenter* seg, const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    
    // Get file size
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    if (size < sizeof(KDictHeader)) {
        fclose(f);
        return 0;
    }
    
    // Allocate single block for entire file
    seg->blob_data = malloc(size);
    if (!seg->blob_data) {
        fclose(f);
        return 0;
    }
    seg->blob_size = size;
    
    if (fread(seg->blob_data, 1, size, f) != (size_t)size) {
        free(seg->blob_data);
        fclose(f);
        return 0;
    }
    fclose(f);
    
    // Setup pointers
    seg->header = (KDictHeader*)seg->blob_data;
    
    // Verify Magic "KDIC"
    if (memcmp(seg->header->magic, "KDIC", 4) != 0) {
        fprintf(stderr, "Invalid dictionary format: Magic mismatch\n");
        free(seg->blob_data);
        return 0;
    }
    
    // Pointers
    // Table follows header immediately
    seg->table = (KDictEntry*)((char*)seg->blob_data + sizeof(KDictHeader));
    // Pool follows table
    size_t table_bytes = seg->header->table_size * sizeof(KDictEntry);
    seg->string_pool = (char*)seg->table + table_bytes;
    
    // Precompute mask (size is power of 2)
    seg->table_mask = seg->header->table_size - 1;
    
    printf("Loaded baked dictionary: %u words, %.2f MB\n", 
           seg->header->num_entries, 
           (double)size / (1024.0*1024.0));
    
    return 1;
}

KhmerSegmenter* khmer_segmenter_init_ex(const char* dictionary_path, const char* frequency_path, SegmenterConfig* config) {
    KhmerSegmenter* seg = (KhmerSegmenter*)malloc(sizeof(KhmerSegmenter));
    memset(seg, 0, sizeof(KhmerSegmenter));

    // Set configuration
    if (config) {
        seg->config = *config;
    } else {
        seg->config = segmenter_config_default();
    }
    
    seg->rule_engine = rule_engine_init(NULL);

    // Load Binary Dictionary
    // Prioritize generic "kdict" path if provided, else fallback to standard location
    // Note: The previous API took .txt and .bin paths. Now we expect a SINGLE .kdict path.
    // However, to maintain API compatibility, we might check if 'dictionary_path' ends in .kdict
    // OR just construct the path.
    
    const char* kdict_path = "khmer_dictionary.kdict";
    // Check if dictionary_path points to the kdict
    if (dictionary_path && strstr(dictionary_path, ".kdict")) {
        kdict_path = dictionary_path;
    } else {
        // Fallback: try to find adjacent to executable or hardcoded
        // For C port, usually run from bin/ folder, so data might be ../../port/common/khmer_dictionary.kdict
        // Or passed explicitly.
        // Let's assume the user passes the correct path or we deduce it.
        // For development, we hardcode relative path for checking:
        // But for production, the caller must provide it.
        if (dictionary_path) kdict_path = dictionary_path; // Assume caller knows best
    }

    if (!load_kdict(seg, kdict_path)) {
        // Try fallback location (common dev path)
        if (!load_kdict(seg, "../common/khmer_dictionary.kdict")) {
            if (!load_kdict(seg, "../../port/common/khmer_dictionary.kdict")) {
                 fprintf(stderr, "Failed to load dictionary: %s\n", kdict_path);
            }
        }
    }
    
    return seg;
}

KhmerSegmenter* khmer_segmenter_init(const char* dictionary_path, const char* frequency_path) {
    return khmer_segmenter_init_ex(dictionary_path, frequency_path, NULL);
}

void khmer_segmenter_free(KhmerSegmenter* seg) {
    if (seg) {
        if (seg->blob_data) free(seg->blob_data);
        if (seg->rule_engine) rule_engine_free(seg->rule_engine); 
        free(seg);
    }
}


// --- Segmentation (Viterbi) ---

// Struct for DP state
typedef struct {
    float cost;
    int prev_idx;
} State;

char* khmer_segmenter_segment(KhmerSegmenter* seg, const char* raw_text, const char* separator) {
    if (!raw_text || !*raw_text) return STRDUP("");
    if (!separator) separator = "\xE2\x80\x8B"; 
    
    // Safety check: if binary dict not loaded
    if (!seg->header) return STRDUP(raw_text);

    // Normalize input text
    char* text;
    if (seg->config.enable_normalization) {
        text = khmer_normalize(raw_text);
    } else {
        text = STRDUP(raw_text);
    }
    if (!text) return STRDUP("");
    size_t n = strlen(text);

    // Initialize memory arena with a 32KB stack buffer (SBO)
    unsigned char stack_buf[32 * 1024];
    MemArena arena;
    arena_init_static(&arena, stack_buf, sizeof(stack_buf));

    // Initialize DP table
    State* dp = (State*)arena_alloc(&arena, (n + 1) * sizeof(State));
    if (!dp) { free(text); arena_free(&arena); return STRDUP(""); } 

    for (size_t i = 0; i <= n; i++) {
        dp[i].cost = 1e9f; 
        dp[i].prev_idx = -1;
    }
    dp[0].cost = 0;

    // Viterbi forward pass
    for (size_t i = 0; i < n; ) {
        // Skip unreachable states
        if (dp[i].cost >= 1e9f) {
             int d_cp;
             i += utf8_decode(text + i, &d_cp);
             continue;
        }

        int cp;
        int char_len = utf8_decode(text + i, &cp);

        // Optional: Repair Mode for malformed input
        if (seg->config.enable_repair_mode) {
            int force_repair = 0;
            if (i > 0) {
                int prev_cp;
                utf8_decode(text + i - 1, &prev_cp);
                // Check for orphaned Coeng
                if (prev_cp == 0x17D2 && (cp >= 0x1780 && cp <= 0x17A2)) force_repair = 1;
            }
            // Check for isolated dependent vowel
            if (cp >= 0x17B6 && cp <= 0x17C5) force_repair = 1;
        
            if (force_repair) {
                size_t next_idx = i + char_len;
                float repair_cost = seg->header->unknown_cost + 50.0f;
                if (next_idx <= n && dp[i].cost + repair_cost < dp[next_idx].cost) {
                    dp[next_idx].cost = dp[i].cost + repair_cost;
                    dp[next_idx].prev_idx = (int)i;
                }
                i++; // Proceed to next byte
                continue; 
            }
        }

        // Handle Numbers, Currency, and Separators
        int is_dig = is_digit_cp(cp);
        int is_curr_start = 0;
        if ((cp == '$' || cp == 0x17DB || cp == 0x20AC || cp == 0xA3 || cp == 0xA5) && i + char_len < n) {
             int next_c;
             utf8_decode(text + i + char_len, &next_c);
             if (is_digit_cp(next_c)) is_curr_start = 1;
        }

        if (is_dig || is_curr_start) {
             size_t num_len = get_number_length(text, n, i);
             size_t next_idx = i + num_len;
             float step_cost = 1.0f;
             if (next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost) {
                 dp[next_idx].cost = dp[i].cost + step_cost;
                 dp[next_idx].prev_idx = (int)i;
             }
        }
        else if (is_separator_cp(cp)) {
             size_t next_idx = i + char_len;
             float step_cost = 0.1f; 
             if (next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost) {
                 dp[next_idx].cost = dp[i].cost + step_cost;
                 dp[next_idx].prev_idx = (int)i;
             }
        }

        // Handle Acronyms
        if (seg->config.enable_acronym_detection && is_acronym_start(text, n, i)) {
            size_t acr_len = get_acronym_length(text, n, i);
            size_t next_idx = i + acr_len;
            float step_cost = seg->header->default_cost;
            if (next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost) {
                dp[next_idx].cost = dp[i].cost + step_cost;
                dp[next_idx].prev_idx = (int)i;
            }
        }

        // Dictionary Lookup (Baked Binary KDict) - Optimized with Incremental Hashing
        size_t end_limit = i + seg->header->max_word_length;
        if (end_limit > n) end_limit = n;

        uint32_t khash = 5381;
        for (size_t j = i; j < end_limit; ) {
            int next_cp;
            int next_len = utf8_decode(text + j, &next_cp);
            
            // Incremental hash for this character's bytes
            for (int k = 0; k < next_len; k++) {
                khash = ((khash << 5) + khash) + (unsigned char)text[j + k];
            }
            j += next_len;
            size_t len = j - i;
            
            // --- KDict Lookup (Inline) ---
            uint32_t idx = khash & seg->table_mask;
            while (seg->table[idx].name_offset != 0) {
                 const char* stored_word = seg->string_pool + seg->table[idx].name_offset;
                 // Optimized string comparison
                 if (stored_word[0] == text[i] && strncmp(stored_word, text + i, len) == 0 && stored_word[len] == 0) {
                     float new_cost = dp[i].cost + seg->table[idx].cost;
                     if (new_cost < dp[j].cost) {
                         dp[j].cost = new_cost;
                         dp[j].prev_idx = (int)i;
                     }
                     break;
                 }
                 idx = (idx + 1) & seg->table_mask;
            }
        }
        
        // Handle Unknown Clusters
        size_t cluster_bytes = 0;
        int is_khmer = is_khmer_char(cp);
        if (is_khmer) get_khmer_cluster_length(text, n, i, &cluster_bytes);
        else cluster_bytes = char_len;

        size_t next_idx = i + cluster_bytes;
        float unk_cost = seg->header->unknown_cost;
        if (cluster_bytes == char_len && is_khmer) { 
             // Penalize invalid single base chars
             if (!is_valid_single_base_char(cp)) unk_cost += 10.0f; 
        }
        
        if (next_idx <= n) {
            float new_cost = dp[i].cost + unk_cost;
            if (new_cost < dp[next_idx].cost) {
                dp[next_idx].cost = new_cost;
                dp[next_idx].prev_idx = (int)i;
            }
        }
        
        i += char_len;
    }

    // Backtracking
    if (dp[n].prev_idx == -1) {
        char* fallback = STRDUP(text);
        free(text); 
        arena_free(&arena);
        return fallback; 
    }

    // Collect segment breaks
    int* breaks = (int*)arena_alloc(&arena, (n + 1) * sizeof(int));
    int count = 0;
    int curr = (int)n;
    while (curr > 0) {
        breaks[count++] = curr;
        curr = dp[curr].prev_idx;
    }
    breaks[count++] = 0; 
    
    // Construct Initial SegmentList
    SegmentList* seg_list = (SegmentList*)arena_alloc(&arena, sizeof(SegmentList));
    seg_list->capacity = count; 
    seg_list->count = 0;
    seg_list->items = (char**)arena_alloc(&arena, sizeof(char*) * count);
    
    for (int k = count - 1; k > 0; k--) {
        int start = breaks[k];
        int end = breaks[k-1];
        int len = end - start;
        
        char* s = (char*)arena_alloc(&arena, len + 1);
        memcpy(s, text + start, len);
        s[len] = 0;
        seg_list->items[seg_list->count++] = s;
    }
    
    free(text); 

    // Apply Rule Engine
    if (seg->rule_engine) {
        rule_engine_apply(seg->rule_engine, seg_list, &arena);
    }

    // Merge Consecutive Unknowns (Heuristic)
    if (seg->config.enable_unknown_merging && seg_list->count > 0) {
        size_t est_cap = seg_list->count;
        char** new_items = (char**)arena_alloc(&arena, sizeof(char*) * est_cap);
        size_t new_count = 0;
        
        char* unknown_buffer = NULL; // Use malloc for this buffer as it grows
        size_t buffer_len = 0;
        size_t buffer_cap = 0;
        
        for (size_t i = 0; i < seg_list->count; i++) {
            const char* s = seg_list->items[i];
            
            // Heuristic to check if 's' is a known word / token
            int is_known = 0;
            size_t slen = strlen(s);
            if (slen > 0 && slen <= 4) {
                int cp_t;
                int l_t = utf8_decode(s, &cp_t);
                if (l_t == (int)slen && is_separator_cp(cp_t)) is_known = 1;
            }
            if (!is_known && slen > 0) {
                int cp_t;
                utf8_decode(s, &cp_t);
                if (is_digit_cp(cp_t)) is_known = 1;
            }
            
            // KDict Lookup for known words
            if (!is_known && seg->header) {
                 uint32_t kh = djb2_hash(s);
                 uint32_t kidx = kh & seg->table_mask;
                 while (seg->table[kidx].name_offset != 0) {
                     const char* sw = seg->string_pool + seg->table[kidx].name_offset;
                     if (strcmp(sw, s) == 0) {
                          is_known = 1;
                          break;
                     }
                     kidx = (kidx + 1) & seg->table_mask;
                 }
            }

            if (!is_known && slen > 0) {
                 int cp_t;
                 int l_t = utf8_decode(s, &cp_t);
                 if (l_t == slen && is_valid_single_base_char(cp_t)) is_known = 1;
            }
            if (!is_known && slen >= 2 && strchr(s, '.')) is_known = 1; 
            
            if (is_known) {
                if (unknown_buffer) {
                    // Flush accumulated unknown buffer
                    new_items[new_count++] = arena_strdup(&arena, unknown_buffer);
                    
                    free(unknown_buffer);
                    unknown_buffer = NULL;
                    buffer_len = 0; buffer_cap = 0;
                }
                new_items[new_count++] = (char*)s;
            } else {
                // Accumulate unknown segment
                 if (buffer_len + slen + 1 > buffer_cap) {
                    buffer_cap = (buffer_len + slen + 1) * 2;
                    if (buffer_cap < 64) buffer_cap = 64;
                    unknown_buffer = (char*)realloc(unknown_buffer, buffer_cap);
                    if (buffer_len == 0) unknown_buffer[0] = 0;
                }
                strcat(unknown_buffer, s);
                buffer_len += slen;
            }
        }
        
        if (unknown_buffer) {
             new_items[new_count++] = arena_strdup(&arena, unknown_buffer);
             free(unknown_buffer);
        }
        
        seg_list->items = new_items;
        seg_list->count = new_count;
        seg_list->capacity = est_cap; 
    }

    // Final Concatenation
    size_t sep_len = strlen(separator);
    size_t total_len = 0;
    for (size_t i = 0; i < seg_list->count; i++) {
        total_len += strlen(seg_list->items[i]);
        if (i < seg_list->count - 1) total_len += sep_len;
    }
    
    char* final_res = (char*)malloc(total_len + 1);
    char* ptr = final_res;
    for (size_t i = 0; i < seg_list->count; i++) {
        size_t slen = strlen(seg_list->items[i]);
        memcpy(ptr, seg_list->items[i], slen);
        ptr += slen;
        if (i < seg_list->count - 1) {
            memcpy(ptr, separator, sep_len);
            ptr += sep_len;
        }
    }
    *ptr = 0;
    
    arena_free(&arena);
    
    return final_res;
}
