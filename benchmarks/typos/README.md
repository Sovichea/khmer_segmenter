# Real-world Khmer typo review set

This directory contains a small, manually reviewed diagnostic set for typo
recovery. It is not a statistically representative corpus and must not be
reported as a general Khmer spellchecking benchmark.

Only minimal typo pairs and short context fragments are stored. Complete social
media posts, author profiles, user identifiers, reactions, and comments are not
redistributed. The records exist to reproduce specific spelling observations
and link back to their public sources.

## Expectations

- `top1`: the intended RAC spelling should be the first whole-word suggestion.
- `top_k`: the intended spelling should occur in the first ten suggestions.
- `normalization`: Unicode/orthographic normalization should accept the form.
- `context_required`: both forms can be lexical, or the correction changes a
  phrase; dictionary-only spelling cannot safely decide it.

Records marked `context_required` are deliberate negative requirements. They
prevent the project from claiming that a word-list spellchecker can solve
homophones such as `នឹង`/`និង` without a contextual model.

## Sources and credits

- `royal-army-2025-02-19`: Royal Cambodian Army Facebook page,
  [public post dated 19 February 2025](https://www.facebook.com/RoyalCambodianArmy1999/posts/1191388972559250/).
- `royal-army-2025-04-02`: Royal Cambodian Army Facebook page,
  [public post dated 2 April 2025](https://www.facebook.com/RoyalCambodianArmy1999/posts/1225159052515575/).
- `sophai-comment-2025`: a public Khmer comment indexed beneath
  [Sophai Creator Share's Facebook post](https://www.facebook.com/SophaiCreatorShare/posts/1637054620678578/).
  The contributor's name and full comment are intentionally not reproduced.
- `exam-page-2025`: វិញ្ញាសាបាក់ឌុប2026 Facebook page,
  [public post](https://www.facebook.com/permalink.php/?id=100076683460508&story_fbid=759568706609238).
- `pisethan-spelling`: Pisethan's
  [Khmer spelling dataset](https://huggingface.co/datasets/Pisethan/khmer_spelling_dataset),
  licensed CC BY 4.0. The upstream dataset has only 13 rows, including
  duplicates and unchanged pairs, so only five distinct correction observations
  are used here.
- `local-corpus-review`: candidates mined from the developer's local
  `khmer_folktales_extracted.txt` and `khmer_wiki_corpus.txt` files. The source
  texts and excerpts are not redistributed by this repository. Every U+200B
  ZERO WIDTH SPACE was removed before segmentation, typo detection, counting,
  and context review. Counts in candidate notes are evidence for prioritizing
  review, not proof that a spelling is incorrect.

Facebook observations remain links and factual minimal excerpts; no Facebook
dataset license is asserted. Remove any record if its public source disappears
or its correction cannot be independently confirmed against the RAC lexicon.

## Run

```bash
python scripts/evaluate_real_world_typos.py
```
