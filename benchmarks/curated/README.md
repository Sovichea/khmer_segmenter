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
for scoring only after `review.status` is `approved`. Version 0.2 uses Sovichea
as its primary reviewer; a second reviewer may be added in a future revision.

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

## Reviewing the 300 project-authored candidates

`review_300.tsv` contains the original 300 project-authored candidates and the
initial manually proposed boundaries. It is retained as the source worksheet,
not as gold data.

`review_300.model.tsv` records the current Khmer Segmenter baseline. Its
boundaries were produced by the runtime rather than by an LLM. Open it as UTF-8
with tab-separated columns:

- `source_text` is the immutable sentence without boundary spaces.
- `model_segmented_text` is the immutable Khmer Segmenter baseline.
- `segmented_text` initially copies the model output for downstream tooling.

In the two segmented columns, ordinary spaces represent word boundaries. This
file is an audit artifact, not the primary human boundary worksheet; reviewers
should use the focused contextual files described below.
`review_300.model.meta.json` records the package version and exact model-manifest
hash used to create the baseline.

The model-seeded sheet can be reproduced from the untouched source worksheet
with the command below. Do not run it over a sheet containing review work.

```bash
python scripts/seed_curated_review.py
```

The model boundaries must not be treated as gold boundaries until focused human
review is complete. Because the worksheet was seeded by the model under test,
this dataset is a regression suite rather than an independent accuracy claim.
The 100-record test split is frozen with the approved v0.2 benchmark.

## Contextual ambiguity review

Reviewers should not have to look up every token in the RAC dictionary or
invent complete sentence boundaries. Generate the focused review files with:

```bash
python scripts/build_curated_ambiguity_review.py
```

The command produces:

- `automatic_rac_segments.tsv`: one summary per sentence. No action is needed
  for an `automatically_resolved` sentence.
- `ambiguous_rac_review.tsv`: only spans for which the model choice and at least
  one alternative are composed entirely from RAC entries (or deterministic
  visual aliases of RAC entries).
- `unresolved_spans.tsv`: supplemental or unknown spans that cannot be treated
  as an RAC contextual ambiguity.
- `ambiguity_review.meta.json`: the exact model identity and extraction limits.

For a reader-friendly interface, generate and serve the local review page:

```bash
python scripts/build_curated_review_html.py
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/benchmarks/curated/review.html
```

The page shows one wrapped card at a time, supports arrow-key navigation and
number-key decisions, saves progress in browser storage, and exports the three
reviewed UTF-8 TSV files. Export regularly as a backup. Previously exported TSV
files can also be imported to resume work in another browser.

For each row in `ambiguous_rac_review.tsv`, read the complete `source_text`,
compare `model_choice` with `alternative_1`, `alternative_2`, and
`alternative_3`, and put one of these values in `reviewer_choice`:

```text
model
alternative_1
alternative_2
alternative_3
uncertain
```

Use only an alternative that is not `none`, then set `review_status` to
`approved`. The JSON columns preserve costs and RAC membership evidence for
auditing; they are not the linguistic answer.

For `unresolved_spans.tsv`, classify each item as `name`,
`valid_missing_term`, `common_variant`, `borrowed_term`, `numeric_notation`,
`typo`, or `noise`. A valid term or variant should be reviewed for the
appropriate lexical source rather than silently promoted from this benchmark.
Spaces may be added to `reviewed_segmented_text` when an unresolved span
contains more than one confirmed unit. Set `review_status` to `approved` after
classification. A sentence containing `typo` or `noise` must be corrected or
replaced before release compilation.

Finally, check sentence naturalness and spelling in
`automatic_rac_segments.tsv`, then set `sentence_review_status` to `approved`.
This is a sentence-quality decision, not an invitation to invent alternative
boundaries.

During review, compile a structurally valid draft with:

```bash
python scripts/compile_curated_ambiguity_review.py
```

After every contextual decision, unresolved classification, and sentence has
been approved, build the release-gating benchmark with:

```bash
python scripts/compile_curated_ambiguity_review.py \
  --output benchmarks/curated/benchmark.jsonl \
  --primary-reviewer "Sovichea" \
  --require-approved
```
