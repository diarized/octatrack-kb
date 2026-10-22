"""Parse the Task 2 spine micro-guide table into build/inputs/spine-guides.yaml.

MAGIC: docs/usage-modes.md "## 2. Spine micro-guide candidate list" is the source
of truth. We parse its markdown table (id | desc | modes | concepts) so Task 15's
guide authoring stays in sync with the analysis instead of hand-duplicating it.
"""
from __future__ import annotations
import pathlib
import re
import yaml

_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")


def _split(cell: str) -> list[str]:
    return [t.strip().strip("`") for t in cell.split(",") if t.strip()]


def parse_spine_guides(usage_modes_path: str, out_path: str) -> list[dict]:
    guides = []
    for line in pathlib.Path(usage_modes_path).read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        slug, desc, modes, concepts = m.groups()
        if slug == "id":  # header row
            continue
        guides.append({
            "id": slug,
            "description": desc.strip(),
            "modes": _split(modes),
            "concepts": _split(concepts),
        })
    pathlib.Path(out_path).write_text(
        yaml.safe_dump(guides, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return guides


if __name__ == "__main__":
    import sys
    g = parse_spine_guides(
        sys.argv[1] if len(sys.argv) > 1 else "docs/usage-modes.md",
        sys.argv[2] if len(sys.argv) > 2 else "build/inputs/spine-guides.yaml",
    )
    print(f"parsed {len(g)} spine guides")
