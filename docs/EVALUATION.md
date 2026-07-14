# Evaluation Guide

Evaluation uses Unicode code-point boundary offsets. This avoids inflating
scores through character overlap and makes disagreements inspectable at exact
token boundaries.

## Supported gold datasets

- [khPOS](https://github.com/ye-kyaw-thu/khPOS): manually segmented and POS
  tagged Khmer text from several formal domains
- [Khmer ALT](https://doi.org/10.5281/zenodo.3937914): translated Wikinews with
  a finer annotation convention

Read [the data policy and credits](DATA.md) before downloading either dataset.

## Stable splits

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

Boundary F1 is the primary comparison metric. Exact sentence match is
intentionally strict, and different valid compound conventions can reduce it.

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
