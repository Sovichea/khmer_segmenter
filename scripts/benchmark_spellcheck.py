"""Measure editor-facing spellcheck and completion costs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from khmer_segmenter import KhmerSegmenter, SpellcheckProfile

try:
    import psutil
except ImportError:
    psutil = None


DEFAULT_TEXT = "សួរស្តី។ ខ្ញុំកំពុងសសេរអត្ថបទខ្មែរសម្រាប់សាកល្បង។"


def elapsed_ms(operation) -> float:
    start = time.perf_counter()
    operation()
    return (time.perf_counter() - start) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="UTF-8 paragraph used for latency tests")
    parser.add_argument(
        "--valid-input",
        type=Path,
        help="UTF-8 valid prose; each non-empty line is checked for false positives",
    )
    parser.add_argument("--prefix", default="សរសេ", help="completion prefix")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8-sig") if args.input else DEFAULT_TEXT
    process = psutil.Process(os.getpid()) if psutil else None
    memory_before = process.memory_info().rss if process else None
    start = time.perf_counter()
    segmenter = KhmerSegmenter()
    initialization_ms = (time.perf_counter() - start) * 1000
    first_spellcheck_ms = elapsed_ms(
        lambda: segmenter.check_text(text, profile=SpellcheckProfile.DOCUMENT)
    )
    repeated = [
        elapsed_ms(lambda: segmenter.check_text(text, profile=SpellcheckProfile.DOCUMENT))
        for _ in range(args.iterations)
    ]
    completions = [
        elapsed_ms(lambda: segmenter.complete_word(args.prefix))
        for _ in range(args.iterations)
    ]
    memory_after = process.memory_info().rss if process else None

    valid_lines = []
    false_positive_lines = 0
    diagnostics = 0
    if args.valid_input:
        valid_lines = [
            line.strip()
            for line in args.valid_input.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        for line in valid_lines:
            found = segmenter.check_text(line, profile=SpellcheckProfile.DOCUMENT)
            false_positive_lines += bool(found)
            diagnostics += len(found)

    report = {
        "text_codepoints": len(text),
        "iterations": args.iterations,
        "initialization_ms": round(initialization_ms, 3),
        "first_spellcheck_ms": round(first_spellcheck_ms, 3),
        "repeated_spellcheck_mean_ms": round(statistics.mean(repeated), 3),
        "repeated_spellcheck_p95_ms": round(sorted(repeated)[int(0.95 * (len(repeated) - 1))], 3),
        "completion_mean_ms": round(statistics.mean(completions), 3),
        "resident_memory_added_mb": (
            round((memory_after - memory_before) / 1024 / 1024, 3)
            if memory_before is not None and memory_after is not None
            else None
        ),
        "valid_lines": len(valid_lines),
        "false_positive_lines": false_positive_lines,
        "false_positive_line_rate": (
            round(false_positive_lines / len(valid_lines), 6) if valid_lines else None
        ),
        "false_positive_diagnostics": diagnostics,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
