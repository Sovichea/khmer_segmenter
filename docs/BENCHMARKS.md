# Benchmark Results

These measurements document a specific code, data, and hardware snapshot. Run
the supplied scripts on your deployment hardware before making capacity or
latency decisions.

## Gold-standard accuracy

The historical locally generated frequency model used only derived training
partitions. Results use stable held-out test partitions and Unicode boundary
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

## Frequency coverage

The recorded local artifacts combined 3,120,579 corpus tokens with 585,396
validated tokens from derived gold training partitions. The generated runtime
frequency table had 29,719 observed entries. The runtime counts are bundled;
detailed provenance and intermediate build outputs are not distributed.

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
