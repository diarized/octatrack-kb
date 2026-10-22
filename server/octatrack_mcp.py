"""FastMCP server exposing the Octatrack KB. Thin adapter over retrieval.py.

MAGIC: all paths come from env vars (OCTATRACK_DB / _REFERENCE / _CONCEPTS) so
the identical file is registered in both Claude Code and Claude Desktop with
only the config differing. Tool bodies just call the Retriever.
"""
from __future__ import annotations
import os
from mcp.server.fastmcp import FastMCP
from octatrack_kb.retrieval import Retriever

_R = Retriever(os.environ["OCTATRACK_DB"],
               os.environ["OCTATRACK_REFERENCE"],
               os.environ["OCTATRACK_CONCEPTS"],
               guides_dir=os.environ.get("OCTATRACK_GUIDES"))
mcp = FastMCP("octatrack-kb")


@mcp.tool()
def search(query: str, k: int = 5) -> list[dict]:
    """Hybrid semantic + keyword search over the Octatrack KB (reference + guides)."""
    return [{"id": h.id, "title": h.title, "layer": h.layer, "score": round(h.score, 4)}
            for h in _R.search(query, k)]


@mcp.tool()
def get_chunk(chunk_id: str) -> dict | None:
    """Return a full reference section or guide by id."""
    return _R.get_chunk(chunk_id)


@mcp.tool()
def get_concept(name: str) -> dict | None:
    """Return a concept's definition chunk, every chunk it's mentioned in,
    and related concepts — the cross-correlation entrypoint."""
    return _R.get_concept(name)


@mcp.tool()
def list_workflows() -> list[dict]:
    """List every task-oriented spine micro-guide (id, title, usage modes)."""
    return _R.list_workflows()


@mcp.tool()
def get_workflow(workflow_id: str) -> dict | None:
    """Return a full workflow guide: modes, concepts, cited sources, and body."""
    return _R.get_workflow(workflow_id)


@mcp.tool()
def list_usage_modes() -> list[dict]:
    """List the usage-mode vocabulary and how many KB items tag each."""
    return _R.list_usage_modes()


@mcp.tool()
def by_usage_mode(mode: str) -> list[dict]:
    """List reference sections and guides tagged with a given usage mode."""
    return _R.by_usage_mode(mode)


@mcp.tool()
def compare_approaches(task: str, k: int = 3) -> list[dict]:
    """Compare the different ways to accomplish a task: the top matching guides,
    each with its usage modes and full body."""
    return _R.compare_approaches(task, k)


if __name__ == "__main__":
    mcp.run()
