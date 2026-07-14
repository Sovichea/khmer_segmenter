# Khmer Segmenter

A deterministic, dictionary-based Khmer word segmenter for formal text,
technical documents, search indexing, and NLP preprocessing. It combines
Unicode normalization, frequency-weighted Viterbi decoding, linguistic rules,
and unknown-word recovery without a runtime machine-learning model.

[Try the live demo](https://sovichea.github.io/khmer_segment_webui_demo/) ·
[Documentation](docs/README.md) ·
[C port](port/c/README.md) ·
[Rust port](port/rust/README.md)

> [!IMPORTANT]
> This is a lexical segmenter, not a semantic parser. It is optimized for
> formal Khmer. Names, slang, new terminology, and mixed-language text may be
> returned as unknown spans for review.

## Highlights

- Deterministic output for the same text and data files
- Khmer Unicode normalization before segmentation
- Explainable dictionary and frequency-based decisions
- Unknown clusters are preserved instead of semantically guessed
- Python reference implementation plus high-performance C and Rust ports
- Optional lexical POS candidates and provenance metadata

## Quick start

Clone the repository and run Python from the project root:

```bash
git clone https://github.com/Sovichea/khmer_segmenter.git
cd khmer_segmenter
python scripts/test_viterbi.py
```

The core Python segmenter uses the standard library. Install the development
requirements only when running comparison and performance tools:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Python usage

```python
from pathlib import Path

from khmer_segmenter import KhmerSegmenter

data_dir = Path("khmer_segmenter/dictionary_data")
segmenter = KhmerSegmenter(
    data_dir / "khmer_dictionary_words.txt",
    data_dir / "khmer_word_frequencies.json",
)

tokens = segmenter.segment("ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល")
print(tokens)
# ['ក្រុមហ៊ុន', 'ទទួល', 'បាន', 'ប្រាក់ចំណូល']
```

For offsets, dictionary source, frequency, and lexical POS candidates:

```python
items = segmenter.segment_with_metadata("ខ្ញុំសរសេរឯកសារ")

for item in items:
    print(item["text"], item["start"], item["end"], item["known"])
```

`pos_candidates` are lexical possibilities, not contextual POS predictions.
Ambiguous and unknown tokens have `pos: None`.

## Process a file

```bash
python -m khmer_segmenter --input path/to/input.txt
```

Run the file benchmark with:

```bash
python -m khmer_segmenter \
  --benchmark \
  --input path/to/input.txt \
  --threads 4
```

## Choose an implementation

| Implementation | Best for | Documentation |
|:---|:---|:---|
| Python | Research, scripting, debugging, and reference behavior | This README |
| C | Embedding, low latency, cross-compilation, and constrained systems | [C guide](port/c/README.md) |
| Rust | Native applications with Rust safety and concurrency | [Rust guide](port/rust/README.md) |
| New language | Reproducing normalization, binary formats, and Viterbi behavior | [Porting guide](port/README.md) |

All implementations use synchronized linguistic resources from `port/common/`
or `khmer_segmenter/dictionary_data/`.

## Data policy

Source corpora are not distributed by this repository. Download them from the
credited original authors, review their terms, and store local copies under
the ignored `dataset/` directory. Those files remain available for local
testing without being added to Git.

The repository's MIT license covers project code; it does not relicense
third-party datasets or derived linguistic resources. See
[Data sources, attribution, and provenance](docs/DATA.md) before rebuilding or
redistributing data artifacts.

## Accuracy snapshot

The checked-in frequency model was evaluated on stable, held-out partitions:

| Dataset | Sentences | Boundary precision | Boundary recall | Boundary F1 |
|:---|---:|---:|---:|---:|
| khPOS test | 1,179 | 89.96% | 93.31% | **91.61%** |
| Khmer ALT POS test | 1,981 | 89.97% | 78.32% | **83.74%** |

Segmentation conventions differ between the corpora, so compare boundary F1
and inspect disagreements instead of treating every mismatch as a lexical
error. See [Evaluation](docs/EVALUATION.md) and
[Benchmarks](docs/BENCHMARKS.md) for methodology and commands.

## Documentation

- [Documentation index](docs/README.md)
- [Design philosophy](docs/DESIGN_PHILOSOPHY.md)
- [Data sources, attribution, and provenance](docs/DATA.md)
- [Evaluation guide](docs/EVALUATION.md)
- [Benchmark results](docs/BENCHMARKS.md)
- [Development and data-generation workflows](docs/DEVELOPMENT.md)
- [Porting guide and algorithm reference](port/README.md)
- [C port](port/c/README.md)
- [Rust port](port/rust/README.md)

## Acknowledgements

- [khmernltk](https://github.com/VietHoang1512/khmer-nltk), used for comparison
  benchmarks
- [sovichet](https://github.com/sovichet), credited for Khmer folktale and
  dictionary resources used in earlier local corpus work
- [phylypo](https://github.com/phylypo/segmentation-crf-khmer), author of the
  `kh_data_10000b` resource used in earlier frequency analysis
- The RAC/NCKL dictionary authority, dataset publishers, corpus creators, and
  annotators listed in [the data credits](docs/DATA.md)

## License

Project code is licensed under the [MIT License](LICENSE). Retain the copyright
and license notice in copies or substantial portions of the software.
