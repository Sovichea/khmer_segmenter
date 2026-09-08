import json
from pathlib import Path

from khmer_segmenter import KhmerSegmenter, compile_klex
from khmer_segmenter.kdict import AUTOCOMPLETE, SEGMENT, SPELLCHECK, SUPPLEMENTAL, KDict

ROOT = Path(__file__).parents[1]
COMMUNITY = ROOT / "community"


def test_reviewed_community_pack_is_segmentation_only_and_reproducible(tmp_path: Path):
    review = json.loads(
        (COMMUNITY / "panhapich_khmer_text_corpus.review.json").read_text(encoding="utf-8")
    )
    approved = {
        item["word"] if item.get("word") else item["candidate"]
        for item in review
        if item["status"] == "approved"
    }
    rejected = {item["candidate"] for item in review if item["status"] == "rejected"}
    source = COMMUNITY / "panhapich_khmer_text_corpus.klex.json"
    bundled = COMMUNITY / "panhapich_khmer_text_corpus.kdict"
    generated = tmp_path / "community.kdict"
    compile_klex(source, generated)

    assert generated.read_bytes() == bundled.read_bytes()
    pack = KDict.load(bundled)
    assert approved <= set(pack.words)
    assert rejected.isdisjoint(pack.words)
    assert pack.packs[0]["policy"] == "segmentation_only"
    assert pack.sources[0]["dataset"] == "Panhapich/khmer-text-corpus"
    for word in approved:
        flags = pack.words[word].flags
        assert flags & (SEGMENT | SUPPLEMENTAL) == SEGMENT | SUPPLEMENTAL
        assert not flags & (SPELLCHECK | AUTOCOMPLETE)

    segmenter = KhmerSegmenter.from_kdict(bundled)
    assert all(not segmenter.is_spelling_valid(word) for word in approved)
