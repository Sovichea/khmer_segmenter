# Curated segmentation benchmark

This directory defines the release-gating benchmark for the RAC 2022 runtime.
The older khPOS and Khmer ALT corpora remain useful compatibility diagnostics,
but their segmentation conventions are not authoritative for this project.

The completed benchmark must contain exactly 300 redistribution-cleared
sentences: 200 development records and 100 frozen test records. Planned strata:

| Category | Total |
| --- | ---: |
| News and formal prose | 60 |
| Conversational text | 40 |
| Public administration | 40 |
| Education | 35 |
| Literary and religious text | 35 |
| Technical text | 30 |
| Names and locations | 25 |
| Repetition forms and numerals | 20 |
| Valid but difficult Unicode | 15 |

Every record needs a source URL or a `project-authored` declaration, explicit
redistribution terms, attribution, and human review. A record becomes eligible
for scoring only after `review.status` is `approved`. Prefer independent review
by two Khmer speakers; document adjudication whenever their boundaries differ.

The test split is frozen after its first approved release. Tune model choices on
the development split only. Never derive accepted spellings from this benchmark.

Validate and score a completed JSONL file with:

```bash
python scripts/evaluate_segmentation.py \
  --dataset curated \
  --dataset-path benchmarks/curated/benchmark.jsonl \
  --split dev \
  --output results/curated-dev.json
```

`example.draft.jsonl` illustrates the format and is not benchmark data.

