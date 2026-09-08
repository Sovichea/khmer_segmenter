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
| Author-curated signature vocabulary | Project-maintained list of important terms and names | Sovichea Tep | Explicitly identified project vocabulary; accepted for segmentation, spelling, and autocomplete without claiming RAC authority |
| Reviewed RAC phrase components | Reusable words occurring inside RAC headword phrases, corroborated by independent corpus use | Khmer Segmenter project review; RAC remains the underlying lexical source | Promoted as valid words with explicit derived provenance; reviewed source phrases may be excluded from one-token segmentation |
| Reviewed RAC definition/example vocabulary | Standalone vocabulary used semantically inside RAC definitions or examples but absent from RAC headwords | Khmer Segmenter project review; RAC remains the underlying evidence source | Manually reviewed for segmentation, spelling, and autocomplete; source typos, notation fragments, and negative examples are rejected |
| khPOS | [`ye-kyaw-thu/khPOS`](https://github.com/ye-kyaw-thu/khPOS) | Vichet Chea and Ye Kyaw Thu; annotation assistance by Sorn Kea and Leng Greyhuy | CC BY-NC-SA 4.0 |
| Khmer ALT | [Zenodo record 3937914](https://doi.org/10.5281/zenodo.3937914) | Chenchen Ding, Masao Utiyama, and Eiichiro Sumita; NICT and NIPTICT | Description and rights field differ; review the record |
| Earlier folktale/dictionary inputs | [sovichet](https://github.com/sovichet) | Sovichet | Ask the original author and review the source terms |
| `kh_data_10000b` | [`phylypo/segmentation-crf-khmer`](https://github.com/phylypo/segmentation-crf-khmer) | Phylypo Tum | Review the original repository |

Source metadata was last checked on 2026-08-01. Upstream publishers may update
files or terms; their current pages are authoritative.

## Bundled runtime data

The installed package includes a layered segmentation model and a strictly
RAC-curated spelling vocabulary:

```text
src/khmer_segmenter/dictionary_data/
|-- khmer_dictionary_words.txt
|-- khmer_dictionary_official_2022_words.txt
|-- khmer_dictionary_author_curated_words.txt
|-- khmer_dictionary_rac_derived_words.txt
|-- khmer_dictionary_rac_usage_words.txt
|-- khmer_dictionary_rac_phrase_exclusions.txt
|-- khmer_dictionary_rac_derived_review.tsv
|-- khmer_dictionary_rac_usage_review.tsv
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_spellcheck_words.txt
|-- khmer_typo_corrections.tsv
|-- khmer_word_frequencies.json
|-- khmer_word_pos.json
`-- khmer_model_manifest.json
```

These are the only linguistic assets approved for inclusion in Python release
archives. Users may override them with `--data-dir`, `data_dir=`, or
`KHMER_SEGMENTER_DATA_DIR`.

`khmer_dictionary_author_curated_words.txt` is intentionally separate from the
RAC list. Its entries are built into the default Python and Rust language packs
as valid segmentation, spelling, and autocomplete forms, while KDIC provenance
identifies them as author-curated project vocabulary.

The RAC-derived review avoids equating every substring with a word. Candidates
must occur inside a RAC headword expression, appear independently in corpus
evidence, and pass a review of the RAC definition and examples as reusable Khmer
vocabulary. The accompanying review TSV retains both approved and rejected
candidates and records the source expression, part of speech, corpus count,
definition assessment, decision, and rationale. Phrase exclusions remain valid
for whole-text spelling checks but cannot force Viterbi to emit the entire
expression as a single word.

RAC also uses useful vocabulary in definitions and examples without always
providing a corresponding headword. The project mines these occurrences into a
review queue, then promotes only forms whose surrounding entry establishes a
standalone meaning. This layer includes common words, names, borrowed terms,
scientific vocabulary, and learned Pali/Sanskrit forms. It does not treat RAC
prose as automatically correct: conflicting forms such as `ទូរស័ព្ទ` are
rejected when RAC's explicit headword is `ទូរសព្ទ`.

Rebuild the local review queue with:

```bash
python scripts/mine_rac_definition_words.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv
```

The generated JSONL and TSV under `build/rac_definition_review/` are candidates,
not trusted runtime data. A reviewer must verify meaning and spelling before
adding a form to `khmer_dictionary_rac_usage_words.txt`; every decision is
recorded in `khmer_dictionary_rac_usage_review.tsv`.

The 2026-09-08 mining run scanned all 44,752 source records. It found 11,481
raw candidates, of which 8,006 occurred in at least two RAC records. Those
figures are deliberately not described as new words: most candidates are
fragments, grammatical notation, parts of phrases, or spellings that conflict
with an explicit headword. The first semantic review promoted 32 forms and
recorded 8 representative rejections. Later batches can continue from the
local queue without weakening the default lexical policy.

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
all generated files and KDIC conversion.

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
|-- khmer_dictionary_author_curated_words.txt
|-- khmer_dictionary_rac_derived_words.txt
|-- khmer_dictionary_rac_usage_words.txt
|-- khmer_dictionary_rac_phrase_exclusions.txt
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_spellcheck_words.txt
|-- khmer_typo_corrections.tsv
|-- khmer_word_frequencies.json
|-- khmer_word_pos.json
`-- khmer_model_manifest.json

khmer_segmenter/dictionary_data/
|-- khmer_dictionary_words.txt
|-- khmer_dictionary_official_2022_words.txt
|-- khmer_dictionary_supplemental_words.txt
|-- khmer_word_frequencies.json
`-- khmer_word_pos.json

port/common/
|-- khmer_dictionary.kdict
`-- khmer_frequencies.bin

port/rust/data/
|-- khmer_dictionary.klex.json
`-- khmer_dictionary.kdict
```

Only approved files under `src/khmer_segmenter/dictionary_data/` are tracked
and packaged with Python. The generated KLEX/KDICT pair under `port/rust/data/`
is tracked with the Rust port so native and WASM developers receive the same
reviewed lexical model. The old `khmer_segmenter/dictionary_data/` location
remains an ignored development directory for rebuilding and comparing local
artifacts.

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
