# RAC-only rebuild design

## Authority and evidence are separate

RAC headwords and subentries determine lexical validity. RAC definitions and
examples only affect relative segmentation costs among already accepted words.
A frequent string in uncurated text never becomes a valid spelling automatically.

## Segmentation versus spellcheck

The segmentation lexicon excludes clean RAC subentries without POS evidence
because many are phrase-like or editorial. The spellcheck lexicon retains those
forms because they are curated RAC forms. This avoids forcing long phrases into
one token while preserving their spelling validity.

## Repetition forms

`ៗ` can be punctuation-like in fallback behavior and lexical inside a complete
word. The runtime therefore keeps accepted dictionary forms containing `ៗ` and
removes only standalone `ៗ` from the word set. During Viterbi decoding, a known
form ending in `ៗ` receives deterministic lexical priority over a base-word plus
separator path.

## Frequency calculation

- Definition occurrence weight: 1.0
- Example occurrence weight: 3.0
- Self-headword occurrence multiplier: 0.25
- Iterations: 3
- Frequency floor at runtime: unchanged from the upstream Viterbi engine

The normalized distribution L1 changes were approximately 0.009407 after the
second iteration and 0.000414 after the third iteration.

## Rebuild and verify

Download `RAC-Khmer-Dict-2022.csv` from pinned Hugging Face revision
`525c0171894465cba920a9181387a032c11610d3` into the ignored `dataset/`
directory. Its expected SHA-256 is
`3c6e9908b7881d36c1e43ae66258554d5c1dc07cc75bc9ea660c985cd413ee76`.
Then run:

```bash
python scripts/rebuild_rac_model.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv \
  --output-dir build/rac
python scripts/validate_findings.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv
```

`khmer_model_manifest.json` records the source hash, generator parameters,
counts, and SHA-256 of every generated runtime file. Source CSVs, audit tables,
and intermediate iteration files are deliberately excluded from packages.
