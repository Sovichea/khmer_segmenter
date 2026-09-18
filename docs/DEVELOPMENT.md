# Development Workflows

This guide covers repository tests and regeneration tasks. Source corpora must
be obtained separately and stored under the ignored `dataset/` directory.

## Fetch upstream sources

The packaged runtime model works on a fresh clone, but rebuild and validation
tools need the upstream RAC source table, which is not stored in Git. Download
the pinned, checksum-verified revision with:

```bash
python scripts/fetch_sources.py
```

Files are written under the ignored `dataset/` directory. Pass `--force` to
refetch or `--output-dir PATH` to place them elsewhere.

## Reproduce the benchmark

The curated benchmark split is tracked in the repository and runs against the
bundled model, so no download is required:

```bash
python -m pytest tests/test_curated_release_benchmark.py -q
python scripts/evaluate_segmentation.py \
  --dataset curated \
  --dataset-path benchmarks/curated/benchmark.jsonl
```

Tools that rebuild the model from source additionally require
`python scripts/fetch_sources.py` first.

## Run tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -q
python scripts/test_viterbi.py
```

Install development and release tools with `python -m pip install -e .[dev]`.

Batch-process a local corpus with:

```bash
python scripts/test_viterbi.py \
  --source path/to/your/local_corpus.txt \
  --limit 500
```

## Rebuild frequencies and native data

The consolidated pipeline normalizes input, iteratively segments the corpus,
updates occurrence frequencies, and compiles shared native artifacts.

```bash
python scripts/prepare_data.py \
  --corpus dataset/my_corpus.txt \
  --dict src/khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
```

Generated native files include the following local, Git-ignored artifacts:

- `port/common/khmer_dictionary.kdict`: baked lookup table
- `port/common/khmer_frequencies.bin`: binary frequency data

Pin input datasets and artifacts when reproducible output matters.

## Incrementally add dictionary words

After reviewing a candidate, add it to the supplemental source. Do not copy a
long phrase directly into the runtime list; rebuild conservative chunks and
inspect the audit first:

```bash
python scripts/prepare_supplemental_lexicon.py path/to/reviewed_words.txt \
  --audit build/supplemental_audit.tsv
```

Then update experimental frequencies when appropriate:

```bash
python scripts/incremental_update.py \
  --dict src/khmer_segmenter/dictionary_data/khmer_dictionary_words.txt \
  --freq src/khmer_segmenter/dictionary_data/khmer_word_frequencies.json \
  --unknown-freq src/khmer_segmenter/dictionary_data/unknown_word_frequencies.json
```

The script uses observed unknown counts, derives a compound estimate when
possible, and otherwise assigns the configured frequency floor.

## Review unknown words

```bash
python scripts/find_unknown_words.py \
  --input output/segmentation_results.txt
```

Review context before adding an entry. Unknown output can be valid terminology,
a proper name, a foreign span, or malformed input.

## Rebuild lexical POS candidates

```bash
python scripts/build_lexical_pos.py
```

This uses the derived khPOS training partition only. It does not build a
contextual POS tagger.

## Dictionary synchronization

Follow [Data Sources, Attribution, and Provenance](DATA.md) to obtain the source
TSV and synchronize the official and supplemental word lists.

For the complete workflow from the upstream TSV through `KDIC` files
used by embedded C and Rust applications, see
[Prepare Dictionaries for Python, C, and Rust](EMBEDDED_DICTIONARY.md).

## Word-break opportunities

Python, Rust, and WASM expose safe word-boundary offsets for layout engines.
They are derived directly from segmentation and require no second dictionary.
The Python reference also offers breaks inside a long word that decomposes into
smaller accepted words, but never next to a bare consonant or a single-cluster
syllable. See [Safe word breaks](WORD_BREAKS.md).

## Shared behavior changes

Changes to normalization, character clustering, Viterbi costs, post-processing,
or binary formats can affect every port. Update and test the Python reference,
the [porting guide](../port/README.md), and native implementations together.

## Build the Python package

```bash
python -m build
python -m twine check dist/*
python scripts/check_distribution.py dist/*
```

Follow the [PyPI Release Guide](PYPI_RELEASE.md) for clean-environment and
TestPyPI verification.
