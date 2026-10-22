# Installing the Octatrack KB in Claude Desktop

This guide is for anyone who wants to chat with the Octatrack knowledge base inside Claude Desktop — no programming experience required, though you will need to run a few terminal commands.

**What an MCP server is, in plain English:** it's a small local program that gives the Claude app a private library to search. When you ask Claude a question about the Octatrack, it quietly queries this library on your own machine and uses the results to give you accurate, sourced answers. Nothing is uploaded anywhere. No extra AI cost is incurred — queries run entirely offline against a pre-built index.

---

## Prerequisites

Before you start, make sure you have:

- **Claude Desktop** installed and working ([claude.ai/download](https://claude.ai/download))
- **Python 3.12 or newer** — check with `python3 --version` in a terminal
- **`uv`** — a fast Python package manager. Install it from [docs.astral.sh/uv](https://docs.astral.sh/uv/) if you don't have it yet
- **~150 MB free disk space** — the first index build downloads a small embedding model (bge-small-en-v1.5); it is cached after that

> **Important — find your absolute path to `uv`:**
> Claude Desktop launches programs directly and does NOT inherit your shell's PATH, so you must give it the full path to `uv`. Find it now and keep it handy:
>
> ```bash
> which uv
> ```
>
> Example output: `/home/yourname/.local/bin/uv` (Linux) or `/Users/yourname/.local/bin/uv` (macOS). You will need this in Step 4.

---

## Step 1 — Get the repo onto your machine

If you have `git`:

```bash
git clone https://github.com/your-org/octatrack-kb.git
cd octatrack-kb
```

Or download and unzip the repository archive, then open a terminal and `cd` into the folder.

Note the absolute path to this folder — you will need it shortly. Example:

```
/home/yourname/octatrack-kb
```

---

## Step 2 — Install Python dependencies

Inside the `octatrack-kb` folder:

```bash
uv sync
```

This installs all required packages into a local virtual environment. It only needs to run once.

---

## Step 3 — Build the local search index

This is the only step that takes a little time (~1–2 minutes). It builds a local database (`server/kb.db`) from the knowledge files. No internet connection or API key is needed — everything runs on your CPU.

```bash
uv run python -c "
from octatrack_kb.corpus import load_corpus, load_guides
from octatrack_kb.index import build_index
build_index(load_corpus('knowledge/reference') + load_guides('knowledge/guides'), 'server/kb.db')
"
```

When it finishes you should see no errors. The file `server/kb.db` will have been created (or updated).

---

## Step 4 — Add the server to Claude Desktop's config

Claude Desktop reads its MCP server list from a JSON config file. You need to add the Octatrack KB server to it.

**Find the config file:**

| Operating system | Path |
|------------------|------|
| Linux | `~/.config/Claude/claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

Open `server/config.example.json` from this repo — it looks like this:

```json
{
  "mcpServers": {
    "octatrack-kb": {
      "command": "uv",
      "args": ["run", "python", "-m", "server.octatrack_mcp"],
      "cwd": "/ABSOLUTE/PATH/TO/octatrack-kb",
      "env": {
        "OCTATRACK_DB": "/ABSOLUTE/PATH/TO/octatrack-kb/server/kb.db",
        "OCTATRACK_REFERENCE": "/ABSOLUTE/PATH/TO/octatrack-kb/knowledge/reference",
        "OCTATRACK_CONCEPTS": "/ABSOLUTE/PATH/TO/octatrack-kb/knowledge/concepts.yaml",
        "OCTATRACK_GUIDES": "/ABSOLUTE/PATH/TO/octatrack-kb/knowledge/guides"
      }
    }
  }
}
```

**Make two substitutions before copying:**

1. Replace every occurrence of `/ABSOLUTE/PATH/TO/octatrack-kb` with the real path to your repo folder (e.g. `/home/yourname/octatrack-kb`).
2. Replace `"command": "uv"` with the absolute path you found in the Prerequisites step (e.g. `"command": "/home/yourname/.local/bin/uv"`).

**Merge into the Claude Desktop config:**

- If the file `claude_desktop_config.json` **does not exist yet**, create it and paste the whole block above (with your substitutions) as the file content.
- If the file **already exists** and has an `"mcpServers"` key, add the `"octatrack-kb"` entry inside that existing object alongside any other servers. Do not replace the whole file.

Save the file.

---

## Step 5 — Fully quit and reopen Claude Desktop

Closing the window is not enough — Claude Desktop keeps running in the background. You must fully quit it:

- **macOS:** right-click the Claude icon in the Dock → Quit, or use the menu bar → Claude → Quit Claude
- **Linux:** close the window and check your system tray; kill the process if it persists

Reopen Claude Desktop. When it starts, it will launch the MCP server in the background.

---

## Verify it works

1. Open a new chat in Claude Desktop.
2. Look for the tools icon (hammer/wrench icon) near the message box — the `octatrack-kb` tools should be listed there. Enable them if they appear as optional.
3. Ask:

   > "How do I sample a live audio source on the Octatrack?"

   You should get a detailed, sourced answer that cites specific sections of the manual. If you see source references like `[audio-inputs]` or `[pickup-machine-basics]`, the KB is working correctly.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `command not found: uv` error in Claude Desktop | `command` in config is `"uv"` instead of the absolute path | Replace with the full path from `which uv` |
| Tools don't appear in Claude Desktop | Desktop wasn't fully quit, or JSON syntax error in config | Fully quit and reopen; validate your JSON at [jsonlint.com](https://jsonlint.com) |
| "Server failed to start" or "MCP error" | A path in the config is wrong or not absolute | Check all four `OCTATRACK_*` env values and `cwd` are absolute paths that actually exist |
| `server/kb.db` missing | Step 3 was skipped or failed | Re-run the `uv run python -c "..."` command from Step 3 |
| Answers seem generic / no source citations | Tools are not being called | Make sure tools are enabled in the chat; try explicitly asking "use the octatrack-kb tools to answer" |

---

## Next steps

- [`server/README.md`](../server/README.md) — full reference for all 8 MCP tools and their parameters
- [`docs/REPLICATION.md`](REPLICATION.md) — how to build a KB like this for a different manual
