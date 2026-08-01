# Documentation

Use this page to find the right level of detail without searching through the
main README.

## Start here

- [Project overview and quick start](../README.md)
- [Design philosophy](DESIGN_PHILOSOPHY.md)
- [Data sources, attribution, and provenance](DATA.md)
- [RAC-only model rebuild](RAC_REBUILD.md)
- [Migration from 0.1.1 to 0.2](MIGRATION_0_2.md)
- [PyPI release guide](PYPI_RELEASE.md)

## Use and evaluate

- [Evaluation guide](EVALUATION.md): curated gate, legacy diagnostics, metrics, and commands
- [Benchmark results](BENCHMARKS.md): accuracy and runtime measurements
- [Development workflows](DEVELOPMENT.md): tests, corpus preparation,
  frequencies, dictionaries, and unknown-word review
- [Prepare dictionaries for Python, C, and Rust](EMBEDDED_DICTIONARY.md): local
  source preparation, KDIC/KHYP conversion, testing, and deployment

## Implementations

- [Algorithm and porting reference](../port/README.md)
- [C implementation](../port/c/README.md)
- [Rust implementation](../port/rust/README.md)

## Recommended reading paths

For application developers: start with the main README, then select the Python,
C, or Rust implementation guide.

For NLP evaluation: read the data policy first, followed by the evaluation and
benchmark documents.

For contributors: read the development workflow and the porting reference
before changing shared dictionary or normalization behavior.
