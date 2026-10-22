"""Peak RSS of the MCP server's retrieval stack, stage by stage.

Research tool — not used by the server.
ru_maxrss is a high-water mark, so each line is cumulative peak, not a delta.

Run: uv run python -m build.tools.measure_rss
"""
import resource


def mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024  # Linux: KiB


if __name__ == "__main__":
    import sqlite3, sqlite_vec, yaml  # noqa: F401
    from octatrack_kb.corpus import load_corpus, load_guides
    load_corpus("knowledge/reference"); load_guides("knowledge/guides")
    print(f"corpus + sqlite, no model:          {mb()} MB")
    import torch, sentence_transformers  # noqa: F401
    print(f"+ import torch/sentence-transformers: {mb()} MB")
    from octatrack_kb.retrieval import Retriever
    r = Retriever("server/kb.db", "knowledge/reference", "knowledge/concepts.yaml",
                  "knowledge/guides")
    r.search("what is a parameter lock")
    print(f"+ bge-small loaded, one hybrid query: {mb()} MB")
