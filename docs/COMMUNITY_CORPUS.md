# Community Corpus Workflow

Community text is useful for discovering names, borrowed words, new terms, and
common variants that do not appear in RAC 2022. It is evidence, not spelling
authority.

The first corpus used by this workflow is
[`Panhapich/khmer-text-corpus`](https://huggingface.co/datasets/Panhapich/khmer-text-corpus),
pinned to revision `e42e1dd0d77836f1874ad14e83f4e291e5bb0a01`. Its dataset card
marks the license as `other` and says that inherited source licenses still need
confirmation. Keep the downloaded corpus and generated candidate cache local.

## Policy

- Remove U+200B ZERO WIDTH SPACE before analysis.
- Run Khmer Viterbi Segmenter on the raw text; do not treat the publisher's
  segmented file as gold annotation.
- Use the publisher's boundaries only as a second candidate-discovery signal.
- Reject partial fragments, malformed Unicode, OCR debris, numbers, and long
  phrases.
- Admit only reviewed lexical units, with a category such as `name`,
  `borrowed_word`, `pali_word`, `new_term`, or `common_variant`.
- Give admitted entries only `segmentation` and `supplemental` KLEX uses.
  Corpus frequency may rank segmentation candidates but cannot make a spelling
  valid or place it in autocomplete.
- Strict mode continues to use RAC, reviewed official lexicons, and user packs.
  The community pack is loaded only in inclusive mode.

This separation allows a frequent form to remain intact for analysis without
declaring that it is the spelling users should write.

## Reproduce candidate mining

Download these two files into an ignored local directory:

```text
dataset/community/Panhapich-khmer-text-corpus/all_text.txt
dataset/community/Panhapich-khmer-text-corpus/all_text_segmented.txt
```

The pinned raw file must have SHA-256:

```text
95cca2f8542f40596c69e5b08f6ec579ff7f01caa4f713db2d15681884b4ddce
```

Build the streaming Rust miner and scan the raw corpus with a KDIC containing
RAC plus the locally available reviewed official lexicons:

```bash
cargo build --release --manifest-path port/rust/Cargo.toml \
  --bin mine_community_words

port/rust/target/release/mine_community_words \
  --raw dataset/community/Panhapich-khmer-text-corpus/all_text.txt \
  --dictionary build/analysis.kdict \
  --output build/raw_candidates.jsonl \
  --frequency-output build/known_frequencies.json
```

Merge the publisher's proposed boundaries without rerunning the expensive
segmentation pass:

```bash
port/rust/target/release/mine_community_words \
  --raw dataset/community/Panhapich-khmer-text-corpus/all_text.txt \
  --segmented dataset/community/Panhapich-khmer-text-corpus/all_text_segmented.txt \
  --dictionary build/analysis.kdict \
  --merge-candidates build/raw_candidates.jsonl \
  --skip-segmenter \
  --output build/community_candidates.jsonl
```

After reviewing candidates in JSON, compile only approved decisions:

```bash
python scripts/prepare_community_lexicon.py \
  --candidates build/community_candidates.jsonl \
  --review community/panhapich.review.json \
  --base-kdict build/analysis.kdict \
  --raw-corpus dataset/community/Panhapich-khmer-text-corpus/all_text.txt \
  --output build/panhapich-community.klex.json \
  --report build/panhapich-community-report.md

khmer-segment data compile build/panhapich-community.klex.json \
  --output build/panhapich-community.kdict
```

The community pack preserves relative frequency among its reviewed entries.
For an experimental one-file inclusive model that also updates the costs of
existing RAC and official-lexicon words, interpolate rather than replace the
curated model:

```bash
python scripts/blend_corpus_frequencies.py \
  --base-kdict build/analysis.kdict \
  --community-kdict build/panhapich-community.kdict \
  --corpus-frequencies build/known_frequencies.json \
  --corpus-weight 0.2 \
  --output-klex build/inclusive-corpus-blend.klex.json \
  --output-kdict build/inclusive-corpus-blend.kdict
```

The default 20% interpolation is an experimental starting point, not a release
default. Promote a blended model only after it does not regress the frozen
curated benchmark and its changed boundaries have been reviewed on real corpus
samples. The strict pack is not modified, and all spelling/autocomplete flags
are copied unchanged from their source packs.

The review file is a JSON array. A correction may replace a noisy extracted
candidate, but the corrected word must still be supported by the displayed
contexts:

```json
[
  {
    "candidate": "ហ្សែន",
    "word": "ហ្សែន",
    "status": "approved",
    "category": "borrowed_word",
    "note": "Repeated independent contexts referring to genes."
  }
]
```

Applications opt into the resulting evidence explicitly:

```python
segmenter = KhmerSegmenter.from_kdict_layers(
    "rac.kdict",
    lexicon_paths=["science.kdict"],
    community_paths=["panhapich-community.kdict"],
    mode="inclusive",
)
```
