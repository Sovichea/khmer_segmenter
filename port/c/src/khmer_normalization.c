#include "khmer_normalization.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// --- Constants & Types ---

static int get_char_type_norm(int c) {
    if ((c >= 0x1780 && c <= 0x17A2) || (c >= 0x17A3 && c <= 0x17B3)) return 1; // BASE
    if (c == 0x17D2) return 2; // COENG
    if (c == 0x17C9 || c == 0x17CA) return 3; // REGISTER
    if (c >= 0x17B6 && c <= 0x17C5) return 4; // VOWEL
    if ((c >= 0x17C6 && c <= 0x17D1) || c == 0x17D3 || c == 0x17DD) return 5; // SIGN
    return 0; // OTHER
}

// Helpers
static int utf8_dec_norm(const char* str, int* out_cp) {
    unsigned char c = (unsigned char)str[0];
    if (c < 0x80) { *out_cp = c; return 1; }
    if ((c & 0xE0) == 0xC0) {
        if (!str[1]) { *out_cp = 0; return 1; }
        *out_cp = ((c & 0x1F) << 6) | (str[1] & 0x3F); return 2; 
    }
    if ((c & 0xF0) == 0xE0) { 
        if (!str[1] || !str[2]) { *out_cp = 0; return 1; }
        *out_cp = ((c & 0x0F) << 12) | ((str[1] & 0x3F) << 6) | (str[2] & 0x3F); return 3; 
    }
    if ((c & 0xF8) == 0xF0) { 
        if (!str[1] || !str[2] || !str[3]) { *out_cp = 0; return 1; }
        *out_cp = ((c & 0x07) << 18) | ((str[1] & 0x3F) << 12) | ((str[2] & 0x3F) << 6) | (str[3] & 0x3F); return 4; 
    }
    *out_cp = 0; return 1;
}

// String Buffer
typedef struct {
    char* data;
    size_t len;
    size_t cap;
} StrBuf;

static void sb_init(StrBuf* sb, size_t cap) {
    sb->data = (char*)malloc(cap);
    sb->data[0] = 0;
    sb->len = 0;
    sb->cap = cap;
}

static void sb_append_len(StrBuf* sb, const char* s, size_t len) {
    if (sb->len + len + 1 >= sb->cap) {
        sb->cap = (sb->cap * 2) + len + 64;
        sb->data = (char*)realloc(sb->data, sb->cap);
    }
    memcpy(sb->data + sb->len, s, len);
    sb->len += len;
    sb->data[sb->len] = 0;
}

static void sb_append(StrBuf* sb, const char* s) {
    sb_append_len(sb, s, strlen(s));
}

// Cluster Item
typedef struct {
    char str[16]; // Max length of one cluster part
    int type; 
    int cp; 
} ClsPart;

static int get_prio(ClsPart* p) {
    int cp; 
    utf8_dec_norm(p->str, &cp);
    if (cp == 0x17D2) {
            // Check second char
            int next_cp;
            if (p->str[3]) { // simplistic utf-8 check assumes 3 byte coeng
                utf8_dec_norm(p->str + 3, &next_cp); // 17D2 is 3 bytes E1 9F 92
                if (next_cp == 0x179A) return 20;
            }
            return 10;
    }
    if (p->type == 3) return 30; // Register
    if (p->type == 4) return 40; // Vowel
    if (p->type == 5) return 50; // Sign
    return 100;
}

static int compare_parts(const void* a, const void* b) {
    ClsPart* pa = (ClsPart*)a;
    ClsPart* pb = (ClsPart*)b;
    
    int prioA = get_prio(pa);
    int prioB = get_prio(pb);
    if (prioA != prioB) return prioA - prioB;
    return pa->cp - pb->cp; // stable-ish
}

static void flush_cluster(StrBuf* final, ClsPart* cluster, int* cls_count) {
    if (*cls_count == 0) return;
    // Sort parts[1..end]
    if (*cls_count > 2) {
        qsort(cluster + 1, *cls_count - 1, sizeof(ClsPart), compare_parts);
    }
    for (int i=0; i < *cls_count; i++) {
        sb_append(final, cluster[i].str);
    }
    *cls_count = 0;
}

