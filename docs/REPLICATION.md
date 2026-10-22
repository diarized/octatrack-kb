# Replicating this KB for a Different Manual

This guide is for someone who wants to build a new knowledge base — for a different synthesizer, effects unit, or any structured PDF manual — using the same pipeline that produced the Octatrack KB.

Some of these steps require model calls (extraction, tagging, guide authoring) and benefit from technical familiarity with the command line. The heavy AI work happens **once**, producing static files. After that, running the server is cheap and local.

---

## The three-layer model

```
Layer 1 — Reference chunks (knowledge/reference/)
    Per-section Markdown files extracted from the source PDF.
    One file per numbered section; YAML frontmatter carries id, source pages, concepts, usage modes.

Layer 2 — Concept graph (knowledge/concepts.yaml + knowledge/INDEX.md)
    168+ canonical concept slugs inverted from chunk frontmatter.
    Deterministic — no model calls; regenerated from the chunks.

Layer 3 — Workflow guides (knowledge/guides/)
    Task-oriented micro-guides authored by Claude from source chunks.
    Each guide cites the reference sections it draws from.
```

**Core principle:** all expensive AI work (vision extraction, concept tagging, guide authoring) happens once at build time. The result is frozen into plain Markdown files. At query time, the MCP server runs local hybrid search (sqlite-vec + FTS5) with no generative AI — only the chat model calling the tools costs anything.

---

## What is manual-specific (must be redone per manual)

| Artifact | Location | What it captures |
|----------|----------|-----------------|
| Source PDF | `build/artifacts/oct.pdf` | The manual itself (gitignored) |
| Section map | `build/inputs/toc.yaml` | Chapter/section boundaries → page ranges |
| Extraction prompt | `build/inputs/prompts/extract_page.md` | How to read each page image (device-specific terminology hints) |
| Usage-mode vocabulary | `build/inputs/spine-guides.yaml` | Operating modes meaningful for this device |
| Spine guide list | `build/inputs/spine-guides.yaml` | 30 (or N) high-value task guides to author |
| Concept glossary seed | `build/inputs/concept-glossary.yaml` | Starting slug list for the tagger |

Everything else in `octatrack_kb/`, `server/`, and the pipeline scripts is generic and reusable without modification.

---

## Auth (critical — read before starting)

The model-driven pipeline steps (extract, tag, reconcile, guide authoring) call Claude through the `claude` CLI in headless mode:

```bash
claude -p --output-format json ...
```

**These calls use a Claude subscription OAuth token, not the metered Messages API.**

- Env var: `CLAUDE_CODE_OAUTH_TOKEN`
- Obtain it with: `claude setup-token` (requires a Claude Pro/Team subscription)
- Do NOT set `ANTHROPIC_API_KEY` alongside it — the build scripts pop it from the subprocess environment, but having it in your shell risks accidental metered calls in other tools

Inject the token for any model phase:

```bash
export CLAUDE_CODE_OAUTH_TOKEN="your-token-here"
# or from a key file:
export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < /path/to/your.key)"
```

**Rate limits:** long extraction and tagging runs will hit the subscription quota ceiling. Symptom: a burst of fast failures after N successes. Recovery: wait for the rate window to reset and re-run. Every pipeline stage is **idempotent** — it skips already-produced outputs — so re-running resumes exactly where it stopped.

---

## Cost and complexity

| Phase | Work type | Cost | Time |
|-------|-----------|------|------|
| Render | Local (Poppler) | Free | ~1 min |
| Extract | Vision model, 1 call/page | Subscription (rate-limited) | Hours to days depending on PDF length and rate limits |
| Assemble | Pure Python | Free | Seconds |
| Tag | LLM, 1–2 calls/chunk | Subscription (rate-limited) | 10–60 min |
| Reconcile | LLM (1 call) + Python | Negligible | Minutes |
| Build concept index | Pure Python | Free | Seconds |
| Author guides | LLM, 2–3 calls/guide | Subscription | 30–90 min |
| Build search index | Local (CPU embeddings) | Free | 1–2 min |
| Run server | Local retrieval only | Free | — |

Extraction and tagging are the expensive, rate-limited parts. Everything else is fast.

---

## Pipeline steps

Work through these in order. For exhaustive detail on each step, see [`docs/BUILDING.md`](BUILDING.md).

### Step 1 — Prepare source material

Place the PDF at `build/artifacts/oct.pdf` (gitignored). A local copy is mandatory — network-mounted files cause I/O errors when the vision model reads deep pages.

### Step 2 — Render pages

Rasterize the PDF to per-page PNGs and extract text layers (used as OCR hints during extraction).

```bash
uv run python -m build.render build/artifacts/oct.pdf build/artifacts/pages
```

Outputs: `build/artifacts/pages/page-NNNN.png`, `page-NNNN.txt`, `manifest.json`.

### Step 3 — Build the section map (toc.yaml)

