# Octatrack KB — Build Pipeline

Converts the 478-page Octatrack Notebook PDF into the three-layer KB (reference chunks, concept graph, guides). Each script is independently resumable.

---

## Pipeline Order

1. `build/tools/build_toc.py` — generate `build/inputs/toc.yaml` from PDF headings
2. `build/render.py` — render PDF pages to PNG + extract text layers
3. `build/extract.py` — per-page vision extraction to Markdown via `claude` CLI
4. `build/assemble.py` — stitch page Markdown into section chunks using `build/inputs/toc.yaml`
5. `build/tag.py` — triaged concept/usage-mode/related tagging
6. `build/reconcile.py generate` then `apply` — Opus slug canonicalization
7. `octatrack_kb/build_index_files.py` — invert frontmatter into `knowledge/concepts.yaml` + `knowledge/INDEX.md`
8. `build/guides.py` — Opus-author + Sonnet-verify 30 spine micro-guides
9. Re-run `octatrack_kb/index.py:build_index` — build the SQLite retrieval index


---

## Auth — Not a Standard API Key

All `claude` CLI calls use the **Claude subscription OAuth token**, not the metered Messages API. The `ANTHROPIC_API_KEY` / `anthropic` SDK path returns 401 for this token.

- Token env var: `CLAUDE_CODE_OAUTH_TOKEN` (obtain via `claude setup-token`)
- All scripts strip `ANTHROPIC_API_KEY` from the subprocess environment to prevent accidental fallback
- `total_cost_usd` in `build/artifacts/extracted/usage.jsonl` is **notional** (API-equivalent pricing); real billing is flat-rate subscription

---

## Script Reference

### `build/tools/build_toc.py`

Regenerates `build/inputs/toc.yaml` — the authoritative section-to-page-range map.

The PDF's embedded bookmarks are too sparse in the back half (Effects / MIDI / Arrangements / System chapters have almost no `N.M` bookmarks). Instead, the script scans every page's text layer for `N.M Title` heading lines and applies a monotonic `(chapter, section)` filter to reject false positives. Page ranges are contiguous and inclusive; each chapter's first section is pulled back to include its decorative title page using the nearest level-1 bookmark within 5 pages. Result: 149 sections, all 16 chapters.

```bash
uv run python build/tools/build_toc.py
```

### `build/render.py`

Renders every PDF page to a PNG and extracts its embedded text layer.

**DPI magic**: 200 DPI keeps an A4 page's long edge (~2339 px) under the Opus 4.8 vision cap of 2576 px — the model receives the full page at native resolution with no server-side downscale. The text layer is saved as a `.txt` alongside each PNG; during extraction it is handed to the vision model as a label-spelling hint, anchoring diagram labels without OCR guesswork. Outputs: `build/artifacts/pages/{page-NNNN.png, page-NNNN.txt, manifest.json}`.

### `build/extract.py`

Per-page vision extraction from PNG to Markdown, driven by the `claude` CLI in headless (`-p`) mode.

Each page spawns one `claude -p` subprocess. The model is granted only the `Read` tool (to load the PNG); all write/network tools are disallowed. Auth is `CLAUDE_CODE_OAUTH_TOKEN` — `ANTHROPIC_API_KEY` is stripped from the subprocess env.

**Resume-by-skip idempotency**: any page whose `page-NNNN.md` already exists in the output directory is skipped unconditionally. A crashed or rate-limited run continues exactly where it stopped — safe to re-invoke without duplication.

**Rate-window behavior**: The original pass used `opus`; after 151/478 pages the subscription rate ceiling was hit and the remaining 327 fast-failed. The model was switched to `sonnet` (lighter quota draw, comparable fidelity). The 151 opus pages are preserved — resume skips them. Set in `build/extract.py:MODEL`.

A per-page timeout (default 300 s) prevents one stuck page from hanging a full 478-page run. Token usage is logged per-page to `build/artifacts/extracted/usage.jsonl`; `total_cost_usd` is notional.

### `build/assemble.py`

Stitches per-page Markdown into one file per section using the page ranges in `build/inputs/toc.yaml`. Hyphenated line-breaks across page boundaries are rejoined. Output chunks carry full frontmatter with `concepts`, `usage_modes`, and `related` emitted as empty lists; those are filled by the Phase D enrichment pass (tag → reconcile). This step is deterministic and re-runnable.

### `build/tag.py`

Concept/usage-mode/related tagging of reference chunks via two-tier model routing.

Every chunk is tagged by **Sonnet** first (cheap). A chunk is re-tagged by **Opus** only if the Sonnet pass meets any escalation trigger:

| Trigger | Threshold |
|---------|-----------|
| `difficulty` field | `"high"` |
| `confidence` field | `< 0.6` |
| Newly minted slugs | `>= 3` |
| Body size | `> 15 000 bytes` |

The Opus result supersedes the Sonnet result when escalation fires; Sonnet tags are kept on Opus failure. No tools are granted (the chunk body is embedded directly in the prompt). Resumable: a chunk whose frontmatter already has a non-empty `concepts` list is skipped. Newly minted slugs are appended to `build/artifacts/minted-slugs.jsonl` for the subsequent Opus reconcile.

### `build/reconcile.py`

Two-step Opus slug canonicalization, auditable and re-runnable.

**`generate`**: Opus reads the full slug census (every slug and its usage count) and proposes a JSON mapping — `canonical: {alias → canonical}` and `drop: [noise-slug, ...]`. The LLM only *proposes*; the mapping is saved to `build/artifacts/slug-reconcile.json` for human inspection before application.

**`apply`**: Pure Python rewrites every chunk's `concepts` through the map — dropping noise slugs, remapping aliases to canonical forms, deduplicating, preserving order. Refreshes `build/inputs/concept-glossary.yaml` with the surviving canonical slugs. Result: 193 raw slugs reduced to 168 canonical slugs.

### `octatrack_kb/build_index_files.py`

Inverts chunk frontmatter into `knowledge/concepts.yaml` and `knowledge/INDEX.md`. A concept's `definition_chunk` is the chunk whose `id` equals the concept slug (if it exists), otherwise the lowest-chapter chunk that tags it. `mentioned_in` lists every tagging chunk; `related` is the union of co-tagged concepts. This is the cross-correlation backbone that `get_concept` traverses.

### `build/guides.py`

Authors 30 task-oriented spine micro-guides with a source-accuracy gate.

Per guide, a three-call pipeline:

1. **AUTHOR (Opus)** — writes `knowledge/guides/<id>.md` grounded only in the supplied reference chunks (up to 6, scored by concept overlap, capped at 28 000 total chars). Cites chunk ids in `sources:` frontmatter.
2. **REVIEW (Sonnet)** — checks every claim against those source chunks; returns unsupported claims as structured issues.
3. **REVISE (Opus)** — if the reviewer flagged issues, rewrites to remove or fix them. Only guides with issues get a third call.

Source chunks are selected by concept overlap: each guide concept is looked up in `knowledge/concepts.yaml`; chunks listed in `mentioned_in` are scored by overlap count; a chunk whose `id` matches a guide concept receives a +5 boost (it is a definition chunk).

Resumable: an existing `knowledge/guides/<id>.md` is skipped. 10 of the 30 guides required a revise pass.

---

## Tools Directory (`build/tools/`)

| Script | Purpose |
|--------|---------|
| `build_toc.py` | Generate `build/inputs/toc.yaml` from PDF page-text heading scan |
| `seed_glossary.py` | Seed `build/inputs/concept-glossary.yaml` from `**Key concepts:**` lists in `docs/usage-modes.md` |
| `parse_spine_guides.py` | Parse the spine-guide Markdown table in `docs/usage-modes.md` into `build/inputs/spine-guides.yaml` |

`seed_glossary.py` and `parse_spine_guides.py` are idempotent (byte-stable output on unchanged input) and keep the tagging and guide-authoring stages in sync with the Task 2 usage-mode analysis document rather than hand-duplicating it.

---

## Key Build Artefacts

| Artefact | Produced by | Notes |
|----------|-------------|-------|
| `build/artifacts/oct.pdf` | manual copy | local copy avoids network-mount I/O errors |
| `build/artifacts/pages/` | `render.py` | 478 PNG+txt + `manifest.json` |
| `build/inputs/toc.yaml` | `tools/build_toc.py` | 149 sections, all 16 chapters |
| `build/artifacts/extracted/` | `extract.py` | 478 per-page `.md` + `usage.jsonl` |
| `build/inputs/concept-glossary.yaml` | `tools/seed_glossary.py` → `reconcile.py apply` | 168 canonical slugs |
| `build/inputs/spine-guides.yaml` | `tools/parse_spine_guides.py` | 30 guide specs |
| `build/artifacts/slug-reconcile.json` | `reconcile.py generate` | reviewable alias→canonical map |
| `knowledge/reference/` | `assemble.py` | 149 section chunks with frontmatter |
| `knowledge/guides/` | `guides.py` | 30 verified micro-guides |
| `knowledge/concepts.yaml` | `build_index_files.py` | 168-concept graph |
| `knowledge/INDEX.md` | `build_index_files.py` | human-readable concept index |
| `server/kb.db` | `octatrack_kb/index.py` | SQLite vec0 + FTS5 index (179 items) |
