"""Load + validate reference chunks from a directory of frontmatter .md files."""
from __future__ import annotations
import pathlib, sys
import frontmatter
from .schema import Chunk, validate_chunk_meta


def load_corpus(reference_dir: str) -> list[Chunk]:
    chunks = []
    for path in sorted(pathlib.Path(reference_dir).glob("*.md")):
        post = frontmatter.load(path)
        problems = validate_chunk_meta(post.metadata)
        fatal = [p for p in problems if "unknown usage_mode" not in p]
        if fatal:
            raise ValueError(f"{path.name}: {'; '.join(fatal)}")
        for p in problems:
            if "unknown usage_mode" in p:
                print(f"warning: {path.name}: {p}", file=sys.stderr)
        m = post.metadata
        chunks.append(Chunk(
            id=m["id"], title=m["title"], chapter=m["chapter"],
            source_pages=m["source_pages"], concepts=m["concepts"],
            body=post.content, section=m.get("section"),
            usage_modes=m.get("usage_modes", []), related=m.get("related", []),
        ))
    return chunks


def load_guides(guides_dir: str) -> list[Chunk]:
    """Load spine micro-guides as Chunk objects (the workflow layer).

    Guides have a different frontmatter shape than reference sections, so we map
    them onto Chunk: `modes` -> usage_modes, `sources` -> related (the reference
    chunk ids they cite). chapter=0 / source_pages=[] flag the synthesized layer.
    """
    guides = []
    for path in sorted(pathlib.Path(guides_dir).glob("*.md")):
        post = frontmatter.load(path)
        m = post.metadata
        guides.append(Chunk(
            id=m["id"], title=m["title"], chapter=0, source_pages=[],
            concepts=m.get("concepts", []), body=post.content, section=None,
            usage_modes=m.get("modes", []), related=m.get("sources", []),
        ))
    return guides
