from octatrack_kb.corpus import load_corpus
from octatrack_kb.index import build_index
from octatrack_kb.retrieval import Retriever


def _retriever(tmp_path):
    chunks = load_corpus("tests/fixtures/reference")
    db = tmp_path / "kb.db"
    build_index(chunks, str(db))
    concepts_yaml = tmp_path / "concepts.yaml"
    concepts_yaml.write_text(
        "scene:\n  label: Scene\n  definition_chunk: scene\n"
        "  mentioned_in: [scene, crossfader]\n  related: [crossfader]\n"
        "  usage_modes: [live-looper]\n"
    )
    return Retriever(str(db), "tests/fixtures/reference", str(concepts_yaml))


def test_search_finds_relevant_chunk(tmp_path):
    r = _retriever(tmp_path)
    hits = r.search("morph between two snapshots with the fader", k=2)
    assert hits[0].id in {"scene", "crossfader"}


def test_get_concept_returns_correlated_chunks(tmp_path):
    r = _retriever(tmp_path)
    c = r.get_concept("scene")
    assert c["definition_chunk"] == "scene"
    assert set(c["mentioned_in"]) == {"scene", "crossfader"}
    assert "crossfader" in c["related"]


def test_correlation_query(tmp_path):
    r = _retriever(tmp_path)
    hits = r.search("crossfader morphs between scene A and scene B snapshots", k=2)
    ids = {h.id for h in hits}
    assert ids == {"scene", "crossfader"}


def test_hyphenated_concept_boost_fires(tmp_path):
    r = _retriever(tmp_path)
    # "parameter lock" appears only as the hyphenated concept slug on `scene`;
    # the boost must fire so scene ranks for this phrase.
    hits = r.search("parameter lock automation", k=2)
    assert any(h.id == "scene" for h in hits)
