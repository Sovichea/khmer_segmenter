# Local corpus typo-candidate review

This review scanned the developer-local folklore and Khmer Wikipedia text
files. It does not redistribute either source corpus or any complete excerpt.

The occurrence totals use `khmer_folktales_extracted.txt` and the full
`khmer_wiki_corpus.txt`. `wiki_5k.txt` is a subset and was not counted again.
`unknown_words_from_results.txt` is a derived report, while `allwords.txt` is
lexicographic reference material rather than natural prose, so neither is used
as independent typo evidence. The ZIP contains paired original and
ZWSP-segmented documents; it is excluded from totals to avoid counting paired
copies of the same document twice.

## Method

1. Remove every U+200B ZERO WIDTH SPACE before any processing.
2. Run the Rust high-recall diagnostic profile over the resulting continuous
   text.
3. Aggregate repeated `(observed form, proposed correction)` spans.
4. Require the correction to be supported by the curated spellcheck lexicon
   for `top1` candidates.
5. Manually reject valid phrases, proper names, Pali/Sanskrit forms, historical
   spellings, and candidates caused by a substring of a longer word.
6. Keep uncertain legacy and colloquial forms as `context_required` rather
   than silently declaring them incorrect.

## Result

The review initially added records `dataset-001` through `dataset-172` as
**pending**. Their current review status is maintained in the canonical TSV;
only records whose status is changed to `approved` affect Python, Rust, CLI, or
WASM spellchecking. Later community-reviewed records may continue the same ID
sequence.

The strongest repeated family omits or misplaces a medial consonant, especially
forms such as:

- `ទំងន់` → `ទម្ងន់`
- `ចំលើយ` → `ចម្លើយ`
- `សំភារៈ` → `សម្ភារៈ`
- `កំលាំង` → `កម្លាំង`
- `បំរើ` → `បម្រើ`

Other recurring groups include wrong final signs (`លក្ខណះ` → `លក្ខណៈ`),
extra final consonants (`សិក្សារ` → `សិក្សា`), and transcription mistakes
(`អ៊ីនធើណេត` → `អ៊ីនធឺណិត`).

## Final-review cautions

Give special attention to `context_required` records. They include widespread
legacy or informal forms such as `អោយ`, `រឺ`, `លឺ`, `ត្រលប់`, and `គំរោង`.
Whether these should produce a red spelling diagnostic is a product policy
decision, even when a modern RAC-preferred form exists.

The same caution applies to `សំដែង` → `សម្ដែង` and `សំអាង` → `សម្អាង`,
which occur often enough that users may regard them as accepted variants.

Also review `ជាមួយនិង` → `ជាមួយនឹង` and `ស្មើនិង` → `ស្មើនឹង` in context:
`និង` and `នឹង` cannot be distinguished safely by dictionary lookup alone.
