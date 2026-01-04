#ifndef KHMER_RULE_ENGINE_H
#define KHMER_RULE_ENGINE_H

#include <stddef.h>

// --- Memory Arena ---
typedef struct MemArena {
    unsigned char* buffer;
    size_t size;
    size_t used;
    struct MemArena* next;
    int flags; /* 1: Static Buffer, 2: Static Struct */
} MemArena;

void arena_init_static(MemArena* arena, void* buffer, size_t size);
MemArena* arena_create(size_t initial_size);
void* arena_alloc(MemArena* arena, size_t size);
char* arena_strdup(MemArena* arena, const char* str);
void arena_free(MemArena* arena);

/* A dynamic array of strings representing segments */
typedef struct {
    char** items;
    size_t count;
    size_t capacity;
} SegmentList;

SegmentList* segment_list_create(size_t cap);
void segment_list_add(SegmentList* list, const char* str);
void segment_list_add_from_arena(SegmentList* list, const char* str, MemArena* arena);
void segment_list_free(SegmentList* list);

// Updated Rule Engine API
typedef struct RuleEngine RuleEngine;
RuleEngine* rule_engine_init(const char* rules_path);
void rule_engine_apply(RuleEngine* engine, SegmentList* segments, MemArena* arena);
void rule_engine_free(RuleEngine* engine);

#endif
