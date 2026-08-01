# Evaluation Guide

Evaluation uses Unicode code-point boundary offsets. This avoids inflating
scores through character overlap and makes disagreements inspectable at exact
token boundaries.

## Authoritative release benchmark

The release gate is a project-owned, redistribution-cleared benchmark of 300
human-reviewed sentences: 200 development and 100 frozen test sentences. Its
schema, category targets, and review rules are in
[`benchmarks/curated/`](../benchmarks/curated/README.md).

```bash
python scripts/evaluate_segmentation.py \
  --dataset curated \
  --dataset-path benchmarks/curated/benchmark.jsonl \
  --split dev \
  --output results/curated-dev.json
```

The benchmark is still being curated. Until all 300 records are approved, a
0.2 build is a release candidate and must not be promoted based on legacy
corpora alone.

## Legacy compatibility datasets

- [khPOS](https://github.com/ye-kyaw-thu/khPOS): manually segmented and POS
  tagged Khmer text from several formal domains
- [Khmer ALT](https://doi.org/10.5281/zenodo.3937914): translated Wikinews with
  a finer annotation convention

khPOS and Khmer ALT are not current, thoroughly curated gold standards for this
project. They remain useful for regression diagnosis and comparison with prior
work, but they do not decide whether the RAC migration is correct.

Read [the data policy and credits](DATA.md) before downloading either dataset.

## Stable legacy splits

Each upstream release provides a single source split. The loader derives stable
80/10/10 train, development, and test partitions from SHA-256 sentence-ID
buckets.

- Use `train` only when deriving frequencies or lexical POS candidates.
- Use `dev` while tuning behavior.
- Report final accuracy on `test`.

## Evaluate khPOS

```bash
python scripts/evaluate_segmentation.py \
  --dataset khpos \
  --split test \
  --output results/khpos_eval.json
```

Use `--dataset-path PATH` for an existing `train.all2` file or `--limit 100`
for a smoke test.

## Evaluate Khmer ALT

```bash
python scripts/evaluate_segmentation.py \
  --dataset khmer_alt_pos \
  --split test \
  --output results/khmer_alt_pos_eval.json
```

Without `--dataset-path`, the evaluator caches official downloads under the
ignored `dataset/benchmarks/` directory.

## Reported metrics

- Boundary precision: predicted boundaries that occur in the gold tokens
- Boundary recall: gold boundaries recovered by the segmenter
- Boundary F1: harmonic mean of boundary precision and recall
- Exact sentence match: sentences with no boundary disagreement
- Unknown-token rate: predicted tokens absent from the runtime dictionary
- Latency: segmentation execution time

Typo recovery should additionally report whole-error-span exact-match recall,
top-1 correction accuracy, top-k correction recall, false-positive rate on
valid words, and diagnostic latency. Segmentation boundary F1 alone cannot
detect the editor failure where only an internal unknown fragment is
underlined.

Run the deterministic missing-dependent-vowel smoke benchmark with:

```bash
python scripts/evaluate_typo_recovery.py --limit 200 \
  --output results/typo-recovery.json
```

This mutation benchmark is useful for regressions but is not a replacement for
human-reviewed spelling errors in real sentence context.

The small sourced review set under [`benchmarks/typos/`](../benchmarks/typos/README.md)
checks examples observed in public Khmer text without redistributing complete
posts or personal identifiers:

```bash
python scripts/evaluate_real_world_typos.py
```

Treat its results as edge-case regression evidence, not as a population-level
accuracy claim. Records that require context are counted separately because a
dictionary-only checker cannot safely resolve valid-word confusions.

On the curated benchmark, boundary F1 is the primary comparison metric. Exact sentence match is
intentionally strict, and different valid compound conventions can reduce it.

The stable gate requires the candidate to beat 0.1.1 overall boundary F1,
without lowering exact sentence match. Any category F1 regression greater than
two percentage points requires explicit review. Runtime and peak-memory
regressions greater than 15% also block promotion pending investigation.

## Inspect errors

The JSON report includes missing and extra boundaries for each disagreement.
Unknown output is a review category: it can represent a name, loanword, new
technical term, typo, or missing dictionary entry.

For corpus-level unknown-word context:

```bash
python scripts/test_viterbi.py \
  --source path/to/your/local_corpus.txt \
  --limit 500

python scripts/find_unknown_words.py \
  --input output/segmentation_results.txt
```

See [Benchmark Results](BENCHMARKS.md) for documented historical measurements.
