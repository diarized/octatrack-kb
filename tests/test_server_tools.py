import os
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index

def test_tool_functions_wired(tmp_path, monkeypatch):
    db = tmp_path / "kb.db"
    chunks = load_corpus("tests/fixtures/reference") + load_guides("tests/fixtures/guides")
    build_index(chunks, str(db))
    (tmp_path / "concepts.yaml").write_text(
        "scene:\n  label: Scene\n  definition_chunk: scene\n"
        "  mentioned_in: [scene]\n  related: [crossfader]\n  usage_modes: []\n")
    monkeypatch.setenv("OCTATRACK_DB", str(db))
    monkeypatch.setenv("OCTATRACK_REFERENCE", "tests/fixtures/reference")
    monkeypatch.setenv("OCTATRACK_CONCEPTS", str(tmp_path / "concepts.yaml"))
    monkeypatch.setenv("OCTATRACK_GUIDES", "tests/fixtures/guides")
    import importlib, server.octatrack_mcp as srv
    importlib.reload(srv)
    assert srv.search("crossfader morph")            # returns non-empty list
    assert srv.get_chunk("scene")["id"] == "scene"
    assert srv.get_concept("scene")["definition_chunk"] == "scene"
    # workflow + usage-mode tools
    assert any(w["id"] == "morph-with-crossfader" for w in srv.list_workflows())
    assert srv.get_workflow("morph-with-crossfader")["modes"]
    assert any(m["mode"] == "live-looper" for m in srv.list_usage_modes())
    assert any(x["id"] == "morph-with-crossfader"
               for x in srv.by_usage_mode("live-looper"))
    assert srv.compare_approaches("morph between scenes")
