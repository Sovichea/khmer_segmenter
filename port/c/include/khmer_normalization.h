#ifndef KHMER_NORMALIZATION_H
#define KHMER_NORMALIZATION_H

/**
 * @brief Normalize Khmer text.
 * Performs ZWS removal, Composite Fixes, and Cluster Reordering.
 * 
 * @param text Input text (UTF-8).
 * @return Newly allocated normalized string. Caller must free.
 */
char* khmer_normalize(const char* text);

#endif
