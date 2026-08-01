# Hugging Face Corpus Experiment

This experiment tests whether additional raw Khmer text improves frequency-
weighted segmentation. It does not modify the packaged dictionary or frequency
table, and it does not treat machine-produced segmentation as gold annotation.

## Sources and credit

| Source | Purpose | Credit | Terms |
|:---|:---|:---|:---|
| [Wikimedia Wikipedia](https://huggingface.co/datasets/wikimedia/wikipedia) (`20231101.km`) | Formal language and vocabulary coverage | Wikimedia contributors and the Wikimedia Foundation | CC BY-SA 3.0 and GFDL |
| [Hugging Face FineWeb2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) (`khm_Khmr`) | Broader web usage and modern vocabulary | FineWeb2 authors, Hugging Face, and Common Crawl | ODC-By 1.0; review Common Crawl terms |

Raw samples, manifests, generated counts, and reports are written under the
ignored `experiments/` directory. They must not be added to Git or release
archives. The generated frequency table remains experimental until its source
terms and redistribution implications have been reviewed.

## Install the optional loader

```bash
python -m pip install -e ".[corpus]"
```

This dependency is for research only and is not installed with the segmenter.

## Run a small pilot

```bash
python scripts/experiment_hf_corpora.py all \
  --wikipedia-limit 1000 \
  --fineweb2-limit 2000
```

## Run the proposed sample

```bash
python scripts/experiment_hf_corpora.py all \
  --wikipedia-limit 25000 \
  --fineweb2-limit 100000
```

Set `HF_TOKEN` in the environment to obtain higher Hugging Face download rate
limits. Do not put the token in a command, script, manifest, or committed file.

The process performs four safeguards:

1. reject documents with insufficient Khmer-script content;
2. deduplicate sampled documents by SHA-256;
3. count only words already present in the approved dictionary and only from
   chunks whose unknown-token rate is at most 15%;
4. write unknown spans to a review list instead of adding them automatically.

The raw-corpus contribution is capped at 20% of the baseline token count, with
Wikipedia weighted at 0.5 and FineWeb2 at 0.2. These are experimental weights,
not claims about corpus quality.

To test another contribution without downloading again, keep `--sample-dir`
pointed at the original sample and choose a separate output directory:

```bash
python scripts/experiment_hf_corpora.py build \
  --sample-dir experiments/hf-corpora \
  --output-dir experiments/hf-corpora-share-10 \
  --corpus-share 0.10
python scripts/experiment_hf_corpora.py evaluate \
  --output-dir experiments/hf-corpora-share-10
```

## Interpret the report

`evaluation_report.json` compares the unchanged production model with the
experimental model on the stable khPOS and Khmer ALT test partitions. A change
is promising only if it improves results across both annotation standards, or
if a domain-specific gain has a documented reason and does not materially harm
the other benchmark.

Raw text cannot establish correct word boundaries. Any unknown candidate must
be reviewed by a Khmer speaker before it can enter the dictionary. The gold
test partitions must never be used to generate frequency counts.

## Pilot result: 2026-07-16

The first reproducible pilot sampled 1,000 Wikipedia documents and 2,000
FineWeb2 documents, capped each document at 2,000 characters, and evaluated all
1,179 khPOS test sentences and 1,981 Khmer ALT test sentences. The pinned source
revisions were:

- Wikimedia Wikipedia: `b04c8d1ceb2f5cd4588862100d08de323dccfbaa`
- FineWeb2: `af9c13333eb981300149d5ca60a8e9d659b276b9`

The table reports the absolute boundary-F1 change in percentage points. “Better”
and “worse” count changed sentences with more or fewer correct boundaries;
other changed sentences moved boundaries without changing the correct count.

| Corpus contribution | khPOS F1 change | khPOS better/worse | ALT F1 change | ALT better/worse |
|---:|---:|---:|---:|---:|
| 5% | +0.00473 | 1 / 0 | +0.00273 | 2 / 0 |
| 10% | +0.00473 | 1 / 0 | +0.00091 | 2 / 1 |
| 20% | +0.01351 | 2 / 0 | +0.00182 | 3 / 1 |
| 40% | +0.03243 | 6 / 0 | +0.00139 | 5 / 2 |
| 80% | +0.04593 | 7 / 0 | +0.00006 | 6 / 3 |

The 40% setting was the best balanced pilot setting, but it changed only 7
khPOS and 19 ALT sentences. At 80%, the ALT improvement effectively disappeared
and boundary instability increased. None of these settings changed exact-
sentence accuracy. The result is therefore evidence that corpus frequencies
can influence useful tie-breaking, not evidence that the production model
should be replaced.

The candidate audit also found that frequent unknown spans contain a mixture of
legitimate variants (for example `ឲ្យ`), names, transliterations, and fragments
created by the current segmenter. Candidates must remain a human-review queue;
automatically adding them would create a self-training feedback loop.

Next, repeat the 40% setting on a larger independently sampled corpus and add a
manually segmented modern-Khmer test set before considering a runtime-data
change. Do not select a setting solely because it maximizes one of the existing
test partitions.
