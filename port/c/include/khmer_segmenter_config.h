#ifndef KHMER_SEGMENTER_CONFIG_H
#define KHMER_SEGMENTER_CONFIG_H

/**
 * Configuration structure for toggleable segmenter features.
 * Allows benchmarking individual features by enabling/disabling them.
 */
typedef struct {
    int enable_frequency_costs;      /* Use frequency-based costs vs default cost */
    int enable_variant_generation;   /* Generate Ta/Da, Ro variants during dict load */
    int enable_repair_mode;          /* Handle malformed input gracefully */
    int enable_acronym_detection;    /* Detect and preserve acronyms (Cluster+.)+ */
    int enable_unknown_merging;      /* Merge consecutive unknown segments */
    int enable_normalization;       /* Enable input normalization */
} SegmenterConfig;

/**
 * Default configuration: All features enabled
 */
static inline SegmenterConfig segmenter_config_default() {
    SegmenterConfig config;
    config.enable_frequency_costs = 1;
    config.enable_variant_generation = 1;
    config.enable_repair_mode = 1;
    config.enable_acronym_detection = 1;
    config.enable_unknown_merging = 1;
    config.enable_normalization = 1;
    return config;
}

/**
 * Disabled configuration: All features off (baseline)
 */
static inline SegmenterConfig segmenter_config_disabled() {
    SegmenterConfig config;
    config.enable_frequency_costs = 0;
    config.enable_variant_generation = 0;
    config.enable_repair_mode = 0;
    config.enable_acronym_detection = 0;
    config.enable_unknown_merging = 0;
    config.enable_normalization = 0;
    return config;
}

#endif /* KHMER_SEGMENTER_CONFIG_H */