char* khmer_normalize(const char* text) {
    if (!text) return NULL;
    
    // 1. Pre-process: Remove ZWS, Replace Composites
    StrBuf temp;
    sb_init(&temp, strlen(text) + 1);
    
    const char* p = text;
    while (*p) {
        int cp;
        int len = utf8_dec_norm(p, &cp);
        
        // ZWS Removal
        if (cp == 0x200B) {
            p += len; 
            continue;
        }
        
        // Composite Checks (e + i -> oe, e + aa -> au)
        if (cp == 0x17C1) { // 'e'
            // Check next
            int next_cp;
            int next_len = 0;
            if (*(p+len)) next_len = utf8_dec_norm(p+len, &next_cp);
             
            if (next_len && next_cp == 0x17B8) { // i
                sb_append(&temp, "\xE1\x9E\xBE"); // oe (17BE)
                p += len + next_len;
                continue;
            }
            if (next_len && next_cp == 0x17B6) { // aa
                sb_append(&temp, "\xE1\x9F\x84"); // au (17C4)
                p += len + next_len;
                continue;
            }
        }
        
        sb_append_len(&temp, p, len);
        p += len;
    }
    
    // 2. Cluster processing
    StrBuf final;
    sb_init(&final, temp.len + 1);
    
    ClsPart cluster[64];
    int cls_count = 0;
    
    p = temp.data;
    size_t n = temp.len;
    size_t i = 0;
    
    while (i < n) {
        int cp;
        int len = utf8_dec_norm(p + i, &cp);
        int type = get_char_type_norm(cp);
        
        if (type == 1) { // BASE
            flush_cluster(&final, cluster, &cls_count);
            // Start new
            utf8_dec_norm(p + i, &cluster[cls_count].cp);
            cluster[cls_count].type = type;
            strncpy(cluster[cls_count].str, p+i, len);
            cluster[cls_count].str[len] = 0;
            cls_count++;
            i += len;
        }
        else if (type == 2) { // COENG
            // Consumes next if valid
            int next_cp;
            int next_len = 0;
            if (i + len < n) next_len = utf8_dec_norm(p + i + len, &next_cp);
            
            // If next is BASE or RO? (all consonants)
            if (next_len && (next_cp >= 0x1780 && next_cp <= 0x17A2)) {
                 // Combined part
                 strncpy(cluster[cls_count].str, p+i, len + next_len);
                 cluster[cls_count].str[len + next_len] = 0;
                 cluster[cls_count].type = 2; // Coeng Part
                 cluster[cls_count].cp = cp;
                 cls_count++;
                 i += len + next_len;
            } else {
                 // Stray coeng
                 strncpy(cluster[cls_count].str, p+i, len);
                 cluster[cls_count].str[len] = 0;
                 cluster[cls_count].type = 2; // Treat as Coeng
                 cluster[cls_count].cp = cp;
                 cls_count++;
                 i += len;
            }
        }
        else if (type == 3 || type == 4 || type == 5) {
            // Modifiers
            if (cls_count > 0) {
                 strncpy(cluster[cls_count].str, p+i, len);
                 cluster[cls_count].str[len] = 0;
                 cluster[cls_count].type = type;
                 cluster[cls_count].cp = cp;
                 cls_count++;
                 i += len; 
            } else {
                 // Isolated modifier
                 sb_append_len(&final, p+i, len);
                 i += len;
            }
        }
        else {
             // Other
             flush_cluster(&final, cluster, &cls_count);
             sb_append_len(&final, p+i, len);
             i += len;
        }
        
        if (cls_count >= 63) flush_cluster(&final, cluster, &cls_count); // Safety
    }
    flush_cluster(&final, cluster, &cls_count);
    
    free(temp.data);
    return final.data;
}
