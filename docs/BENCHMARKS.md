# Benchmark Results

These measurements document a specific code, data, and hardware snapshot. Run
the supplied scripts on your deployment hardware before making capacity or
latency decisions.

## Legacy compatibility accuracy

These corpora are outdated or insufficiently curated for the project's current
segmentation convention. The numbers below are historical diagnostics, not a
release gate. The historical locally generated frequency model used only
derived training partitions. Results use stable held-out test partitions and Unicode boundary
scoring. The approved runtime model is distributed under the separate data
terms in [`DATA_LICENSE.md`](../DATA_LICENSE.md).

| Dataset | Sentences | Boundary precision | Boundary recall | Boundary F1 | Exact sentence | Unknown tokens |
|:---|---:|---:|---:|---:|---:|---:|
| khPOS test | 1,179 | 89.96% | 93.31% | **91.61%** | 37.49% | 3.34% |
| Khmer ALT POS test | 1,981 | 89.97% | 78.32% | **83.74%** | 0.30% | 4.54% |

khPOS is more representative of local formal and news-style Cambodian text.
Khmer ALT uses translated Wikinews and often finer, morpheme-level boundaries,
so lower recall is not necessarily a dictionary error.

Training-only gold augmentation changed khPOS test F1 from 91.46% to 91.61%
and Khmer ALT test F1 from 83.78% to 83.74%. This difference reinforces that
the corpora do not encode an identical segmentation standard.

The strict RAC candidate showed the expected convention tradeoff in local
diagnostics: khPOS boundary F1 changed from 92.14% to 89.00%, while Khmer ALT
changed from 84.63% to 89.29%. That disagreement is why neither legacy corpus
is authoritative. The 300-sentence curated benchmark must be completed before
the 0.2 stable-release decision.

## RAC 0.2 release-candidate performance

A local Windows/Python 3.10 comparison used six representative sentences in a
12,000-call loop. It measures the common segmentation-only path; POS/source and
spellcheck resources in 0.2 load lazily when those APIs are first used.

| Version | Initialization | Incremental RSS | Sentences/second |
|:---|---:|---:|---:|
| 0.1.1 | 0.684 s | 23.5 MB | 2,500 |
| 0.2.0rc1 | 0.358 s | 12.5 MB | 2,529 |

The candidate stayed within the 15% release threshold: startup and incremental
memory improved substantially, while steady-state throughput was approximately
unchanged (+1%). Repeat this measurement on deployment hardware before making
capacity decisions.

## Frequency coverage

The historical 0.1 artifacts combined 3,120,579 corpus tokens with 585,396
tokens from derived legacy training partitions and produced 29,719 frequency
entries. The strict RAC 0.2 model instead has 25,401 entries derived only from
RAC definitions, examples, and discounted self-headword evidence. Its final raw
weighted total is 838,723.25; integer serialization yields 840,592. The bundled
manifest records these parameters and file hashes, while source and
intermediate audit data remain local.

## Runtime snapshot

The following historical measurements were recorded on consumer Linux/Ryzen 7
hardware with four worker threads where applicable.

| Scenario | Metric | khmernltk | Python | C | Rust |
|:---|:---|---:|---:|---:|---:|
| Micro | Sequential latency | ~2.90 ms | ~2.21 ms | ~0.36 ms | ~0.34 ms |
| Micro | Four-thread throughput | ~330 calls/s | ~503 calls/s | ~10,970 calls/s | ~10,909 calls/s |
| Macro | Four-thread throughput | ~378 lines/s | ~585 lines/s | ~30,838 lines/s | ~31,250 lines/s |
| Memory | Initialization | ~113 MB | ~36 MB | ~4.8 MB | ~2.2 MB |

Python thread scaling is constrained by the GIL and scheduling overhead. Native
ports are intended for high-throughput or low-memory deployments.

## Reproduce locally

```bash
python scripts/benchmark_suite.py

khmer-segment benchmark --input path/to/your/local_corpus.txt
```

See [Evaluation Guide](EVALUATION.md) for gold-corpus commands and metric
definitions.
