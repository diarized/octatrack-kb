"""Invert chunk frontmatter into concepts.yaml + a human INDEX.md.

MAGIC: a concept's definition_chunk is the chunk whose id == the concept slug
if it exists, else the first (lowest chapter) chunk that tags it. mentioned_in
is every chunk tagging the concept; related is the union of co-tagged concepts.
"""
from __future__ import annotations
import yaml
from .schema import Chunk


def build_concepts(chunks: list[Chunk], out_path: str) -> dict:
    by_id = {c.id: c for c in chunks}
    concepts: dict[str, dict] = {}
    for c in sorted(chunks, key=lambda c: c.chapter):
        for slug in c.concepts:
            e = concepts.setdefault(slug, {
                "label": slug.replace("-", " ").title(),
                "definition_chunk": None, "mentioned_in": [],
                "related": set(), "usage_modes": set()})
            e["mentioned_in"].append(c.id)
            e["related"].update(x for x in c.concepts if x != slug)
            e["usage_modes"].update(c.usage_modes)
            if e["definition_chunk"] is None:
                e["definition_chunk"] = slug if slug in by_id else c.id
    for e in concepts.values():
        e["related"] = sorted(e["related"])
        e["usage_modes"] = sorted(e["usage_modes"])
    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(concepts, fh, sort_keys=True, allow_unicode=True)
    return concepts


def build_index_md(concepts: dict, out_path: str) -> None:
    lines = ["# Concept Index\n"]
    for slug in sorted(concepts):
        e = concepts[slug]
        lines.append(f"- **{e['label']}** (`{slug}`) — defined in "
                     f"`{e['definition_chunk']}`; see also "
                     f"{', '.join(e['related']) or '—'}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
