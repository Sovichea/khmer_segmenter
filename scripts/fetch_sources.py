#!/usr/bin/env python3
"""Download the pinned upstream sources needed by repository tools.

A fresh clone contains the runtime model but not the upstream source tables,
which are intentionally excluded from Git. This script fetches them from the
pinned revision so rebuild and validation scripts can run reproducibly.

Example:
    python scripts/fetch_sources.py
    python scripts/fetch_sources.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "dataset"

RAC_REVISION = "525c0171894465cba920a9181387a032c11610d3"
RAC_URL = (
    "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/"
    f"{RAC_REVISION}/RAC-Khmer-Dict-2022.csv"
)
RAC_SHA256 = "3c6e9908b7881d36c1e43ae66258554d5c1dc07cc75bc9ea660c985cd413ee76"

# Chuon Nath Dictionary (1967), digitized by the Open Institute / SPICE.
# Used as a secondary frequency source and for reviewed legacy orthography.
KH_DICT_REVISION = "85f37da6d79e9cc8f45a1fe308fc518fa24eddb4"
KH_DICT_BASE = (
    "https://raw.githubusercontent.com/interscript/khmer-dict-spice/"
    f"{KH_DICT_REVISION}/"
)

SOURCES = (
    {
        "name": "RAC-Khmer-Dict-2022.csv",
        "url": RAC_URL,
        "sha256": RAC_SHA256,
    },
    {
        "name": "kh_dictionary.csv",
        "url": KH_DICT_BASE + "kh_dictionary.csv",
        "sha256": "08784fa1a34e0c620d100421d6c7daa7cbafd8e5836dfe792b3f64ff94d22ca9",
        "subdir": "khmer-dict-spice",
    },
    {
        "name": "SBBICkm_KH.txt",
        "url": KH_DICT_BASE + "SBBICkm_KH.txt",
        "sha256": "04069fd81ea2107cd324d2f776da60cdf749b100a55dfffb58c896a7556fca7f",
        "subdir": "khmer-dict-spice",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "khmer-segmenter-fetch"})
    try:
        with urllib.request.urlopen(request) as response, temporary.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.URLError as error:  # pragma: no cover - network dependent
        temporary.unlink(missing_ok=True)
        raise SystemExit(
            f"failed to download {url}: {error}\n"
            "Check your network connection and try again."
        ) from error
    temporary.replace(destination)


def fetch_source(source: dict, destination_dir: Path, *, force: bool) -> bool:
    destination = destination_dir / source.get("subdir", "") / source["name"]
    if destination.is_file() and not force:
        digest = _sha256(destination)
        if digest == source["sha256"]:
            print(f"[skip] {destination} already matches the pinned revision")
            return True
        print(f"[warn] {destination} does not match the pinned revision; refetching")
    print(f"[get ] {source['url']}")
    _download(source["url"], destination)
    digest = _sha256(destination)
    if digest != source["sha256"]:
        destination.unlink(missing_ok=True)
        raise SystemExit(
            f"checksum mismatch for {destination}:\n"
            f"  expected {source['sha256']}\n"
            f"  actual   {digest}\n"
            "The upstream file changed; review before using it."
        )
    print(f"[ ok ] {destination} verified")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATASET_DIR,
        help="destination directory (default: dataset/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="download again even when the file already matches",
    )
    args = parser.parse_args()
    destination_dir = args.output_dir.resolve()
    for source in SOURCES:
        fetch_source(source, destination_dir, force=args.force)
    print("Upstream sources are ready. Rebuild tools can now run.")


if __name__ == "__main__":
    sys.exit(main())
