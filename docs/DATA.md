# Data Sources, Attribution, and Provenance

This document separates project code from third-party corpora and linguistic
resources. Always review the upstream terms before downloading, rebuilding, or
redistributing an artifact.

## Repository policy

Source corpora are not tracked in Git. Keep local test and training files under
`dataset/`, which is ignored by the repository. Removing a file from the
current Git tree does not remove it from older Git history.

The MIT license applies to project code only. It does not relicense upstream
datasets or data derived from them.

## Sources and credits

| Resource | Original source | Credit | Upstream terms |
|:---|:---|:---|:---|
| RAC/NCKL Khmer Dictionary 2022 | [Seanghay Hay's `khmer-dictionary-44k` extraction](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k) | National Council of Khmer Language, Royal Academy of Cambodia (dictionary authority); Seanghay Hay / `seanghay` (extraction and publication) | Dataset card states research only and not for commercial use |
| khPOS | [`ye-kyaw-thu/khPOS`](https://github.com/ye-kyaw-thu/khPOS) | Vichet Chea and Ye Kyaw Thu; annotation assistance acknowledged to Sorn Kea and Leng Greyhuy | CC BY-NC-SA 4.0 |
| Khmer ALT | [Zenodo record 3937914](https://doi.org/10.5281/zenodo.3937914) | Chenchen Ding, Masao Utiyama, and Eiichiro Sumita; developed by NICT and NIPTICT | Description states CC BY-NC-SA 4.0, while the Zenodo rights field displays CC BY 4.0; review the record |
| Earlier folktale and dictionary inputs | [sovichet](https://github.com/sovichet) | Sovichet | Obtain from the original author and review its terms |
| `kh_data_10000b` | [`phylypo/segmentation-crf-khmer`](https://github.com/phylypo/segmentation-crf-khmer) | Phylypo Tum | Obtain from the original repository and review its terms |

Source metadata was checked on 2026-07-01.

## Local data layout

Create local paths as needed; Git will ignore the entire directory:

```text
dataset/
├── benchmarks/          # downloaded evaluation archives and extracted files
├── my_corpus.txt        # a user-provided corpus
└── other-local-data/    # any additional licensed local resources
```

The khPOS and Khmer ALT evaluation loaders download their official source files
to `dataset/benchmarks/` when a local path is not supplied.

## Runtime artifacts

Files under `khmer_segmenter/dictionary_data/` serve different purposes:

| File | Purpose |
|:---|:---|
| `khmer_dictionary_words.txt` | Runtime union of official and supplemental vocabulary |
| `khmer_dictionary_official_2022_words.txt` | Normalized RAC/NCKL 2022 headwords |
| `khmer_dictionary_supplemental_words.txt` | Community vocabulary outside the reference extraction |
| `khmer_word_frequencies.json` | Combined runtime occurrence frequencies |
| `khmer_word_frequencies_corpus.json` | Corpus-only frequency baseline |
| `khmer_word_pos.json` | Deterministic lexical POS candidates |
| `*_provenance.json` | Source, method, split, and count metadata |

## Rebuild the dictionary

Download `pairs.tsv` from the credited extraction and run:

```bash
python scripts/sync_rac_dictionary.py \
  --rac-tsv dataset/benchmarks/rac_dictionary_2022_pairs.tsv
```

The synchronization process normalizes headwords, rejects entries containing
whitespace, keeps supplemental vocabulary separate, and writes source counts to
`khmer_dictionary_provenance.json`.

## Rebuild derived gold artifacts

Only derived training partitions may contribute to runtime frequencies or POS
candidates. Development and test partitions are reserved for evaluation.

```bash
python scripts/augment_frequencies_from_gold.py
python scripts/build_lexical_pos.py
```

The corresponding provenance JSON files record dataset links, credits, split
policy, and counts so regeneration does not remove attribution.
