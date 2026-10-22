# octatrack-kb

Code for building a local knowledge base from the Elektron Octatrack manual and serving it to AI clients through a FastMCP server.

**This repository contains code only. The knowledge base is NOT included.** The manual is copyrighted by Elektron Music Machines; no manual text, page images, extracted sections, generated guides or search indexes are distributed here. To use the server you must build the KB yourself from your own legally obtained copy of the Octatrack manual PDF.

Not affiliated with, endorsed by, or sponsored by Elektron. Octatrack is a trademark of Elektron Music Machines. All trademarks are the property of their respective owners.

## Pipeline

Manual PDF -> page PNG + text layer -> per-page Markdown (vision model via `claude` CLI) -> section chunks -> concept tags -> concept graph -> task guides -> SQLite index -> MCP server.

| Layer | Path (created by you, gitignored) |
|-------|------|
| Reference chunks | `knowledge/reference/*.md` |
| Concept graph | `knowledge/concepts.yaml`, `knowledge/INDEX.md` |
| Guides | `knowledge/guides/*.md` |
| Index | `server/kb.db` (sqlite-vec + FTS5; embeddings `BAAI/bge-small-en-v1.5` on CPU) |

Schemas: [`docs/SCHEMAS.md`](docs/SCHEMAS.md). Script details: [`build/README.md`](build/README.md), [`docs/BUILDING.md`](docs/BUILDING.md), [`docs/REPLICATION.md`](docs/REPLICATION.md).

## Requirements

- Python >= 3.12, [`uv`](https://docs.astral.sh/uv/)
- `claude` CLI with `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) for the model-driven build steps (extract, tag, reconcile, guides). The scripts strip `ANTHROPIC_API_KEY` from the subprocess env.
- Your own copy of the Octatrack manual PDF

## Build the KB yourself

```bash
uv sync
mkdir -p build/artifacts && cp /path/to/your/octatrack-manual.pdf build/artifacts/oct.pdf
export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < /path/to/token-file)"

# 1. Section map -> build/inputs/toc.yaml
uv run python build/tools/build_toc.py

# 2. Render pages (PNG + text layer) -> build/artifacts/pages/
uv run python -c "from build.render import render_pdf; render_pdf('build/artifacts/oct.pdf','build/artifacts/pages')"

# 3. Per-page extraction -> build/artifacts/extracted/ (resumable)
uv run python -m build.extract build/artifacts/pages build/artifacts/extracted build/inputs/prompts/extract_page.md

# 4. Assemble section chunks -> knowledge/reference/
uv run python -c "from build.assemble import assemble; assemble('build/artifacts/extracted','build/inputs/toc.yaml','knowledge/reference')"

# 5. Tag concepts (needs build/inputs/concept-glossary.yaml, see below)
uv run python -m build.tag knowledge/reference build/inputs/concept-glossary.yaml

# 6. Reconcile slugs
uv run python -m build.reconcile generate
uv run python -m build.reconcile apply

# 7. Concept graph -> knowledge/concepts.yaml, knowledge/INDEX.md
uv run python -c "from octatrack_kb.corpus import load_corpus; from octatrack_kb.build_index_files import build_concepts, build_index_md; ch=load_corpus('knowledge/reference'); c=build_concepts(ch,'knowledge/concepts.yaml'); build_index_md(c,'knowledge/INDEX.md')"

# 8. Guides (needs build/inputs/spine-guides.yaml, see below) -> knowledge/guides/
uv run python -m build.guides

# 9. Search index -> server/kb.db
uv run python -c "from octatrack_kb.corpus import load_corpus, load_guides; from octatrack_kb.index import build_index; build_index(load_corpus('knowledge/reference')+load_guides('knowledge/guides'),'server/kb.db')"
```

Inputs you must author yourself (not shipped, they derive from the manual):

- `build/inputs/concept-glossary.yaml`: map of `slug -> {label, aliases}` seed for the tagger (`build/tools/seed_glossary.py` can seed it from your own usage-mode notes).
- `build/inputs/spine-guides.yaml`: list of `{id, description, modes, concepts}` guide specs (`build/tools/parse_spine_guides.py` can parse a Markdown table of your own).

Every stage skips outputs that already exist, so interrupted runs resume. Expect the model-driven stages to consume subscription quota.

## Run the MCP server

Env vars (see [`server/README.md`](server/README.md)): `OCTATRACK_DB`, `OCTATRACK_REFERENCE`, `OCTATRACK_CONCEPTS`, `OCTATRACK_GUIDES` (optional).

```bash
OCTATRACK_DB=$PWD/server/kb.db OCTATRACK_REFERENCE=$PWD/knowledge/reference \
OCTATRACK_CONCEPTS=$PWD/knowledge/concepts.yaml OCTATRACK_GUIDES=$PWD/knowledge/guides \
uv run python -m server.octatrack_mcp
```

Tools: `search`, `get_chunk`, `get_concept`, `list_workflows`, `get_workflow`, `list_usage_modes`, `by_usage_mode`, `compare_approaches`. No generative AI runs at query time.

## Register with an MCP client

Claude Code / any stdio client: copy [`server/config.example.json`](server/config.example.json) and replace `/ABSOLUTE/PATH/TO/octatrack-kb`. Claude Code shortcut: run `docs/install.sh` from the target project directory (writes `./.claude/mcp.json`). Claude Desktop: see [`docs/INSTALL.md`](docs/INSTALL.md).

## Tests

```bash
uv run --extra dev pytest -q
```

Tests use small synthetic fixtures in `tests/fixtures/`; they do not need the manual.

## License

MIT, see [`LICENSE`](LICENSE). The license covers this code only, not the Octatrack manual or anything derived from it.
