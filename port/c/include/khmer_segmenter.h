#ifndef KHMER_SEGMENTER_H
#define KHMER_SEGMENTER_H

#include <stddef.h>
#include "khmer_segmenter_config.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct KhmerSegmenter KhmerSegmenter;

/**
 * @brief Initialize the Khmer Segmenter with default configuration (all features enabled).
 * 
 * @param dictionary_path Path to the dictionary file (line-separated words).
 * @param frequency_path Path to the binary frequency file.
 * @return Pointer to the segmenter instance, or NULL on failure.
 */
KhmerSegmenter* khmer_segmenter_init(const char* dictionary_path, const char* frequency_path);

/**
 * @brief Initialize the Khmer Segmenter with custom configuration.
 * 
 * @param dictionary_path Path to the dictionary file (line-separated words).
 * @param frequency_path Path to the binary frequency file (optional, can be NULL).
 * @param config Pointer to configuration struct (enables/disables features).
 * @return Pointer to the segmenter instance, or NULL on failure.
 */
KhmerSegmenter* khmer_segmenter_init_ex(const char* dictionary_path, const char* frequency_path, SegmenterConfig* config);

/**
 * @brief Segment a Khmer string.
 * 
 * @param segmenter Pointer to the segmenter instance.
 * @param text UTF-8 encoded Khmer text to segment.
 * @return A string containing the segmented text with zero-width spaces (or custom separator) inserted.
 *         The caller is responsible for freeing the returned string.
 */
char* khmer_segmenter_segment(KhmerSegmenter* segmenter, const char* text, const char* separator);

/**
 * @brief Free the segmenter instance.
 * 
 * @param segmenter Pointer to the segmenter instance.
 */
void khmer_segmenter_free(KhmerSegmenter* segmenter);

// ============================================================================
// Hyphenation API
// ============================================================================

typedef struct KHypDict KHypDict;

/**
 * @brief Initialize the Hyphenation Dictionary from a binary .kdict file
 * 
 * @param dict_path Path to the khmer_hyphenation.kdict file
 * @return Pointer to the dictionary instance, or NULL on failure
 */
KHypDict* khmer_hyphenation_init(const char* dict_path);

/**
 * @brief Look up a word's hyphenation map in O(1) time
 * 
 * @param dict Pointer to the hyphenation dictionary instance
 * @param word UTF-8 encoded Khmer word to lookup
 * @return Hyphenated string containing Zero Width Spaces (must not be freed), or NULL if not found
 */
const char* khmer_hyphenation_lookup(KHypDict* dict, const char* word);

/**
 * @brief Free the hyphenation dictionary instance
 * 
 * @param dict Pointer to the dictionary instance
 */
void khmer_hyphenation_free(KHypDict* dict);

#ifdef __cplusplus
}
#endif

#endif // KHMER_SEGMENTER_H
