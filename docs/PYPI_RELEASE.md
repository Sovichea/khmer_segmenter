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
system. Confirm that unapproved generated data remains ignored:

```bash
git status --short
git check-ignore khmer_segmenter/dictionary_data/khmer_dictionary_words.txt
git check-ignore port/common/khmer_dictionary.kdict
```

## 2. Test the source package

```bash
python -m pip install -e .
python -m pytest -q
python scripts/validate_findings.py --bundled-only
khmer-segment --help
khmer-segment data sources
```

Tests use both small independent fixtures and the approved bundled runtime
data. No network download is required.

## 3. Build and inspect

Remove old build outputs, then build the wheel and source distribution:

```bash
python -m build
python -m twine check dist/*
python scripts/check_distribution.py dist/*
```

The audit permits only the attributed runtime model, its reproducibility
manifest, and the preserved experimental hyphenation asset in the package data
directory. It rejects source corpora, native binaries, audit outputs, backups,
and other linguistic artifacts. Do not publish if it reports a prohibited member.

## 4. Test the wheel outside the repository

Create another empty environment outside the checkout and install the wheel:

```bash
python -m venv /tmp/khmer-segmenter-wheel-test
/tmp/khmer-segmenter-wheel-test/bin/python -m pip install dist/*.whl
/tmp/khmer-segmenter-wheel-test/bin/khmer-segment --help
/tmp/khmer-segmenter-wheel-test/bin/khmer-segment data status
```

On Windows, use a normal directory such as
`$env:TEMP\khmer-segmenter-wheel-test` and its `Scripts` folder. The dictionary,
frequencies, spellcheck lexicon, model manifest, lexical POS data, and
hyphenation pairs must report as available.
Run a real segmentation command to confirm direct use after installation.

## 5. TestPyPI and PyPI

The repository uses GitHub OIDC Trusted Publishing and does not store PyPI API
tokens. The trusted-publisher records must use:

```text
Workflow: publish-to-pypi.yml
TestPyPI environment: testpypi
PyPI environment: pypi
```

After committing and pushing the workflow, open **GitHub Actions → Publish
Python package → Run workflow**. A manual run builds, validates, and publishes
version `0.2.0rc3` to TestPyPI.

Test installation from TestPyPI before publishing a production release:

```bash
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --no-deps \
khmer-viterbi-segmenter==0.2.0rc3
```

Do not publish the release candidate to production PyPI until the 300-sentence
curated benchmark is approved and its stable gate passes. Then create the
corresponding GitHub Release tag; the release event rebuilds from that commit,
reruns the metadata and data audits, and publishes through trusted publishing.
Configure required reviewers on the `pypi` GitHub environment for manual
production approval.

Before the first public release, review old Git history separately. Clean wheel
contents do not remove restricted artifacts from historical commits.
