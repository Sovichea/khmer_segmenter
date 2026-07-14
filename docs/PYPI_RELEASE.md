# PyPI Release Guide

The PyPI distribution is `khmer-viterbi-segmenter`; the Python import package
and CLI are `khmer_segmenter` and `khmer-segment`. The name `khmer-segmenter`
is already used by a different PyPI project.

## 1. Start clean

Create a fresh virtual environment and install release tooling:

```bash
python -m venv .venv-release
python -m pip install --upgrade pip
python -m pip install build twine
```

Activate the environment using the command appropriate for the operating
system. Confirm that generated data remains ignored:

```bash
git status --short
git check-ignore khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
git check-ignore port/common/khmer_dictionary.kdict
```

## 2. Test the source package

```bash
python -m pip install -e .
python -m unittest discover -s tests -q
khmer-segment --help
khmer-segment data sources
```

Tests use small, independently created temporary fixtures. They do not require
or package the local production dictionary.

## 3. Build and inspect

Remove old build outputs, then build the wheel and source distribution:

```bash
python -m build
python -m twine check dist/*
python scripts/check_distribution.py dist/*
```

The audit rejects dictionary directories, native data binaries, and known
runtime data filenames. Do not publish if it reports a prohibited member.

## 4. Test the wheel outside the repository

Create another empty environment outside the checkout and install the wheel:

```bash
python -m venv /tmp/khmer-segmenter-wheel-test
/tmp/khmer-segmenter-wheel-test/bin/python -m pip install dist/*.whl
/tmp/khmer-segmenter-wheel-test/bin/khmer-segment --help
/tmp/khmer-segmenter-wheel-test/bin/khmer-segment data status
```

On Windows, use a normal directory such as
`$env:TEMP\khmer-segmenter-wheel-test` and its `Scripts` folder. A missing
dictionary status is expected in this clean environment; it proves the wheel
did not silently bundle local data.

## 5. TestPyPI and PyPI

Upload a release candidate to TestPyPI first:

```bash
python -m twine upload --repository testpypi dist/*
```

Test installation from TestPyPI, create a signed/versioned Git tag, and publish
the exact already-tested artifacts. For the final repository workflow, prefer
PyPI Trusted Publishing from a protected GitHub environment instead of storing
long-lived API tokens.

Before the first public release, review old Git history separately. Clean wheel
contents do not remove restricted artifacts from historical commits.
