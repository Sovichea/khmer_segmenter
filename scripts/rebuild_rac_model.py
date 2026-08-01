#!/usr/bin/env python3
"""Rebuild strict RAC-only runtime data from the structured RAC 2022 CSV."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from khmer_segmenter.rac_rebuild import build_rac_model  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rac-csv",
        type=Path,
        default=ROOT / "dataset" / "RAC-Khmer-Dict-2022.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "rac")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--processes",
        type=int,
        default=max(1, min(4, (os.cpu_count() or 2) - 1)),
    )
    parser.add_argument(
        "--install-data-dir",
        type=Path,
        help="copy the rebuilt runtime files into this directory",
    )
    args = parser.parse_args()
    result = build_rac_model(
        args.rac_csv,
        args.output_dir,
        iterations=args.iterations,
        processes=args.processes,
    )
    if args.install_data_dir:
        args.install_data_dir.mkdir(parents=True, exist_ok=True)
        for source in result.data_dir.iterdir():
            if source.is_file():
                shutil.copyfile(source, args.install_data_dir / source.name)
    print(
        json.dumps(
            {
                "data_dir": str(result.data_dir),
                "summary": str(result.summary_path),
                "report": str(result.report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
