"""Seed build/inputs/concept-glossary.yaml from the Task 2 usage-mode analysis.

MAGIC: the seed vocabulary is the union of every `**Key concepts:** [...]` list in
docs/usage-modes.md (the 8 mode sections). These are the slugs the tagging pass
starts from; the tagger may mint new ones, which the Opus reconcile later folds in.
Re-running is idempotent and byte-stable (sorted slugs).
"""
from __future__ import annotations
import pathlib
import re
import yaml

_KEY_CONCEPTS = re.compile(r"\*\*Key concepts:\*\*\s*\[([^\]]*)\]", re.DOTALL)


def seed_glossary(usage_modes_path: str, out_path: str) -> dict:
    text = pathlib.Path(usage_modes_path).read_text(encoding="utf-8")
    slugs: set[str] = set()
    for block in _KEY_CONCEPTS.findall(text):
        for tok in block.replace("\n", " ").split(","):
            tok = tok.strip()
            if re.fullmatch(r"[a-z][a-z0-9-]+", tok):
                slugs.add(tok)

    glossary = {
        slug: {"label": slug.replace("-", " ").title(), "aliases": []}
        for slug in sorted(slugs)
    }
    pathlib.Path(out_path).write_text(
        yaml.safe_dump(glossary, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )
    return glossary


if __name__ == "__main__":
    import sys

    g = seed_glossary(
        sys.argv[1] if len(sys.argv) > 1 else "docs/usage-modes.md",
        sys.argv[2] if len(sys.argv) > 2 else "build/inputs/concept-glossary.yaml",
    )
    print(f"seeded {len(g)} concept slugs")
