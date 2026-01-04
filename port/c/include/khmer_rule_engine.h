#ifndef KHMER_RULE_ENGINE_H
#define KHMER_RULE_ENGINE_H

#include <stddef.h>

/* A dynamic array of strings representing segments */
typedef struct {
    char** items;
    size_t count;
    size_t capacity;
} SegmentList;

SegmentList* segment_list_create(size_t cap);
void segment_list_add(SegmentList* list, const char* str);
void segment_list_free(SegmentList* list);

typedef struct RuleEngine RuleEngine;

RuleEngine* rule_engine_init(const char* rules_path);
void rule_engine_apply(RuleEngine* engine, SegmentList* segments);
void rule_engine_free(RuleEngine* engine);

#endif
