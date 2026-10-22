from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
from octatrack_kb.retrieval import Retriever


def test_load_guides_maps_modes_and_sources():
    guides = load_guides("tests/fixtures/guides")
    g = {x.id: x for x in guides}["morph-with-crossfader"]
    assert g.usage_modes == ["live-looper", "groovebox"]   # modes -> usage_modes
    assert g.related == ["scene", "crossfader"]              # sources -> related
    assert "crossfader" in g.body


def _retriever(tmp_path):
    db = tmp_path / "kb.db"
    chunks = load_corpus("tests/fixtures/reference") + load_guides("tests/fixtures/guides")
    build_index(chunks, str(db))
    (tmp_path / "concepts.yaml").write_text(
        "scene:\n  label: Scene\n  definition_chunk: scene\n"
        "  mentioned_in: [scene]\n  related: [crossfader]\n  usage_modes: [live-looper]\n")
    return Retriever(str(db), "tests/fixtures/reference",
                     str(tmp_path / "concepts.yaml"),
                     guides_dir="tests/fixtures/guides")


def test_search_can_surface_guides_with_layer(tmp_path):
    r = _retriever(tmp_path)
    hits = r.search("morph between scenes with crossfader", k=8)
    by_id = {h.id: h for h in hits}
    assert "morph-with-crossfader" in by_id
    assert by_id["morph-with-crossfader"].layer == "guide"


def test_list_and_get_workflow(tmp_path):
    r = _retriever(tmp_path)
    wfs = {w["id"]: w for w in r.list_workflows()}
    assert "morph-with-crossfader" in wfs
    assert "live-looper" in wfs["morph-with-crossfader"]["modes"]
    full = r.get_workflow("morph-with-crossfader")
    assert full["sources"] == ["scene", "crossfader"]
    assert "Steps" in full["body"]


def test_list_usage_modes_and_by_usage_mode(tmp_path):
    r = _retriever(tmp_path)
    modes = r.list_usage_modes()
    assert "live-looper" in {m["mode"] for m in modes}
    members = r.by_usage_mode("live-looper")
    assert "morph-with-crossfader" in {m["id"] for m in members}


def test_compare_approaches_returns_guides(tmp_path):
    r = _retriever(tmp_path)
    res = r.compare_approaches("morph between scenes", k=3)
    assert any(a["id"] == "morph-with-crossfader" for a in res)
    assert all("modes" in a for a in res)
