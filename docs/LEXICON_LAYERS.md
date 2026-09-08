# Layered Lexicon Packs

A single dictionary should not decide every language policy. Khmer Viterbi
Segmenter can load independently replaceable KDIC v2 packs in this order:

1. **RAC** — the primary spelling and segmentation authority.
2. **Reviewed official lexicons** — genuinely new lexical units from named
   terminology sources, with one pack per source.
3. **User dictionary** — trusted application, organization, or personal words.
4. **Community evidence** — corpus-derived forms that are useful in inclusive
   mode but are not treated as RAC authority.

`strict` mode loads RAC, official lexicons, and user packs. `inclusive` mode
also loads community packs. Community entries therefore cannot silently make
strict spellcheck accept a popular typo.

## Python

```python
from khmer_segmenter import KhmerSegmenter

segmenter = KhmerSegmenter.from_kdict_layers(
    "rac.kdict",
    lexicon_paths=["geography.kdict", "science.kdict"],
    user_paths=["my-project.kdict"],
    community_paths=["community.kdict"],
    mode="strict",  # change to "inclusive" to load community evidence
)

evidence = segmenter.provenance_for("កាដម្យូម")
```

## CLI

Layer options are global and may be repeated:

```bash
khmer-segment \
  --rac-kdict rac.kdict \
  --lexicon-kdict geography.kdict \
  --lexicon-kdict science.kdict \
  --user-kdict my-project.kdict \
  --community-kdict community.kdict \
  --lexicon-mode strict \
  analyze --profile typing "..."
```

Inspect the identity, source documents, hashes, and policy counts embedded in
any pack:

```bash
khmer-segment data inspect geography.kdict
```

Rust and WASM read the same KDIC records. Applications that require one file
can use successive `data compile --base ...` operations to create a standalone
deployment pack. The original per-source packs should remain separate during
review so a source can be updated or removed without rebuilding unrelated
lexicons.

## Preparing the local official lexicons

The repository does not publish the source PDFs or generated packs. After
placing the locally obtained PDF and extraction TSV in `dataset/lexicon/`, run:

```bash
python scripts/prepare_official_lexicons.py
```

The script:

- normalizes text and removes zero-width characters;
- compares every candidate with RAC 2022, including COENG DA/TA aliases;
- excludes exact RAC words, confidently decomposable RAC phrases, annotations,
  examples, and reviewed multiword expressions;
- admits geography names only when the independent structured extraction
  corroborates the source row;
- treats all other OCR-only forms as pending until a human records an
  `approved` or `rejected` decision in
  `dataset/lexicon/official_lexicon_review.tsv`;
- writes one KLEX, KDIC, and audit TSV per source under
  `dataset/lexicon/generated/`;
- writes `official_lexicons.review.html`, an interactive card view showing the
  source crop beside each candidate, with correction, approval, rejection,
  status filtering, browser-local progress, and TSV export;
- embeds the source title, authority, year, PDF filename, SHA-256 digest, page,
  region, and original source headword in the KDIC provenance trailer.

The review TSV uses these columns:

```text
source  locator  candidate  status  approved_word  coeng_status  note
```

Use `approved_word` to correct an OCR transcription. If that corrected form is
already in RAC, the audit records `approved_rac` and does not duplicate it in
the secondary pack. Use `rejected` for a false extraction. Unlisted candidates
remain visible in the HTML review but are not compiled.

Approved forms containing COENG DA or COENG TA require a second decision:
`coeng_status=verified`. Until then they are compiled for segmentation only.
The compiler may generate the visual DA/TA alias for segmentation, but strict
spellcheck and autocomplete receive neither form from that secondary pack.
After verification, strict spellcheck accepts only the approved lexical form;
applications may still explicitly select visual spelling accuracy when they
want to accept both encodings.

An approved correction that exactly matches a RAC headword inherits RAC's
lexical authority and is recorded as `coeng_status=verified_rac`. A form that
matches only a generated RAC COENG DA/TA visual alias does not inherit that
authority: it remains pending for strict spelling even though segmentation may
use it.

The result is conservative, but it is still an extraction review—not a new
linguistic authority. Read each audit before distributing a generated pack.
In particular, verify the source document's copyright and redistribution
terms. The MPTC volume inspected for this workflow explicitly restricts
copying for distribution or commercial use without permission, so its pack is
local-only unless permission is obtained.

## Priority is not validity

Pack order resolves segmentation competition; flags decide policy. A form may
be accepted for segmentation without being accepted by spellcheck. Likewise,
a reviewed correction can preserve a common typo as one diagnostic span while
still suggesting the authoritative spelling. This separation should remain in
place when community packs are added later.
