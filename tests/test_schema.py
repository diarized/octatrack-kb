from octatrack_kb.schema import validate_chunk_meta

def test_valid_meta_has_no_problems():
    meta = {"id": "scene", "title": "Scene", "chapter": 8,
            "source_pages": [157, 165], "concepts": ["scene"],
            "usage_modes": ["live-looper"]}
    assert validate_chunk_meta(meta) == []

def test_missing_required_key_reported():
    problems = validate_chunk_meta({"id": "x"})
    assert any("missing required keys" in p for p in problems)

def test_unknown_usage_mode_reported():
    meta = {"id": "x", "title": "X", "chapter": 1,
            "source_pages": [1], "concepts": [], "usage_modes": ["nonsense"]}
    problems = validate_chunk_meta(meta)
    assert any("unknown usage_mode" in p for p in problems)
