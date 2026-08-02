# Data Sources, Downloads, and Attribution

This repository distributes attributed runtime linguistic files so the
segmenter works immediately after installation. Their noncommercial and
attribution terms are recorded in [`DATA_LICENSE.md`](../DATA_LICENSE.md).
Source downloads, evaluation corpora, backups, provenance payloads,
intermediate files, and native build artifacts remain local and ignored.

The project MIT license covers code only. It does not relicense the bundled
dictionary or its runtime adaptations.

## Sources and credits

| Resource | Original source | Credit | Terms to review |
|:---|:---|:---|:---|
| Khmer Dictionary 2022 extraction | [Seanghay Hay's `khmer-dictionary-44k`](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k) | National Council of Khmer Language, Royal Academy of Cambodia (authority); Seanghay Hay / `seanghay` (extraction and publication) | Noncommercial redistribution with attribution, confirmed by Seanghay Hay |
| Legacy supplemental segmentation forms | Earlier attributed runtime dictionary in this project, conservatively decomposed during migration | Sovichea and project maintainers (runtime curation); retain the Khmer Dictionary 2022 credits above | Segmentation evidence only; distributed under the same noncommercial attribution notice |
| khPOS | [`ye-kyaw-thu/khPOS`](https://github.com/ye-kyaw-thu/khPOS) | Vichet Chea and Ye Kyaw Thu; annotation assistance by Sorn Kea and Leng Greyhuy | CC BY-NC-SA 4.0 |
| Khmer ALT | [Zenodo record 3937914](https://doi.org/10.5281/zenodo.3937914) | Chenchen Ding, Masao Utiyama, and Eiichiro Sumita; NICT and NIPTICT | Description and rights field differ; review the record |
| Earlier folktale/dictionary inputs | [sovichet](https://github.com/sovichet) | Sovichet | Ask the original author and review the source terms |
| `kh_data_10000b` | [`phylypo/segmentation-crf-khmer`](https://github.com/phylypo/segmentation-crf-khmer) | Phylypo Tum | Review the original repository |

Source metadata was last checked on 2026-08-01. Upstream publishers may update
files or terms; their current pages are authoritative.

## Bundled runtime data

The installed package includes a layered segmentation model, a strictly
RAC-curated spelling vocabulary, and the preserved experimental hyphenation
asset:

```text
src/khmer_segmenter/dictionary_data/
|-- khmer_dictionary_words.txt
|-- khmer_dictionary_official_2022_words.txt
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_spellcheck_words.txt
|-- khmer_typo_corrections.tsv
|-- khmer_word_frequencies.json
|-- khmer_word_pos.json
|-- khmer_dictionary_hyphenation_pairs.txt
`-- khmer_model_manifest.json
```

These are the only linguistic assets approved for inclusion in Python release
archives. Users may override them with `--data-dir`, `data_dir=`, or
`KHMER_SEGMENTER_DATA_DIR`.

## Download and rebuild the dictionary

From the repository root on Linux or macOS:

```bash
mkdir -p dataset
curl -L \
  "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/525c0171894465cba920a9181387a032c11610d3/RAC-Khmer-Dict-2022.csv?download=true" \
  -o dataset/RAC-Khmer-Dict-2022.csv
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force dataset | Out-Null
Invoke-WebRequest `
  -Uri "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/525c0171894465cba920a9181387a032c11610d3/RAC-Khmer-Dict-2022.csv?download=true" `
  -OutFile "dataset/RAC-Khmer-Dict-2022.csv"
```

This downloads directly from the credited publisher. Rebuild and validate the
authoritative RAC base model with:

```bash
python scripts/rebuild_rac_model.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv \
  --output-dir build/rac
python scripts/validate_findings.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv
```

The simpler `khmer-segment data prepare --rac-tsv PATH` command is retained for
custom dictionary overrides, not for reproducing the bundled strict model.

See [Prepare Dictionaries for Python, C, and Rust](EMBEDDED_DICTIONARY.md) for
all generated files and KDIC/KHYP conversion.

## Optional evaluation corpora

Evaluation helpers download official archives into the ignored
`dataset/benchmarks/` cache when a local path is not provided. They never place
the corpora inside the Python package.

Run evaluation after reviewing each upstream license:

```bash
python scripts/evaluate_segmentation.py --dataset khpos --split test
python scripts/evaluate_segmentation.py --dataset khmer_alt_pos --split test
```

Use `python scripts/evaluate_segmentation.py --help` for explicit local-source
options and current dataset identifiers.

## Development layout

```text
dataset/
|-- RAC-Khmer-Dict-2022.csv
|-- benchmarks/
|-- my_corpus.txt
`-- other-local-data/

src/khmer_segmenter/dictionary_data/
|-- khmer_dictionary_words.txt
|-- khmer_dictionary_official_2022_words.txt
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_spellcheck_words.txt
|-- khmer_typo_corrections.tsv
|-- khmer_word_frequencies.json
|-- khmer_word_pos.json
|-- khmer_dictionary_hyphenation_pairs.txt
`-- khmer_model_manifest.json

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

Only approved files under `src/khmer_segmenter/dictionary_data/` are tracked
and packaged. The old `khmer_segmenter/dictionary_data/` location remains an
ignored development directory for rebuilding and comparing local artifacts.

## Optional research frequencies and POS candidates

The curated spelling vocabulary and frequency model do not use external
corpora for lexical validity or frequency evidence. The supplemental file is
segmentation-only and cannot make a spelling valid. Researchers may still
generate local experimental frequencies from a corpus they are authorized to
use:

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
that only approved attributed runtime data is present; see
[PyPI Release Guide](PYPI_RELEASE.md).