`build/inputs/toc.yaml` maps each section (`id`, `title`, `chapter`, `section`, `pages: [start, end]`) across all chapters of your manual.

The helper script `build/tools/build_toc.py` scans page text layers for `N.M Title` headings:

```bash
uv run python -m build.tools.build_toc build/artifacts/pages build/inputs/toc.yaml
```

Review and manually correct the output — the heuristic works well but may miss or duplicate headings in unusual layouts. This file is the authoritative source of truth for chapter/section boundaries.

### Step 4 — Manual analysis (usage modes + guide candidates)

Before extraction, analyse the manual to define:

- **Usage modes** — the distinct operating contexts of the device (e.g., `sampler`, `sequencer`, `fx-processor`). These become the controlled vocabulary for tagging.
- **Spine guide candidates** — 20–40 high-value tasks worth a dedicated workflow guide.

Write these up in your own notes (a `docs/usage-modes.md` of your own is optional). Then encode them in `build/inputs/spine-guides.yaml` (one entry per guide: `id`, `description`, `modes`, `concepts`).

Seed the concept glossary from your usage-modes analysis:

```bash
uv run python -m build.tools.seed_glossary docs/usage-modes.md build/inputs/concept-glossary.yaml
```

### Step 5 — Write the extraction prompt

Edit `build/inputs/prompts/extract_page.md` to capture device-specific terminology, diagram types, and layout conventions for your manual. This prompt is sent with each page image; device-specific hints improve extraction accuracy significantly.

### Step 6 — Extract pages

One model call per page. Reads `build/artifacts/pages/manifest.json`, writes `build/artifacts/extracted/page-NNNN.md`. Skips pages that already have an output file.

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." \
  nohup uv run python -m build.extract \
    build/artifacts/pages \
    build/artifacts/extracted \
    build/inputs/prompts/extract_page.md \
  > build/logs/extract.log 2>&1 &
```

Monitor progress:

```bash
ls build/artifacts/extracted/*.md | wc -l   # compare to total page count
tail -20 build/logs/extract.log
```

### Step 7 — Assemble reference chunks

Stitch per-page Markdown into per-section files using `build/inputs/toc.yaml` page ranges. Outputs to `knowledge/reference/`.

```bash
uv run python -c "
from build.assemble import assemble
assemble('build/artifacts/extracted', 'build/inputs/toc.yaml', 'knowledge/reference')
"
```

### Step 8 — Tag concepts

Tag each reference chunk with concept slugs. Uses two-tier model routing (Sonnet default, Opus for difficult chunks). Skips chunks that already have a non-empty `concepts:` field.

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." \
  uv run python -m build.tag knowledge/reference build/inputs/concept-glossary.yaml
```

### Step 9 — Reconcile slugs

The tagger mints new slugs freely. Reconcile merges synonyms and drops OCR noise:

```bash
# Step 1: LLM proposes alias→canonical map
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.reconcile generate

# Step 2: Pure Python applies the map to all chunk frontmatter
uv run python -m build.reconcile apply
```

### Step 10 — Build concept index

Invert chunk frontmatter into the concept graph. Deterministic, no model calls.

```bash
uv run python -m octatrack_kb.build_index_files
```

Outputs: `knowledge/concepts.yaml`, `knowledge/INDEX.md`.

### Step 11 — Author workflow guides

Three-call pipeline per guide (Author → Review → Revise). Skips existing `knowledge/guides/<id>.md` files.

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.guides
```

### Step 12 — Build the search index

Local embedding + FTS5 index. Downloads the embedding model on first run (~90 MB, cached).

```bash
uv run python -c "
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
build_index(
    load_corpus('knowledge/reference') + load_guides('knowledge/guides'),
    'server/kb.db'
)
"
```

### Step 13 — Run the server

Follow [`docs/INSTALL.md`](INSTALL.md) to register the server with Claude Desktop. No further changes needed — the server reads the paths from env vars.

---

## Adapting the scripts

Most pipeline scripts accept paths as arguments or use configurable defaults. The manual-specific knobs are all in `build/inputs/`:

- `toc.yaml` — section boundaries (drives assemble)
- `concept-glossary.yaml` — slug vocabulary (drives tag and reconcile)
- `spine-guides.yaml` — guide specifications (drives guides.py)
- `prompts/extract_page.md` — extraction prompt (drives extract.py)

The `octatrack_kb/` package (schema, corpus loader, index builder, retrieval) and `server/octatrack_mcp.py` are generic — they work for any KB built to this schema. Rename `OCTATRACK_*` env vars to match your device if you want, but the server code will need a matching update.

---

## Cross-references

- [`docs/BUILDING.md`](BUILDING.md) — exhaustive phase-by-phase build log with exact commands, model history, and debugging notes
- [`docs/SCHEMAS.md`](SCHEMAS.md) — YAML frontmatter schemas for reference chunks and guides
- [`docs/INSTALL.md`](INSTALL.md) — end-user Claude Desktop setup
- [`server/README.md`](../server/README.md) — MCP tool reference
