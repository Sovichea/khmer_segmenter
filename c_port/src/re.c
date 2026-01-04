#include "re.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// Cross-platform strdup compatibility
#if defined(_WIN32)
    #define STRDUP _strdup
#else
    #define STRDUP strdup
#endif

/*
 * Specialized Pattern Matcher for Khmer Segmenter Rules
 * Supports:
 * - Literals (UTF-8 bytes)
 * - ^ and $ anchors
 * - [...] Character classes with ranges (uXXXX-uYYYY) and lists (uXXXX)
 * - (a|b) Simple Alternation (top level only for simplicity or simple groups)
 */

typedef enum {
    OP_MATCH,
    OP_CHAR,
    OP_CLASS,
    OP_ALTERNATION,
    OP_END
} OpCode;

typedef struct {
    OpCode type;
    union {
        int cp; // OP_CHAR
        struct {
            int* ranges; // Pairs [start, end]
            int count;
        } cls;
        struct {
            char** options;
            int count;
        } alt;
    } data;
} Instruction;

struct re_t {
    Instruction* insts;
    int count;
    int anchored_start;
    int anchored_end;
};

// Helper: Decode UTF-8 (duplicated from khmer_segmenter.c to keep independent, or we can link)
static int utf8_decode_re(const char* str, int* out_codepoint) {
    unsigned char c = (unsigned char)str[0];
    if (c < 0x80) { *out_codepoint = c; return 1; }
    if ((c & 0xE0) == 0xC0) { 
        if (!str[1]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x1F) << 6) | (str[1] & 0x3F); return 2; 
    }
    if ((c & 0xF0) == 0xE0) { 
        if (!str[1] || !str[2]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x0F) << 12) | ((str[1] & 0x3F) << 6) | (str[2] & 0x3F); return 3; 
    }
    if ((c & 0xF8) == 0xF0) { 
        if (!str[1] || !str[2] || !str[3]) { *out_codepoint = 0; return 1; }
        *out_codepoint = ((c & 0x07) << 18) | ((str[1] & 0x3F) << 12) | ((str[2] & 0x3F) << 6) | (str[3] & 0x3F); return 4; 
    }
    *out_codepoint = 0; return 1;
}

static int parse_hex_codepoint(const char* p, int* out_cp) {
    // Expect uXXXX or \uXXXX
    if (*p == '\\') p++;
    if (*p == 'u') p++;
    char buf[5] = {0};
    strncpy(buf, p, 4);
    *out_cp = (int)strtol(buf, NULL, 16);
    return 4; // chars consumed from hex part (XXXX)
}

re_t* re_compile(const char* pattern) {
    if (!pattern) return NULL;
    re_t* re = (re_t*)calloc(1, sizeof(re_t));
    re->insts = (Instruction*)calloc(32, sizeof(Instruction)); // Cap 32 instructions
    
    const char* p = pattern;
    if (*p == '^') {
        re->anchored_start = 1;
        p++;
    }
    
    // Parse loop
    int idx = 0;
    while (*p) {
        if (*p == '$' && *(p+1) == '\0') {
            re->anchored_end = 1;
            break;
        }
        
        if (*p == '[') {
            // Character Class
            p++;
            Instruction* inst = &re->insts[idx++];
            inst->type = OP_CLASS;
            inst->data.cls.ranges = (int*)calloc(32, sizeof(int) * 2); // Cap
            int r_idx = 0;
            
            while (*p && *p != ']') {
                int cp1;
                int len1 = 0;
                if (*p == '\\' && *(p+1) == 'u') {
                    // Unicode escape \uXXXX
                    len1 = 2 + parse_hex_codepoint(p, &cp1);
                } else if (*p == '\\' && *(p+1) != 'u') {
                    // Escaped literal
                    p++;
                    len1 = utf8_decode_re(p, &cp1);
                } else {
                    // Literal
                    len1 = utf8_decode_re(p, &cp1);
                }
                
                // Check range dash
                // Format: A-B
                // If next char is '-' and char AFTER that is not ']'
                const char* next_p = p + len1;
                if (*next_p == '-' && *(next_p+1) != ']') {
                    p = next_p + 1; // skip dash
                    int cp2;
                    int len2 = 0;
                    if (*p == '\\' && *(p+1) == 'u') {
                        len2 = 2 + parse_hex_codepoint(p, &cp2);
                    } else {
                         len2 = utf8_decode_re(p, &cp2);
                    }
                    inst->data.cls.ranges[r_idx*2] = cp1;
                    inst->data.cls.ranges[r_idx*2+1] = cp2;
                    r_idx++;
                    p += len2;
                } else {
                    // Single char range
                    inst->data.cls.ranges[r_idx*2] = cp1;
                    inst->data.cls.ranges[r_idx*2+1] = cp1;
                    r_idx++;
                    p += len1;
                }
            }
            inst->data.cls.count = r_idx;
            if (*p == ']') p++;
        } 
        else if (*p == '(') {
            // Group / Alternation (kork|dor)
            p++;
            Instruction* inst = &re->insts[idx++];
            inst->type = OP_ALTERNATION;
            inst->data.alt.options = (char**)calloc(8, sizeof(char*));
            int opt_idx = 0;
            
            char buffer[64];
            int b_idx = 0;
            while (*p && *p != ')') {
                if (*p == '|') {
                    buffer[b_idx] = '\0';
                    inst->data.alt.options[opt_idx++] = STRDUP(buffer);
                    b_idx = 0;
                    p++;
                } else {
                    buffer[b_idx++] = *p++;
                }
            }
            buffer[b_idx] = '\0';
            inst->data.alt.options[opt_idx++] = STRDUP(buffer);
            inst->data.alt.count = opt_idx;
            
            if (*p == ')') p++;
        }
        else {
            // Literal Char
            Instruction* inst = &re->insts[idx++];
            inst->type = OP_CHAR;
            int cp;
            int len = 0;
            if (*p == '\\' && *(p+1) == 'u') {
                 len = 2 + parse_hex_codepoint(p, &cp);
            } else {
                 len = utf8_decode_re(p, &cp);
            }
            inst->data.cp = cp;
            p += len;
        }
    }
    re->count = idx;
    return re;
}

