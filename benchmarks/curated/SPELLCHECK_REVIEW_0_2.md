# 0.2 Visual-Mode Spellcheck Review

This short review isolates every diagnostic produced when the document profile
checks the 300 segmentation-review sentences with `accuracy="visual"`.

For each item, replace `pending` with one of:

- `error` — the source form should be corrected;
- `common_variant` — accepted in community-aware spelling but not RAC-strict mode;
- `valid_lexicon` — a reviewed lexical item that belongs in an official pack;
- `name` — valid in this context and suitable for a name/user pack;
- `unknown` — not enough evidence to classify it.

## nfp-029

Sentence: `អ្នកទេសចរបានមកទស្សនាតំបន់ប្រាសាទកាន់តែច្រើន។`

Diagnostic: `ទស្សនា` (`extra_character`)

Suggestions: `ទស្សន`, `ទស្សនៈ`

Decision: `valid_lexicon`

Note: widely used Pali-derived verb meaning to look at, visit, tour, or attend;
the reviewed reference is <https://en.wiktionary.org/wiki/ទស្សនា>.

## con-015

Sentence: `តោះយើងទៅផឹកកាហ្វេជាមួយគ្នា។`

Diagnostic: `តោះ` (`extra_character`)

Suggestions: `តះ`, `តុះ`, `តោ`

Decision: `common_variant`

Canonical form: `តស់`

## con-023

Sentence: `កុំបារម្ភអីខ្ញុំអាចដោះស្រាយបាន។`

Diagnostic: `អី` (`probable_misspelling`)

Suggestions: `អា`, `អើ`, `អ៊ី`

Decision: `common_variant`

Note: informal and literary substitute whose intended expansion can depend on
context (`អ្វី` or `ថ្វី`); do not force one automatic replacement.

## con-029

Sentence: `ដើរត្រង់ទៅរួចបត់ឆ្វេងនៅស្តុប។`

Diagnostic: `ស្តុប` (`probable_misspelling`)

Suggestions: `ស្តូប`, `ស្តូបៈ`, `ស្ដាប់`

Decision: `valid_lexicon`

Note: established borrowed word used for a traffic stop/intersection.

## nam-004

Sentence: `លោកវណ្ណាបានទៅទស្សនាប្រាសាទអង្គរវត្ត។`

Diagnostic 1: `វណ្ណា` (`extra_character`)

Suggestions: `វណ្ណ`, `វណ្ណៈ`, `ឧណ្ណា`

Decision: `name`

Diagnostic 2: `ទស្សនា` (`extra_character`)

Suggestions: `ទស្សន`, `ទស្សនៈ`

Decision: `valid_lexicon`

Note: same reviewed lexical item as `nfp-029`.

## nam-011

Sentence: `អ្នកស្រីចន្ទាបានបើកហាងលក់សៀវភៅនៅក្រុងបាត់ដំបង។`

Diagnostic: `ចន្ទា` (`extra_character`)

Suggestions: `ចន្ទ`, `ចន្ទី`, `ចន្ទាស`

Decision: `error`

Note: `ចន្ទា` may be a personal name after the honorific `អ្នកស្រី`, but context
alone must not make an unknown form spelling-valid. The deterministic base
policy flags it because it is absent from the curated lexicons. A user or
application dictionary can explicitly accept the name. Do not apply an
automatic correction because the intended spelling is not known.
