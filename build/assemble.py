"""Stitch per-page Markdown into section chunks driven by toc.yaml.

MAGIC: toc.yaml page ranges are inclusive. concepts/related/usage_modes are
emitted empty here and populated by the Phase D enrichment pass, so this step
stays deterministic and re-runnable.
"""
from __future__ import annotations
import pathlib
import yaml, frontmatter


def _join_pages(texts: list[str]) -> str:
    # Join a hyphenated line-break across a page boundary; else blank line.
    out = []
    for t in texts:
        t = t.rstrip()
        if out and out[-1].endswith("-"):
            out[-1] = out[-1][:-1] + t.lstrip()
        else:
            out.append(t)
    return "\n\n".join(out)


def assemble(pages_dir: str, toc_path: str, out_dir: str) -> list[str]:
    pages = pathlib.Path(pages_dir)
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    toc = yaml.safe_load(pathlib.Path(toc_path).read_text())
    written = []
    for sec in toc["sections"]:
        lo, hi = sec["pages"]
        texts = []
        for p in range(lo, hi + 1):
            f = pages / f"page-{p:04d}.md"
            if f.exists():
                texts.append(f.read_text(encoding="utf-8"))
        post = frontmatter.Post(_join_pages(texts))
        post["id"] = sec["id"]
        post["title"] = sec["title"]
        post["chapter"] = sec["chapter"]
        post["section"] = sec.get("section")
        post["source_pages"] = [lo, hi]
        post["usage_modes"] = []
        post["concepts"] = []
        post["related"] = []
        dest = out / f"{sec['id']}.md"
        dest.write_text(frontmatter.dumps(post), encoding="utf-8")
        written.append(str(dest))
    return written
