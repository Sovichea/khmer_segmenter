# Prepare Dictionaries for Python, C, and Rust

Dictionary source files and generated binary dictionaries are deliberately not
redistributed by this repository. The commands below create local, Git-ignored
artifacts for testing or deployment. Run all commands from the repository root
unless a step says otherwise.

## 1. Obtain the original dictionary

Download `pairs.tsv` from
[Seanghay Hay's `khmer-dictionary-44k` publication on Hugging Face](https://huggingface.co/datasets/seanghay/khmer-dictionary-44k)
and save it locally, for example as:

```text
dataset/rac_dictionary_2022_pairs.tsv
```

Direct download commands for Linux, macOS, and Windows are provided in
[Data Sources, Downloads, and Attribution](DATA.md#download-the-dictionary).

Review the upstream research-only/non-commercial terms before using the data.
Credit the National Council of Khmer Language, Royal Academy of Cambodia as
the dictionary authority and Seanghay Hay (`seanghay`) for the extraction and
publication. Do not commit the downloaded or generated files.

## 2. Build the local text dictionary

```bash
python scripts/sync_rac_dictionary.py \
  --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

On PowerShell, the same command can be written on one line:

```powershell
python scripts/sync_rac_dictionary.py --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

This creates:

```text
khmer_segmenter/dictionary_data/khmer_dictionary_official_2022_words.txt
khmer_segmenter/dictionary_data/khmer_dictionary_supplemental_words.txt
khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
port/common/khmer_dictionary_words.txt
```

The authoritative base is `khmer_dictionary_words.txt`, a normalized UTF-8 file
with one word per line. If a local supplemental file already exists, the sync
step decomposes phrase-like entries into conservative chunks and records an
audit. Python loads the two layers separately so supplemental entries receive a
penalty and remain invalid for spelling.

Verify Python segmentation before compiling native data:

```bash
python scripts/test_viterbi.py "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"
```

## 3. Convert the dictionary to KDIC

Both native implementations read the same `KDIC` version 1 format. It contains
the normalized words, generated spelling variants, and frequency-derived word
costs in an open-addressed lookup table.

If a suitable local frequency JSON already exists, compile directly:

```bash
python scripts/build_dictionary_kdict.py
```

Explicit paths are also supported:

```bash
python scripts/build_dictionary_kdict.py \
  --dict khmer_segmenter/dictionary_data/khmer_dictionary_words.txt \
  --supplemental khmer_segmenter/dictionary_data/khmer_dictionary_supplemental_words.txt \
  --spellcheck khmer_segmenter/dictionary_data/khmer_spellcheck_words.txt \
  --freq khmer_segmenter/dictionary_data/khmer_word_frequencies.json \
  --output port/common/khmer_dictionary.kdict
```

The output is:

```text
port/common/khmer_dictionary.kdict
```

The compiled file includes word costs and the supplemental penalty, so C and
Rust do not need a separate frequency file when loading
`khmer_dictionary.kdict`. Rust spelling and completion use the synchronized
curated spelling list, not every KDIC segmentation entry.

## 4. Rebuild frequencies from a local corpus

Use this path when the frequency JSON does not exist or should reflect a new
corpus. The iterative pipeline uses the C executable, so build it first.

```bash
cd port/c
zig build release
cd ../..
```

Then run the complete pipeline with one or more locally obtained corpora:

```bash
python scripts/prepare_data.py \
  --corpus dataset/my_corpus.txt \
  --dict khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
```

The pipeline normalizes the corpus, estimates frequencies iteratively, and
generates these local artifacts (dictionary-derived text and binaries are
ignored by Git):

```text
khmer_segmenter/dictionary_data/khmer_word_frequencies.json
port/common/khmer_frequencies.bin
port/common/khmer_dictionary.kdict
khmer_segmenter/dictionary_data/khmer_dictionary_hyphenation_pairs.txt
port/common/khmer_hyphenation.kdict
```

`khmer_frequencies.bin` is the legacy text-dictionary companion format. New
native deployments should normally use the single `khmer_dictionary.kdict`
file instead.

## 5. Build only the hyphenation dictionary

After the text dictionary and frequency JSON exist, run:

```bash
python generate_hyphenation_pairs.py
python build_hyphenation_kdict.py
```

This creates `port/common/khmer_hyphenation.kdict` in `KHYP` version 1 format.
It is optional unless the application exposes hyphenation.

## 6. Test the C artifact

Build the executable if necessary:

```bash
cd port/c
zig build release
cd ../..
```

From the repository root on Windows:

```powershell
.\port\c\zig-out\win\bin\khmer_segmenter.exe "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"
.\port\c\zig-out\win\bin\khmer_segmenter.exe --test-hyphenation "សហប្រតិបត្តិការ"
```

On Linux, use `port/c/zig-out/linux/bin/khmer_segmenter`. The development CLI
finds data in `port/common/`. An embedded C application can instead pass the
deployed `.kdict` path to `khmer_segmenter_init_ex`. The current C loader reads
KDIC from a file; memory-only firmware would require a separate byte-array
loader.

## 7. Test the Rust artifact

```bash
cd port/rust
cargo run --release -- "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"
cargo run --release -- --test-hyphenation "សហប្រតិបត្តិការ"
```

The Rust CLI finds both files in `../common/` when run from `port/rust`. Library
applications can load a deployed file with `KDict::load`. The lower-level Rust
KDIC reader also exposes `KDict::from_bytes` for integrations that package the
artifact as application bytes.

## 8. Deploy and verify

Copy only the locally generated files needed by the target application:

```text
khmer_dictionary.kdict       required for segmentation
khmer_hyphenation.kdict      optional for hyphenation
```

Treat these binaries as derived dictionary artifacts subject to the upstream
terms. Do not publish them in a wheel, crate, firmware image, release archive,
or application without confirming that the intended redistribution is allowed.
For reproducible private builds, record the source revision, build command, and
SHA-256 hashes alongside the artifacts.
