# Octatrack KB — Build History & Extension Guide

## Contents

1. [Source material](#1-source-material)
2. [Auth (critical)](#2-auth-critical)
3. [Phase A — Scaffold & render](#3-phase-a--scaffold--render)
4. [Phase B — TOC & usage-mode analysis](#4-phase-b--toc--usage-mode-analysis)
5. [Phase C — Extraction](#5-phase-c--extraction)
6. [Phase D — Assemble, tag, reconcile, index files](#6-phase-d--assemble-tag-reconcile-index-files)
7. [Phase E — Micro-guides, real index, MCP tools](#7-phase-e--micro-guides-real-index-mcp-tools)
8. [How to extend](#8-how-to-extend)

---

## 1. Source material

- **PDF:** "Octatrack Notebook : Reference & Guide", 478 pages.
- **Local copy:** `build/artifacts/oct.pdf` (gitignored). A local copy is recommended (network mounts can cause I/O errors).

---

## 2. Auth (critical)

All model calls go through the `claude` CLI in headless mode (`claude -p --output-format json`), authenticated by a **Claude subscription OAuth token** (`CLAUDE_CODE_OAUTH_TOKEN`).

**This is not the metered Messages API.** Sending `ANTHROPIC_API_KEY` (x-api-key) returns 401 for an OAuth token. All build scripts pop `ANTHROPIC_API_KEY` from the subprocess environment to prevent accidental fallback.

| Item | Value |
|------|-------|
| Token file (outside repo, mode 600) | `/path/to/claude-oauth-token.key` |
| Env var name | `CLAUDE_CODE_OAUTH_TOKEN` |
| Billing model | Flat-rate subscription |
| `total_cost_usd` in CLI output | **Notional** (API-equivalent pricing, not real charge) |
| Real token observability | `build/artifacts/extracted/usage.jsonl` (per-page) |

**Inject the token:**

```bash
F=/path/to/claude-oauth-token.key
export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < "$F")"
```

**Rate-limit windows.** Long runs hit the subscription quota ceiling. Symptom: a burst of fast-failures after N successes — the CLI exits 1 with empty stderr. Recovery: wait for the window to reset, then re-run. Every pipeline stage is **idempotent** (skips already-produced outputs), so re-running continues exactly where it stopped.

---

## 3. Phase A — Scaffold & render

**Task 3 — render pages**

`build/render.py` rasterizes `build/artifacts/oct.pdf` at 200 DPI.

Outputs (gitignored, re-generable):

| Path | Description |
|------|-------------|
| `build/artifacts/pages/page-NNNN.png` | 478 page images |
| `build/artifacts/pages/page-NNNN.txt` | text layer (pdftotext), used as OCR spelling hint |
| `build/artifacts/pages/manifest.json` | array of `{page, png, txt}` entries |

Re-run:

```bash
uv run python -m build.render build/artifacts/oct.pdf build/artifacts/pages
```

---

## 4. Phase B — TOC & usage-mode analysis

**TOC — `build/inputs/toc.yaml` (149 sections)**

`build/tools/build_toc.py` scans each page's text layer for `N.M Title` headings. PDF embedded bookmarks were too sparse in the back half of the manual to use directly. A monotonic `(chapter, minor)` filter rejects false positives like "1.5 Bar" from body text. Result: 149 per-section chunks spanning all 16 chapters.

**Usage-mode analysis**

Manual analysis task producing the 8 `USAGE_MODES`, the spine micro-guide candidates and the MCP tool-surface decisions; its output is not included in this repo. It seeds `build/inputs/spine-guides.yaml`.

---

## 5. Phase C — Extraction

**`build/extract.py`** — one `claude -p` subprocess per page.

How it works:

1. Reads `build/artifacts/pages/manifest.json`.
2. Builds a prompt embedding the absolute PNG path and text-layer hint.
3. Calls `claude -p` with `--allowedTools Read` (model loads the image via the Read tool) and `--disallowedTools WebFetch,WebSearch,Bash,Write,Edit,Glob,Grep`.
4. Parses `--output-format json` response; writes `build/artifacts/extracted/page-NNNN.md` and appends a usage record to `build/artifacts/extracted/usage.jsonl`.
5. **Skip condition:** any `page-NNNN.md` that already exists is not re-processed.

**Model history:**

| Pass | Model | Pages | Outcome |
|------|-------|-------|---------|
| First | opus | 151/478 | Stalled — hit subscription rate ceiling; 327 fast-failures |
| Resume | sonnet | 327/478 | Completed successfully |
| Final | — | 478/478 | 0 failures; 151 opus + 327 sonnet pages kept |

Model is set in `build/extract.py:MODEL = "sonnet"`.

**Blank pages:** 20 pages are legitimate "NOTES" pages with no content; extracted as `# NOTES`.

**Per-page profile (opus):** ~7k input / 1–13k output / ~20k cache-create / ~45k cache-read tokens; ~20–40 s/page.

Re-run (resumes automatically):

```bash
F=/path/to/claude-oauth-token.key
CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < "$F")" \
  nohup uv run python -m build.extract build/artifacts/pages build/artifacts/extracted \
  build/inputs/prompts/extract_page.md > build/logs/extract_run.log 2>&1 &
```

Check progress:

```bash
ls build/artifacts/extracted/*.md | wc -l   # target: 478
tail -5 build/logs/extract_run.log
pgrep -af 'build.extract'
```

---

## 6. Phase D — Assemble, tag, reconcile, index files

### Task 12 — Assemble reference sections

`build/assemble.py` stitches per-page Markdown from `build/artifacts/extracted/` into 149 section files in `knowledge/reference/`, using `build/inputs/toc.yaml` inclusive page ranges. `concepts`, `usage_modes`, and `related` frontmatter fields are emitted empty (filled in Phase D tagging).

```bash
uv run python -c "from build.assemble import assemble; assemble('build/artifacts/extracted','build/inputs/toc.yaml','knowledge/reference')"
```

### Task 13 — Concept tagging (`build/tag.py`)

Two-tier model routing:

| Tier | Model | Condition |
|------|-------|-----------|
| Default | sonnet | all chunks |
| Escalate | opus | `difficulty==high` OR `confidence<0.6` OR `new_slugs>=3` OR `body>15KB` |

Result: 149 chunks tagged — 106 sonnet, 43 opus. The run hit a rate window at 105/149; resume was idempotent (skip condition: non-empty `concepts` in frontmatter).

Minted slugs are appended to `build/artifacts/minted-slugs.jsonl` for the reconcile step.

Glossary seed: `build/tools/seed_glossary.py` seeded `build/inputs/concept-glossary.yaml` from `docs/usage-modes.md` (67 initial slugs).

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.tag knowledge/reference build/inputs/concept-glossary.yaml
```

### Task 13 (steps 3–4) — Slug reconcile (`build/reconcile.py`)

Two auditable steps — the LLM proposes, Python applies:

**`generate`** — opus reads `build/artifacts/slug-census.json` (slug → count), emits `build/artifacts/slug-reconcile.json`: an alias→canonical map plus a drop list for OCR noise.

**`apply`** — pure Python rewrites all chunk frontmatter through the map, refreshes `build/inputs/concept-glossary.yaml`.

Result: 193 → 168 canonical slugs (22 synonym merges, 3 OCR-noise drops, e.g. `trig-mode-one-one2-hold`). 0 empty concepts, 0 orphan slugs.

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.reconcile generate
uv run python -m build.reconcile apply
```

### Task 14 — `knowledge/concepts.yaml` + `knowledge/INDEX.md`

`octatrack_kb/build_index_files.py` inverts chunk frontmatter into 168 concept entries (`definition_chunk`, `mentioned_in`, `related` = co-tagged union, `usage_modes`). Deterministic, no model calls.

```bash
uv run python -c "from octatrack_kb.corpus import load_corpus; from octatrack_kb.build_index_files import build_concepts, build_index_md; ch=load_corpus('knowledge/reference'); c=build_concepts(ch,'knowledge/concepts.yaml'); build_index_md(c,'knowledge/INDEX.md')"
```

Outputs: `knowledge/concepts.yaml`, `knowledge/INDEX.md`.

---

## 7. Phase E — Micro-guides, real index, MCP tools

### Task 15 — Spine micro-guides (`build/guides.py`)

30 guides defined in `build/inputs/spine-guides.yaml`. Per-guide three-call pipeline:

| Step | Model | Role |
|------|-------|------|
| AUTHOR | opus | Write guide grounded only in concept-overlapping reference chunks; cite `sources:` |
| REVIEW | sonnet | Flag unsupported claims |
| REVISE | opus | Rewrite to fix flagged claims (only if reviewer found issues) |

Results: 30 guides written, 10 revised. Sources are ranked by concept overlap (up to 6 chunks, 28k token body cap).

**Gotcha:** The opus revise step sometimes wrapped its output in a prose preamble + ` ```markdown ` fence, leaving real frontmatter stranded in the body (empty `sources`). Fixed by hardening `_extract_guide_md` in `build/guides.py` to tolerate prose + fences, and repairing the 9 affected files in place. Every guide's `sources[]` resolves to a real reference chunk id.

Resume (skips existing `knowledge/guides/<id>.md`):

```bash
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.guides
```

### Task 16 — Build the real index

`octatrack_kb/index.py` uses sqlite-vec (`vec0`, 384-dim float32) + FTS5 over `knowledge/reference/` + `knowledge/guides/` = 179 items total.

Embeddings: `BAAI/bge-small-en-v1.5`, asymmetric (query prefix `"Represent this sentence for searching relevant passages: "` on queries only; passages have no prefix).

```bash
uv run python -c "
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
build_index(load_corpus('knowledge/reference') + load_guides('knowledge/guides'), 'server/kb.db')
"
```

### Tasks 17–18 — MCP tools & server registration

`server/octatrack_mcp.py` — FastMCP server. Tools include `list_workflows`, `get_workflow`, `list_usage_modes`, `by_usage_mode`, `compare_approaches` (parameter: `task`), plus the core search/retrieve tools. `Hit` objects carry a `layer` field (`reference` or `guide`).

Server registered at user scope:

```bash
claude mcp add octatrack-kb  # stdio transport
```

Claude Desktop config: absolute `uv` path required. Server env vars (auth, db path) are in `~/.claude.json` — outside the repo.

29 tests pass: `uv run pytest -q`.

---

## 8. How to extend

### Re-index after any corpus edit

Run after any change to `knowledge/reference/` or `knowledge/guides/`:

```bash
uv run python -c "
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
build_index(load_corpus('knowledge/reference') + load_guides('knowledge/guides'), 'server/kb.db')
"
```

### Add a reference chunk

1. Create `knowledge/reference/<id>.md` with full frontmatter (`id`, `title`, `chapter`, `source_pages`, `concepts=[]`, `usage_modes=[]`, `related=[]`, `section`).
2. Tag it (empty `concepts` means `tag.py` picks it up automatically):
   ```bash
   CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.tag knowledge/reference build/inputs/concept-glossary.yaml
   ```
3. If the tagger mints new slugs, reconcile:
   ```bash
   CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.reconcile generate
   uv run python -m build.reconcile apply
   ```
4. Rebuild concept index:
   ```bash
   uv run python -c "from octatrack_kb.corpus import load_corpus; from octatrack_kb.build_index_files import build_concepts, build_index_md; ch=load_corpus('knowledge/reference'); c=build_concepts(ch,'knowledge/concepts.yaml'); build_index_md(c,'knowledge/INDEX.md')"
   ```
5. Re-index (command above).

### Add or update a concept

Concepts are emergent from chunk tagging — they are not declared independently. To introduce a new concept slug:

- Add it to `build/inputs/concept-glossary.yaml` so taggers see it, OR
- Add it directly to the `concepts:` list of the relevant reference chunk(s).

Then rebuild `knowledge/concepts.yaml`/`knowledge/INDEX.md` (inline command above) and re-index.

### Author a new micro-guide

1. Add a row to `build/inputs/spine-guides.yaml` with `id`, `description`, `modes`, `concepts`.
2. Run (idempotent — skips existing guides):
   ```bash
   CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.guides
   ```
3. Re-index (command above).

### Force-redo a single output

Every stage skips already-produced outputs. To force a redo, delete the output file and re-run the stage:

```bash
# Re-extract a single page
rm build/artifacts/extracted/page-0042.md
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.extract build/artifacts/pages build/artifacts/extracted build/inputs/prompts/extract_page.md

# Re-tag a single chunk (clear its concepts frontmatter first, or delete + reassemble)
# Easiest: edit the file to set concepts: [] then re-run tag.py

# Re-author a guide
rm knowledge/guides/my-guide.md
CLAUDE_CODE_OAUTH_TOKEN="..." uv run python -m build.guides
```

### Auth setup for any model phase

```bash
F=/path/to/claude-oauth-token.key
export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < "$F")"
# Now run any build.* module
```

Do not set `ANTHROPIC_API_KEY` alongside `CLAUDE_CODE_OAUTH_TOKEN` — the build scripts pop it from the subprocess environment, but having it set at the shell level risks accidental metered calls in other tools.