int re_matchp(re_t* re, const char* text) {
    if (!re || !text) return 0;
    
    // Simple matching engine (no backtracking needed for these simple rules usually)
    // But Alternation needs branch? Or just string compare?
    // Our alternation is simple strings: (A|B).
    
    const char* t = text;
    int inst_idx = 0;
    
    while (inst_idx < re->count) {
        if (*t == '\0') {
             // End of text, but have instructions left?
             return 0; 
        }
        
        Instruction* inst = &re->insts[inst_idx];
        int cp;
        int len = utf8_decode_re(t, &cp);
        
        switch (inst->type) {
            case OP_CHAR:
                if (cp != inst->data.cp) return 0;
                t += len;
                break;
            case OP_CLASS: {
                int found = 0;
                for (int i=0; i < inst->data.cls.count; i++) {
                    int start = inst->data.cls.ranges[i*2];
                    int end = inst->data.cls.ranges[i*2+1];
                    if (cp >= start && cp <= end) {
                        found = 1;
                        break;
                    }
                }
                if (!found) return 0;
                t += len;
                break;
            }
            case OP_ALTERNATION: {
                // Check if current text matches any option
                int matched = 0;
                for (int i=0; i < inst->data.alt.count; i++) {
                    char* opt = inst->data.alt.options[i];
                    // Warning: Option is UTF-8 string, 't' is start of text
                    // We need to see if 't' STARTS with 'opt'
                    // For (kork|dor), options are "ក៏", "ដ៏".
                    // They are generally multi-char.
                    if (strncmp(t, opt, strlen(opt)) == 0) {
                        t += strlen(opt);
                        matched = 1;
                        break;
                    }
                }
                if (!matched) return 0;
                break;
            }
        }
        inst_idx++;
    }
    
    // If anchored end, check endpoint
    if (re->anchored_end) {
        if (*t != '\0') return 0;
    }
    
    return 1;
}

int re_match(const char* pattern, const char* text) {
    re_t* re = re_compile(pattern);
    if (!re) return 0;
    int res = re_matchp(re, text);
    re_free(re);
    return res;
}

void re_free(re_t* re) {
    if (re) {
        for (int i=0; i < re->count; i++) {
            if (re->insts[i].type == OP_CLASS) {
                free(re->insts[i].data.cls.ranges);
            }
            if (re->insts[i].type == OP_ALTERNATION) {
                for(int k=0; k<re->insts[i].data.alt.count; k++) free(re->insts[i].data.alt.options[k]);
                free(re->insts[i].data.alt.options);
            }
        }
        free(re->insts);
        free(re);
    }
}
