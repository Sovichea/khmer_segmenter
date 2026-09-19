# Khmer Viterbi Segmenter 0.3.1

Version 0.3.1 is a precision fix for typo detection. It stops common phrases
from being reported as misspellings of rare compounds.

Highlights:

- The typo detector no longer flags a phrase of common words when a
  machine-generated one-character alias happens to resemble a rare compound.
  For example `ត្រីសួរ` ("fish asked") is no longer reported as a typo of
  `ត្រីសូរ`, and `អ្នកគ្រូ` ("teacher") is no longer reported as a typo of
  `អ្នកគ្រួ`.
- Reviewed phrase collisions are listed in
  `khmer_typo_phrase_exclusions.txt` and shared by the Python, Rust, and
  WebAssembly ports, so behaviour stays identical across implementations.
- Approved correction pairs and real missing or extra `រ` typos, such as
  `ចងកា` -> `ចងការ`, are unchanged.

The bundled RAC-derived lexical data is redistributed for noncommercial use with
attribution. See `DATA_LICENSE.md` for its source, pinned revision, and terms.
The program source remains under the MIT license.

Known limitations:

- Phrase collisions are reviewed rather than inferred from frequency, because
  missing or extra `រ` typos overlap the same surface patterns; regenerate the
  list with `python scripts/build_typo_phrase_exclusions.py`.
- segmentation is lexical and deterministic, not full semantic parsing;
- unknown names, new terminology, and informal forms can still require an
  application dictionary;
- the 300-sentence benchmark was seeded from model output and then reviewed, so
  it is a regression set rather than an independent linguistic gold standard;
- the C port reads KDIC data but does not yet expose the full analysis API.
