"""Command-line interface installed as ``khmer-segment``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .data import (
    DATA_DIR_ENV,
    DICTIONARY_SOURCE_CREDIT,
    DICTIONARY_SOURCE_URL,
    DataFiles,
    DataNotFoundError,
    candidate_data_dirs,
)
from .hyphenation import KhmerHyphenator
from .preparation import prepare_dictionary
from .viterbi import KhmerSegmenter


def _add_text_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", nargs="?", help="Khmer text; omit to read stdin")
    parser.add_argument("--input", "-i", type=Path, help="read UTF-8 text from a file")
    parser.add_argument("--output", "-o", type=Path, help="write UTF-8 output to a file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="khmer-segment",
        description="Segment and analyze Khmer text using bundled or user-supplied data.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help=f"local linguistic data directory (or set {DATA_DIR_ENV})",
    )
    parser.add_argument("--verbose", action="store_true", help="show data-loading details")
    commands = parser.add_subparsers(dest="command", required=True)

    segment = commands.add_parser("segment", help="segment text into tokens")
    _add_text_input(segment)
    segment.add_argument("--format", choices=("plain", "json", "jsonl"), default="plain")
    segment.add_argument("--delimiter", default=" | ", help="plain-output delimiter")
    segment.add_argument("--no-normalize", action="store_true")

    analyze = commands.add_parser(
        "analyze", help="return offsets and lexical metadata (not contextual POS tagging)"
    )
    _add_text_input(analyze)
    analyze.add_argument("--format", choices=("json", "jsonl"), default="json")
    analyze.add_argument("--no-normalize", action="store_true")

    spellcheck = commands.add_parser(
        "spellcheck", help="check words against the curated RAC spelling lexicon"
    )
    _add_text_input(spellcheck)
    spellcheck.add_argument("--format", choices=("plain", "json", "jsonl"), default="plain")
    spellcheck.add_argument("--no-normalize", action="store_true")

    diagnose = commands.add_parser(
        "diagnose", help="find probable Khmer typos and return whole-span suggestions"
    )
    _add_text_input(diagnose)
    diagnose.add_argument("--format", choices=("json", "jsonl"), default="json")
    diagnose.add_argument("--no-normalize", action="store_true")
    diagnose.add_argument("--max-edit-cost", type=float, default=0.75)
    diagnose.add_argument("--max-suggestions", type=int, default=3)
    diagnose.add_argument(
        "--include-valid-fragments",
        action="store_true",
        help="also inspect adjacent valid tokens (higher recall, more false positives)",
    )

    hyphenate = commands.add_parser(
        "hyphenate", help="apply locally generated safe break opportunities"
    )
    _add_text_input(hyphenate)
    hyphenate.add_argument(
        "--separator",
        default="\u200b",
        help="inserted separator; defaults to zero-width space",
    )
    hyphenate.add_argument(
        "--visible-hyphen", action="store_true", help="insert '-' for inspection"
    )

    benchmark = commands.add_parser("benchmark", help="measure segmentation throughput")
    benchmark.add_argument("--input", "-i", required=True, type=Path)
    benchmark.add_argument("--limit", type=int, default=-1)

    data = commands.add_parser("data", help="inspect external data requirements")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    data_commands.add_parser("status", help="show resolved local files")
    data_commands.add_parser("sources", help="show original download sources and credits")
    prepare = data_commands.add_parser(
        "prepare", help="normalize a manually downloaded dictionary TSV"
    )
    prepare.add_argument("--rac-tsv", required=True, type=Path)
    prepare.add_argument(
        "--output-dir",
        type=Path,
        help="destination; defaults to --data-dir or the user data directory",
    )
    return parser


def _read_inputs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    if args.text is not None and args.input is not None:
        parser.error("provide either positional text or --input, not both")
    if args.text is not None:
        return [args.text]
    if args.input is not None:
        content = args.input.read_text(encoding="utf-8-sig")
    else:
        if sys.stdin.isatty():
            parser.error("provide text, --input FILE, or pipe UTF-8 text on stdin")
        content = sys.stdin.read()
    return [line for line in content.splitlines() if line.strip()]


def _write(text: str, output: Path | None = None) -> None:
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _serialize_records(records: list[dict[str, Any]], output_format: str) -> str:
    if output_format == "jsonl":
        return "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    return json.dumps(records, ensure_ascii=False, indent=2)


def _segmenter(args: argparse.Namespace) -> KhmerSegmenter:
    return KhmerSegmenter.from_data_dir(args.data_dir)


def _data_files_for_status(explicit: Path | None) -> DataFiles:
    candidates = candidate_data_dirs(explicit)
    for candidate in candidates:
        files = DataFiles(candidate)
        if any(files.status().values()):
            return files
    return DataFiles(candidates[0])


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "data":
        if args.data_command == "sources":
            print(f"Dictionary: {DICTIONARY_SOURCE_URL}")
            print(f"Credit: {DICTIONARY_SOURCE_CREDIT}")
            print("Authority: National Council of Khmer Language, Royal Academy of Cambodia")
            print("Terms: noncommercial redistribution with attribution")
            print("Notice: DATA_LICENSE.md in the source and installed distribution")
            print("Optional rebuild: khmer-segment data prepare --rac-tsv PATH")
            return 0
        if args.data_command == "prepare":
            output_dir = args.output_dir or _data_files_for_status(args.data_dir).root
            report = prepare_dictionary(args.rac_tsv, output_dir)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"Prepared local dictionary in: {Path(output_dir).resolve()}")
            return 0
        files = _data_files_for_status(args.data_dir)
        print(f"Data directory: {files.root}")
        for name, exists in files.status().items():
            print(f"{name:20} {'ready' if exists else 'missing'}")
        return 0 if files.dictionary.is_file() else 1

    if args.command == "benchmark":
        lines = [
            line for line in args.input.read_text(encoding="utf-8-sig").splitlines() if line.strip()
        ]
        if args.limit >= 0:
            lines = lines[: args.limit]
        segmenter = _segmenter(args)
        started = time.perf_counter()
        token_count = sum(len(segmenter.segment(line)) for line in lines)
        duration = max(time.perf_counter() - started, 1e-9)
        print(f"lines={len(lines)} tokens={token_count} seconds={duration:.6f}")
        print(f"lines_per_second={len(lines) / duration:.2f}")
        return 0

    texts = _read_inputs(args, parser)
    segmenter = _segmenter(args)

    if args.command == "segment":
        records = [
            {
                "text": text,
                "tokens": segmenter.segment(text, normalize=not args.no_normalize),
            }
            for text in texts
        ]
        if args.format == "plain":
            rendered = "\n".join(args.delimiter.join(record["tokens"]) for record in records)
        else:
            rendered = _serialize_records(records, args.format)
        _write(rendered, args.output)
        return 0

    if args.command == "analyze":
        records = [
            {
                "text": text,
                "tokens": [
                    token.to_dict()
                    for token in segmenter.analyze(text, normalize=not args.no_normalize)
                ],
            }
            for text in texts
        ]
        _write(_serialize_records(records, args.format), args.output)
        return 0

    if args.command == "spellcheck":
        words = [word for text in texts for word in text.split()]
        records = segmenter.check_spelling(words, normalize=not args.no_normalize)
        if args.format == "plain":
            rendered = "\n".join(
                f"{'valid' if record['valid'] else 'invalid'}\t{record['word']}"
                for record in records
            )
        else:
            rendered = _serialize_records(records, args.format)
        _write(rendered, args.output)
        return 0

    if args.command == "diagnose":
        records = [
            {
                "text": text,
                "diagnostics": [
                    diagnostic.to_dict()
                    for diagnostic in segmenter.detect_typos(
                        text,
                        normalize=not args.no_normalize,
                        max_edit_cost=args.max_edit_cost,
                        max_suggestions=args.max_suggestions,
                        include_valid_fragments=args.include_valid_fragments,
                    )
                ],
            }
            for text in texts
        ]
        _write(_serialize_records(records, args.format), args.output)
        return 0

    if args.command == "hyphenate":
        hyphenator = KhmerHyphenator.from_data_dir(args.data_dir)
        separator = "-" if args.visible_hyphen else args.separator
        rendered = "\n".join(
            hyphenator.hyphenate(text, segmenter=segmenter, separator=separator) for text in texts
        )
        _write(rendered, args.output)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        return run(args, parser)
    except (DataNotFoundError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
