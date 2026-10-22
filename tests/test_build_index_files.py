from octatrack_kb.corpus import load_corpus
from octatrack_kb.build_index_files import build_concepts, build_index_md
import yaml


def test_build_concepts_inverts_frontmatter(tmp_path):
    chunks = load_corpus("tests/fixtures/reference")
    out = tmp_path / "concepts.yaml"
    build_concepts(chunks, str(out))
    data = yaml.safe_load(out.read_text())
    assert "scene" in data
    assert "scene" in data["scene"]["mentioned_in"]
    assert "crossfader" in data["scene"]["mentioned_in"]  # crossfader tags scene


def test_definition_chunk_prefers_eponymous_chunk(tmp_path):
    chunks = load_corpus("tests/fixtures/reference")
    out = tmp_path / "concepts.yaml"
    data = build_concepts(chunks, str(out))
    # a chunk whose id == slug is the canonical definition
    assert data["scene"]["definition_chunk"] == "scene"
    assert data["crossfader"]["definition_chunk"] == "crossfader"


def test_related_is_union_of_cotagged(tmp_path):
    chunks = load_corpus("tests/fixtures/reference")
    data = build_concepts(chunks, str(tmp_path / "c.yaml"))
    # scene is co-tagged with crossfader and parameter-lock
    assert "crossfader" in data["scene"]["related"]
    assert "parameter-lock" in data["scene"]["related"]
    assert "scene" not in data["scene"]["related"]  # never itself


def test_build_index_md_lists_every_concept(tmp_path):
    chunks = load_corpus("tests/fixtures/reference")
    concepts = build_concepts(chunks, str(tmp_path / "c.yaml"))
    md = tmp_path / "INDEX.md"
    build_index_md(concepts, str(md))
    text = md.read_text()
    for slug in concepts:
        assert f"`{slug}`" in text
