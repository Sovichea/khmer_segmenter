/*
 * Minimal Regex Implementation
 * Based on tiny-regex-c
 */

#ifndef KEY_RE_H
#define KEY_RE_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct re_t re_t;

/* Compile regex string pattern to a regex_t structure. */
re_t* re_compile(const char* pattern);

/* Find matches of the compiled pattern inside text. */
int re_matchp(re_t* pattern, const char* text);

/* Find matches of the string pattern inside text (compile + match). */
int re_match(const char* pattern, const char* text);

void re_free(re_t* pattern);

#ifdef __cplusplus
}
#endif

#endif /* KEY_RE_H */
