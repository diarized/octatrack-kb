from octatrack_kb.corpus import load_corpus

def test_load_fixture_corpus():
    chunks = load_corpus("tests/fixtures/reference")
    by_id = {c.id: c for c in chunks}
    assert "scene" in by_id and "crossfader" in by_id
    assert by_id["scene"].chapter == 8
    assert "crossfader" in by_id["scene"].concepts

def test_load_rejects_invalid_chunk(tmp_path):
    (tmp_path / "bad.md").write_text("---\nid: bad\n---\nbody")  # missing keys
    import pytest
    with pytest.raises(ValueError, match="bad.md"):
        load_corpus(str(tmp_path))
