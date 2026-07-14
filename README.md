# Khmer Segmenter

A deterministic, dictionary-based Khmer word segmenter for NLP preprocessing,
search, formal documents, and embedded applications. It combines Khmer Unicode
normalization, frequency-weighted Viterbi decoding, linguistic rules, and
unknown-word recovery without a runtime machine-learning model.

[Documentation](docs/README.md) ·
[Data preparation](docs/EMBEDDED_DICTIONARY.md) ·
[C port](port/c/README.md) ·
[Rust port](port/rust/README.md) ·
[Live demo](https://sovichea.github.io/khmer_segment_webui_demo/)

> [!IMPORTANT]
> Linguistic data is not included in this repository or in Python packages.
> Each developer downloads the original source, reviews its terms, and builds
> local runtime files. Project code is MIT licensed; external data keeps its
> own upstream terms.

## Features

- Deterministic segmentation for the same code and local data
- Khmer Unicode normalization
- Frequency-weighted dictionary decisions
- Unknown-span preservation
- Typed token metadata with offsets and lexical POS candidates
- Optional locally generated hyphenation
- Python API and `khmer-segment` CLI
- Shared KDIC/KHYP formats for C and Rust applications

This is a lexical segmenter, not a semantic parser or contextual POS tagger.
`pos_candidates` are possibilities found in optional local lexical data.

## Install for development

Python 3.10 or newer is required.

```bash
git clone https://github.com/Sovichea/khmer_segmenter.git
cd khmer_segmenter
python -m venv .venv
```

Activate the environment and install the src-layout package:

```bash
# Linux/macOS
source .venv/bin/activate
python -m pip install -e .
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

After its first release, the distribution will install with:

```bash
pip install khmer-viterbi-segmenter
```

The import package remains `khmer_segmenter`.

## Prepare the dictionary

The original dictionary is published by Seanghay Hay (`seanghay`) on Hugging
Face and was extracted from the Khmer Dictionary 2022 of the National Council
of Khmer Language, Royal Academy of Cambodia:

<https://huggingface.co/datasets/seanghay/khmer-dictionary-44k>

The dataset card says it is for research purposes only. Review those terms
before downloading or using it.

Create the ignored local dataset directory and download `pairs.tsv` directly
from the original publisher:

```bash
mkdir -p dataset
curl -L \
  "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/main/pairs.tsv?download=true" \
  -o dataset/rac_dictionary_2022_pairs.tsv
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force dataset | Out-Null
Invoke-WebRequest `
  -Uri "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/main/pairs.tsv?download=true" `
  -OutFile "dataset/rac_dictionary_2022_pairs.tsv"
```

Generate the ignored local runtime dictionary:

```bash
khmer-segment data prepare \
  --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

When working from a repository clone, the wrapper below also copies the local
text dictionary to `port/common/` for native development:

```bash
python scripts/sync_rac_dictionary.py \
  --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

The Python resolver checks these locations in order:

1. `data_dir=` or CLI `--data-dir`
2. `KHMER_SEGMENTER_DATA_DIR`
3. The user data directory for the operating system
4. `khmer_segmenter/dictionary_data/` in a development checkout

Check the resolved files:

```bash
khmer-segment data status
khmer-segment data sources
khmer-segment data prepare --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

See [Prepare Dictionaries for Python, C, and Rust](docs/EMBEDDED_DICTIONARY.md)
for frequency generation and KDIC/KHYP compilation.

## Python API

```python
from khmer_segmenter import KhmerSegmenter, prepare_dictionary

prepare_dictionary(
    "dataset/rac_dictionary_2022_pairs.tsv",
    "khmer_segmenter/dictionary_data",
)

segmenter = KhmerSegmenter.from_data_dir(
    "khmer_segmenter/dictionary_data"
)

tokens = segmenter.segment("ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា")
print(tokens)
```

If `KHMER_SEGMENTER_DATA_DIR` is configured, the constructor needs no paths:

```python
segmenter = KhmerSegmenter()
```

Typed analysis results include normalized offsets and optional lexical data:

```python
for token in segmenter.analyze("ខ្ញុំសរសេរឯកសារ"):
    print(token.text, token.start, token.end, token.known)
    print(token.frequency, token.pos_candidates)
```

The legacy dictionary result remains available as
`segment_with_metadata(text)`.

Optional hyphenation uses locally generated pairs:

```python
from khmer_segmenter import KhmerHyphenator

hyphenator = KhmerHyphenator.from_data_dir(
    "khmer_segmenter/dictionary_data"
)
result = hyphenator.hyphenate(
    "សហប្រតិបត្តិការ",
    segmenter=segmenter,
    separator="-",  # use "\u200b" for invisible break opportunities
)
```

## CLI

Segment positional text, a file, or standard input:

```bash
khmer-segment segment "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"
khmer-segment segment --input input.txt --output segmented.txt
cat input.txt | khmer-segment segment
```

Machine-readable output:

```bash
khmer-segment segment "ខ្ញុំសរសេរឯកសារ" --format json
khmer-segment analyze "ខ្ញុំសរសេរឯកសារ" --format json
```

`analyze` reports lexical candidates; it does not claim contextual POS tagging.

Hyphenation and benchmarking:

```bash
khmer-segment hyphenate "សហប្រតិបត្តិការ" --visible-hyphen
khmer-segment benchmark --input dataset/my_corpus.txt --limit 1000
```

Use a non-default local data directory with the global option before the
subcommand:

```bash
khmer-segment --data-dir /path/to/local/data segment "អត្ថបទខ្មែរ"
```

## Build the Python distribution

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

The wheel contains Python code and `rules.json` only. Tests should always
inspect the archive before publishing to confirm that no local linguistic data
was included.

## Documentation

- [Documentation index](docs/README.md)
- [Data sources, attribution, and provenance](docs/DATA.md)
- [Dictionary and embedded-data preparation](docs/EMBEDDED_DICTIONARY.md)
- [Development workflows](docs/DEVELOPMENT.md)
- [Evaluation](docs/EVALUATION.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Algorithm and porting reference](port/README.md)

## Data policy

Downloaded corpora, dictionaries, frequency tables, POS tables, provenance
payloads containing derived counts, and native dictionary binaries are ignored
and must remain local. The repository provides source links, credit, schemas,
and reproducible generation tools instead of redistributing those artifacts.

Removing files from the current Git tree does not remove copies from old Git
history. See [the data policy](docs/DATA.md) before publishing or rewriting
repository history.

## License and acknowledgements

Project code is licensed under the [MIT License](LICENSE). That license does not
apply to third-party linguistic data.

Original data authors, authorities, corpus creators, and annotators are listed
in [Data Sources, Attribution, and Provenance](docs/DATA.md).
