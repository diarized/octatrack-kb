# Octatrack KB — MCP Server

FastMCP server bridging the Octatrack KB to Claude. Thin adapter over `octatrack_kb/retrieval.py`; all tool bodies delegate to `Retriever`.

---

## Environment Variables

| Variable | Points at | Required |
|----------|-----------|----------|
| `OCTATRACK_DB` | SQLite index file (`server/kb.db`) | yes |
| `OCTATRACK_REFERENCE` | Directory of 149 reference chunk `.md` files (`knowledge/reference/`) | yes |
| `OCTATRACK_CONCEPTS` | `knowledge/concepts.yaml` concept graph | yes |
| `OCTATRACK_GUIDES` | Directory of 30 guide `.md` files (`knowledge/guides/`) | no (workflow tools disabled if absent) |

The same `server/octatrack_mcp.py` file works for both Claude Code and Claude Desktop — only the config differs.

---

## MCP Tools

### `search(query: str, k: int = 5) -> list[dict]`

Hybrid semantic + keyword search over all 179 KB items (149 reference + 30 guides).

Returns: `[{id, title, layer, score}, ...]` sorted by descending score.

```json
{"query": "how does parameter lock work with LFOs", "k": 5}
```

### `get_chunk(chunk_id: str) -> dict | None`

Fetch a full reference section or guide by id. Returns the complete body plus all frontmatter fields.

Returns: `{id, title, layer, chapter, section, source_pages, concepts, related, body}` or `null`.

```json
{"chunk_id": "parameter-lock"}
```

### `get_concept(name: str) -> dict | None`

Cross-correlation entrypoint. Returns the concept's definition chunk, every chunk it is mentioned in, and related concepts — the full topic neighbourhood in one hop.

Returns: `{concept, label, definition_chunk, mentioned_in, related, usage_modes}` or `null`.

```json
{"name": "parameter-lock"}
```

### `list_workflows() -> list[dict]`

List every task-oriented spine micro-guide.

Returns: `[{id, title, modes}, ...]` for all 30 guides.

```json
{}
```

### `get_workflow(workflow_id: str) -> dict | None`

Full guide content: title, usage modes, concepts in scope, cited source reference chunk ids, and the guide body.

Returns: `{id, title, modes, concepts, sources, body}` or `null`.

```json
{"workflow_id": "sample-a-live-source"}
```

### `list_usage_modes() -> list[dict]`

The controlled usage-mode vocabulary with item counts for the current corpus.

Returns: `[{mode, count}, ...]` for all 8 modes.

```json
{}
```

### `by_usage_mode(mode: str) -> list[dict]`

All reference sections and guides tagged with a given usage mode. `layer` distinguishes the source.

Returns: `[{id, title, layer}, ...]`.

```json
{"mode": "sampler"}
```

### `compare_approaches(task: str, k: int = 3) -> list[dict]`

Top `k` guides matching a task description, each with its usage modes and full body. Useful for seeing different ways to accomplish the same goal.

Returns: `[{id, title, modes, score, body}, ...]`.

```json
{"task": "loop a sample in sync with the sequencer", "k": 3}
```

---

## Retrieval Scoring

Source: `octatrack_kb/retrieval.py:40-75`.

**Final score** for a candidate chunk:

```
score = vec_sim + 0.5 * fts_score + 0.25 * concept_boost
```

- **`vec_sim`**: `1 / (1 + L2_distance)` on normalized `bge-small-en-v1.5` embeddings (384-dim). Candidates retrieved by `sqlite-vec` KNN from a `vec0` virtual table.
- **`fts_score`**: `bm25_rank / best_bm25_rank` (0–1) from a parallel FTS5 table. BM25 rank is negative (lower = better), so dividing by the best row's rank gives the top FTS match 1.0 and scales the rest proportionally. FTS failures on malformed query syntax fall through silently; vector results still stand.
- **`concept_boost`**: `+0.25` per chunk if any query term matches a chunk's concept slug (single-token: set intersection; hyphenated multi-word slugs like `parameter-lock`: substring match of the de-hyphenated form against the query string, since whitespace-splitting would never reassemble them).

**Embedding model**: `BAAI/bge-small-en-v1.5`. Asymmetric — queries prepend `"Represent this sentence for searching relevant passages: "`, passage embeddings are stored without a prefix. Passages are indexed as `title\nbody`.

**`layer` field**: `"reference"` for chunks from `knowledge/reference/`, `"guide"` for chunks from `knowledge/guides/`. Present in `search` results and `get_chunk`/`get_workflow` responses.

---

## Registration

### Claude Code (user scope)

```bash
claude mcp add octatrack-kb \
  -e OCTATRACK_DB=/absolute/path/to/server/kb.db \
  -e OCTATRACK_REFERENCE=/absolute/path/to/knowledge/reference \
  -e OCTATRACK_CONCEPTS=/absolute/path/to/knowledge/concepts.yaml \
  -e OCTATRACK_GUIDES=/absolute/path/to/knowledge/guides \
  -- uv run python -m server.octatrack_mcp
```

Verify: `claude mcp list` — status should show `Connected`.

### Claude Desktop

Merge `server/config.example.json` into `~/.config/Claude/claude_desktop_config.json` under the `"mcpServers"` key. The `"command"` value must be the **absolute path** to `uv` — Claude Desktop does not inherit `$PATH`.

```json
{
  "mcpServers": {
    "octatrack-kb": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "python", "-m", "server.octatrack_mcp"],
      "cwd": "/absolute/path/to/octatrack-kb",
      "env": {
        "OCTATRACK_DB": "/absolute/path/to/server/kb.db",
        "OCTATRACK_REFERENCE": "/absolute/path/to/knowledge/reference",
        "OCTATRACK_CONCEPTS": "/absolute/path/to/knowledge/concepts.yaml",
        "OCTATRACK_GUIDES": "/absolute/path/to/knowledge/guides"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config.

---

## Rebuilding the Index

After any change to `knowledge/reference/` or `knowledge/guides/`:

```bash
uv run python -c "
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
build_index(load_corpus('knowledge/reference') + load_guides('knowledge/guides'), 'server/kb.db')
"
```
