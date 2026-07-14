# Data Sources, Downloads, and Attribution

This repository distributes algorithms and generation tools, not third-party
linguistic data. Downloaded sources and every generated dictionary, frequency,
POS, provenance-count, and native binary artifact remain local and ignored.

The project MIT license covers code only. It does not relicense upstream data
or derived artifacts.

## Sources and credits

| Resource | Original source | Credit | Terms to review |
|:---|:---|:---|:---|
| Khmer Dictionary 2022 extraction | [Seanghay Hay's `khmer-dictionary-44k`](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k) | National Council of Khmer Language, Royal Academy of Cambodia (authority); Seanghay Hay / `seanghay` (extraction and publication) | Dataset card says research purpose only |
| khPOS | [`ye-kyaw-thu/khPOS`](https://github.com/ye-kyaw-thu/khPOS) | Vichet Chea and Ye Kyaw Thu; annotation assistance by Sorn Kea and Leng Greyhuy | CC BY-NC-SA 4.0 |
| Khmer ALT | [Zenodo record 3937914](https://doi.org/10.5281/zenodo.3937914) | Chenchen Ding, Masao Utiyama, and Eiichiro Sumita; NICT and NIPTICT | Description and rights field differ; review the record |
| Earlier folktale/dictionary inputs | [sovichet](https://github.com/sovichet) | Sovichet | Ask the original author and review the source terms |
| `kh_data_10000b` | [`phylypo/segmentation-crf-khmer`](https://github.com/phylypo/segmentation-crf-khmer) | Phylypo Tum | Review the original repository |

Source metadata was last checked on 2026-07-14. Upstream publishers may update
files or terms; their current pages are authoritative.

## Download the dictionary

From the repository root on Linux or macOS:

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

This downloads directly from the credited publisher; the project does not
mirror the file. Then normalize and generate the local runtime dictionary:

```bash
khmer-segment data prepare \
  --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

From a source checkout, this wrapper additionally prepares the native text
dictionary location:

```bash
python scripts/sync_rac_dictionary.py \
  --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

See [Prepare Dictionaries for Python, C, and Rust](EMBEDDED_DICTIONARY.md) for
all generated files and KDIC/KHYP conversion.

## Optional evaluation corpora

Evaluation helpers download official archives into the ignored
`dataset/benchmarks/` cache when a local path is not provided. They never place
the corpora inside the Python package.

Run evaluation after reviewing each upstream license:

```bash
python scripts/evaluate_segmentation.py --dataset khpos
python scripts/evaluate_segmentation.py --dataset khmer_alt_pos
```

Use `python scripts/evaluate_segmentation.py --help` for explicit local-source
options and current dataset identifiers.

## Local layout

```text
dataset/
|-- rac_dictionary_2022_pairs.tsv
|-- benchmarks/
|-- my_corpus.txt
`-- other-local-data/

khmer_segmenter/dictionary_data/
|-- khmer_dictionary_words.txt
|-- khmer_dictionary_official_2022_words.txt
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_word_frequencies.json
|-- khmer_word_pos.json
`-- khmer_dictionary_hyphenation_pairs.txt

port/common/
|-- khmer_dictionary.kdict
|-- khmer_frequencies.bin
`-- khmer_hyphenation.kdict
```

All paths above are ignored by Git. The old `khmer_segmenter/dictionary_data/`
location remains a development data directory; importable package code now
lives under `src/khmer_segmenter/` and cannot accidentally package that data.

## Generate optional local frequencies and POS candidates

Generate frequencies from a corpus you are authorized to use:

```bash
python scripts/prepare_data.py \
  --corpus dataset/my_corpus.txt \
  --dict khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
```

The segmenter works without a frequency JSON by applying default dictionary
costs, although segmentation quality may differ.

The following research commands use training partitions from separately
licensed corpora and produce local, ignored files:

```bash
python scripts/augment_frequencies_from_gold.py
python scripts/build_lexical_pos.py
```

They do not create a contextual POS model. Do not redistribute their outputs
unless the upstream terms and intended use permit it.

## History and release safety

Removing a file from the current Git tree does not erase it from older commits.
Before making a public release, decide whether repository history must be
rewritten. Every wheel and source distribution must also be inspected to prove
that local data is absent; see [PyPI Release Guide](PYPI_RELEASE.md).
