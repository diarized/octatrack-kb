"""Canonical data schemas for the Octatrack KB.

MAGIC: chunk identity is the `id` field (kebab-case), NOT the filename — the
loader trusts frontmatter `id`, so a chunk can be renamed on disk without
breaking concept-graph links. `related` holds chunk ids (see-also between
sections); concept-to-concept relationships live in concepts.yaml, not here.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# Controlled vocabulary for usage_modes. Finalized by the Phase 0 analysis
# (Task 2) which may extend this list.
USAGE_MODES = {
    "sampler", "sequencer", "groovebox", "live-looper",
    "midi-sequencer", "midi-controller", "fx-processor", "mixer",
}

REQUIRED_CHUNK_KEYS = {"id", "title", "chapter", "source_pages", "concepts"}


@dataclass
class Chunk:
    id: str
    title: str
    chapter: int
    source_pages: list[int]
    concepts: list[str]
    body: str
    section: str | None = None
    usage_modes: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)


def validate_chunk_meta(meta: dict) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    problems = []
    missing = REQUIRED_CHUNK_KEYS - meta.keys()
    if missing:
        problems.append(f"missing required keys: {sorted(missing)}")
    if "id" in meta and not isinstance(meta["id"], str):
        problems.append("id must be a string")
    for m in meta.get("usage_modes", []):
        if m not in USAGE_MODES:
            problems.append(f"unknown usage_mode: {m!r}")
    sp = meta.get("source_pages")
    if sp is not None and (not isinstance(sp, list) or not all(isinstance(p, int) for p in sp)):
        problems.append("source_pages must be a list of ints")
    return problems
