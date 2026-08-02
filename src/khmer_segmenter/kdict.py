"""Reader for the shared, compact KDIC language-pack format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import struct


SEGMENT = 1 << 0
SPELLCHECK = 1 << 1
AUTOCOMPLETE = 1 << 2
TYPO_SURFACE = 1 << 3
SUPPLEMENTAL = 1 << 4

_HEADER = struct.Struct("<4sIIIffII")
_TABLE_ENTRY = struct.Struct("<If")
_EXTENSION_HEADER = struct.Struct("<4sIII")
_WORD_RECORD = struct.Struct("<IIf")
_TYPO_RECORD = struct.Struct("<II")


@dataclass(frozen=True)
class KDictWord:
    word: str
    flags: int
    cost: float


class KDict:
    """Decoded KDIC data shared by the Python, Rust, and WASM runtimes."""

    def __init__(self, data: bytes):
        if len(data) < _HEADER.size:
            raise ValueError("KDIC file is truncated")
        (
            magic,
            self.version,
            self.num_entries,
            self.table_size,
            self.default_cost,
            self.unknown_cost,
            self.max_word_bytes,
            extension_offset,
        ) = _HEADER.unpack_from(data)
        if magic != b"KDIC":
            raise ValueError("invalid KDIC magic")
        if self.version not in (1, 2):
            raise ValueError(f"unsupported KDIC version {self.version}")
        if self.table_size < 2 or self.table_size & (self.table_size - 1):
            raise ValueError("KDIC table size must be a power of two")
        if self.num_entries >= self.table_size:
            raise ValueError("KDIC hash table must contain an empty slot")
        if not math.isfinite(self.default_cost) or not math.isfinite(self.unknown_cost):
            raise ValueError("KDIC costs must be finite")
        table_end = _HEADER.size + self.table_size * _TABLE_ENTRY.size
        if table_end > len(data):
            raise ValueError("KDIC hash table is truncated")
        pool_end = extension_offset if self.version >= 2 and extension_offset else len(data)
        if not table_end <= pool_end <= len(data):
            raise ValueError("invalid KDIC extension offset")
        self._data = data
        self._pool_start = table_end
        self._pool_end = pool_end
        self.words: dict[str, KDictWord] = {}
        self.typo_corrections: dict[str, str] = {}

        if self.version >= 2:
            if not extension_offset:
                raise ValueError("KDIC v2 requires a metadata extension")
            self._read_extension(extension_offset)
        else:
            self._read_v1_words()
        if sum(1 for index in range(self.table_size) if _TABLE_ENTRY.unpack_from(
            self._data, _HEADER.size + index * _TABLE_ENTRY.size
        )[0]) != self.num_entries:
            raise ValueError("KDIC entry count does not match the hash table")

    @classmethod
    def load(cls, path: str | Path) -> "KDict":
        return cls(Path(path).read_bytes())

    def _string(self, offset: int) -> str:
        start = self._pool_start + offset
        if not self._pool_start <= start < self._pool_end:
            raise ValueError("KDIC string offset is outside the pool")
        end = self._data.find(b"\0", start, self._pool_end)
        if end < 0:
            raise ValueError("unterminated KDIC string")
        return self._data[start:end].decode("utf-8")

    def _read_v1_words(self) -> None:
        for index in range(self.table_size):
            offset, cost = _TABLE_ENTRY.unpack_from(
                self._data, _HEADER.size + index * _TABLE_ENTRY.size
            )
            if offset:
                word = self._string(offset)
                self.words[word] = KDictWord(
                    word, SEGMENT | SPELLCHECK | AUTOCOMPLETE, cost
                )

    def _read_extension(self, offset: int) -> None:
        if offset + _EXTENSION_HEADER.size > len(self._data):
            raise ValueError("KDIC extension is truncated")
        magic, version, word_count, typo_count = _EXTENSION_HEADER.unpack_from(
            self._data, offset
        )
        if magic != b"KDX2" or version != 1:
            raise ValueError("unsupported KDIC extension")
        cursor = offset + _EXTENSION_HEADER.size
        required = cursor + word_count * _WORD_RECORD.size + typo_count * _TYPO_RECORD.size
        if required > len(self._data):
            raise ValueError("KDIC metadata records are truncated")
        for _ in range(word_count):
            word_offset, flags, cost = _WORD_RECORD.unpack_from(self._data, cursor)
            cursor += _WORD_RECORD.size
            word = self._string(word_offset)
            if word in self.words:
                raise ValueError(f"duplicate KDIC lexical record: {word!r}")
            if not math.isfinite(cost):
                raise ValueError(f"invalid KDIC lexical record: {word!r}")
            self.words[word] = KDictWord(word, flags, cost)
        for _ in range(typo_count):
            typed_offset, correction_offset = _TYPO_RECORD.unpack_from(self._data, cursor)
            cursor += _TYPO_RECORD.size
            typed = self._string(typed_offset)
            correction = self._string(correction_offset)
            if typed in self.typo_corrections:
                raise ValueError(f"duplicate KDIC typo correction: {typed!r}")
            self.typo_corrections[typed] = correction


def _djb2_hash(word: str) -> int:
    value = 5381
    for byte in word.encode("utf-8"):
        value = ((value << 5) + value + byte) & 0xFFFFFFFF
    return value


def _clean_word(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
    )


def compile_klex(
    source_path: str | Path,
    output_path: str | Path,
    *,
    base_path: str | Path | None = None,
) -> Path:
    """Compile a single editable KLEX JSON source into a KDIC v2 pack."""

    source_path = Path(source_path)
    output_path = Path(output_path)
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if source.get("version") != 1 or not isinstance(source.get("entries"), list):
        raise ValueError("KLEX requires version 1 and an entries array")

    use_flags = {
        "segmentation": SEGMENT,
        "spelling": SPELLCHECK,
        "autocomplete": AUTOCOMPLETE,
        "typo": TYPO_SURFACE,
        "supplemental": SUPPLEMENTAL,
    }
    base = KDict.load(base_path) if base_path is not None else None
    if base is not None and base.version < 2:
        raise ValueError("KLEX overlays require a KDIC v2 base pack")
    flags_by_word: dict[str, int] = (
        {word: record.flags for word, record in base.words.items()} if base else {}
    )
    base_costs: dict[str, float] = (
        {word: record.cost for word, record in base.words.items()} if base else {}
    )
    counts: dict[str, float] = {}
    overlay_words: set[str] = set()
    corrections: dict[str, str] = dict(base.typo_corrections) if base else {}
    overlay_corrections: dict[str, str] = {}
    for index, record in enumerate(source["entries"], start=1):
        if not isinstance(record, dict):
            raise ValueError(f"KLEX entry {index} must be an object")
        word = _clean_word(record.get("word"))
        uses = record.get("uses", [])
        if not word or not isinstance(uses, list) or not uses:
            raise ValueError(f"KLEX entry {index} requires word and uses")
        unknown_uses = set(uses) - set(use_flags)
        if unknown_uses:
            raise ValueError(f"KLEX entry {index} has unknown uses: {sorted(unknown_uses)}")
        flags = sum(use_flags[use] for use in set(uses))
        overlay_words.add(word)
        if flags & SUPPLEMENTAL:
            flags |= SEGMENT
        if flags & AUTOCOMPLETE and not flags & SPELLCHECK:
            raise ValueError(f"KLEX entry {index}: autocomplete requires spelling")
        frequency = float(record.get("frequency", 0) or 0)
        if not math.isfinite(frequency) or frequency < 0:
            raise ValueError(f"KLEX entry {index}: frequency must be finite and non-negative")
        counts[word] = max(counts.get(word, 0), frequency)
        if flags & TYPO_SURFACE:
            if record.get("status", "approved") == "approved":
                correction = _clean_word(record.get("correction"))
                if not correction or correction == word:
                    raise ValueError(f"KLEX entry {index}: typo requires a different correction")
                previous = overlay_corrections.get(word)
                if previous is not None and previous != correction:
                    raise ValueError(f"conflicting KLEX correction for {word!r}")
                overlay_corrections[word] = correction
                corrections[word] = correction
            else:
                flags &= ~TYPO_SURFACE
        flags_by_word[word] = flags_by_word.get(word, 0) | flags

    for typed, correction in corrections.items():
        if not flags_by_word.get(correction, 0) & SPELLCHECK:
            raise ValueError(
                f"KLEX correction {typed!r} -> {correction!r} must target a spelling entry"
            )

    floor = 5.0
    if base is not None:
        default_cost = base.default_cost
        unknown_cost = base.unknown_cost
        total = floor * (10**default_cost)
        costs = dict(base_costs)
        costs.update(
            {
                word: -math.log10(max(counts.get(word, 0), floor) / total)
                for word in overlay_words
                if word not in base_costs
            }
        )
    else:
        total = sum(max(count, floor) for count in counts.values()) or floor
        default_cost = -math.log10(floor / total)
        unknown_cost = default_cost + 5.0
        costs = {
            word: -math.log10(max(counts.get(word, 0), floor) / total)
            for word in flags_by_word
        }
    segmentation_words = {
        word for word, flags in flags_by_word.items() if flags & SEGMENT
    }
    table_size = 1
    required_size = max(2, math.ceil(len(segmentation_words) / 0.70))
    while table_size < required_size:
        table_size <<= 1

    metadata_words = set(flags_by_word) | set(corrections) | set(corrections.values())
    pool = bytearray(b"\0")
    offsets: dict[str, int] = {}
    for word in sorted(metadata_words):
        offsets[word] = len(pool)
        pool.extend(word.encode("utf-8") + b"\0")

    table: list[tuple[int, float]] = [(0, 0.0)] * table_size
    for word in sorted(segmentation_words):
        slot = _djb2_hash(word) & (table_size - 1)
        while table[slot][0]:
            slot = (slot + 1) & (table_size - 1)
        table[slot] = (offsets[word], costs[word])

    extension_offset = _HEADER.size + table_size * _TABLE_ENTRY.size + len(pool)
    output = bytearray(
        _HEADER.pack(
            b"KDIC",
            2,
            len(segmentation_words),
            table_size,
            default_cost,
            unknown_cost,
            max((len(word.encode("utf-8")) for word in segmentation_words), default=0),
            extension_offset,
        )
    )
    for offset, cost in table:
        output.extend(_TABLE_ENTRY.pack(offset, cost))
    output.extend(pool)
    output.extend(_EXTENSION_HEADER.pack(b"KDX2", 1, len(flags_by_word), len(corrections)))
    for word in sorted(flags_by_word):
        output.extend(_WORD_RECORD.pack(offsets[word], flags_by_word[word], costs[word]))
    for typed, correction in sorted(corrections.items()):
        output.extend(_TYPO_RECORD.pack(offsets[typed], offsets[correction]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)
    return output_path
