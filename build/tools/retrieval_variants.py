"""Compare current hybrid retrieval against text-only (no embedding model) variants.

Research tool — not used by the server.
Runs the coverage_check battery through each variant and reports expected-token
hits in top-5, top-1 agreement with the hybrid, and top-5 overlap with it.
Text-only variants score FTS hits by rank position (1/(1+pos)) + concept boost.

Run: uv run python -m build.tools.retrieval_variants
"""
from __future__ import annotations
import re, sqlite3
from octatrack_kb.retrieval import Retriever
from build.tools.coverage_check import BATTERY

STOP = set("a an and the of to in on for with how do i is what are vs from over "
           "as by it its use set up into".split())


def or_query(q: str) -> str:
    """'how do I slice a break' -> '"slice" OR "break"' (FTS5 default is AND)."""
    toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in STOP]
    return " OR ".join(f'"{t}"' for t in toks)


def main() -> None:
    r = Retriever("server/kb.db", "knowledge/reference", "knowledge/concepts.yaml",
                  "knowledge/guides")
    # Variant D index: porter stemming, title weighted 5x over body.
    mem = sqlite3.connect(":memory:")
    mem.execute("CREATE VIRTUAL TABLE f USING fts5(id UNINDEXED, title, body, "
                "tokenize='porter unicode61')")
    for c in r.all.values():
        mem.execute("INSERT INTO f VALUES (?,?,?)", (c.id, c.title, c.body))

    def text_search(q, con, sql, match, k=5):
        scores: dict[str, float] = {}
        try:
            for pos, (i, _) in enumerate(con.execute(sql, (match,))):
                scores[i] = scores.get(i, 0.0) + 1.0 / (1 + pos)
        except sqlite3.OperationalError:
            pass
        terms, ql = {t.lower() for t in q.split()}, q.lower()
        for cid, c in r.all.items():  # same concept boost as Retriever.search
            if terms & {x.lower() for x in c.concepts} or \
               any(x.lower().replace("-", " ") in ql for x in c.concepts):
                scores[cid] = scores.get(cid, 0.0) + 0.25
        return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:k]]

    fts = "SELECT id, rank FROM fts_chunks WHERE fts_chunks MATCH ? ORDER BY rank LIMIT 20"
    fts_d = "SELECT id, bm25(f, 0, 5.0, 1.0) FROM f WHERE f MATCH ? ORDER BY 2 LIMIT 20"
    variants = {
        "A hybrid (current)":       lambda q: [h.id for h in r.search(q, 5)],
        "B FTS raw query":          lambda q: text_search(q, r.con, fts, q),
        "C FTS OR-tokens":          lambda q: text_search(q, r.con, fts, or_query(q)),
        "D FTS OR+porter+title x5": lambda q: text_search(q, mem, fts_d, or_query(q)),
    }
    base = {q: variants["A hybrid (current)"](q) for q, _ in BATTERY}
    n = len(BATTERY)
    for name, fn in variants.items():
        hit = top1 = overlap = 0
        misses = []
        for q, exp in BATTERY:
            ids = fn(q)
            blob = " ".join(f"{i} {r.all[i].title}".lower() for i in ids if i in r.all)
            hit += exp in blob
            if exp not in blob:
                misses.append(q)
            top1 += bool(ids) and ids[0] == base[q][0]
            overlap += len(set(ids) & set(base[q]))
        print(f"{name:26} expected-token {hit}/{n} | top1==hybrid {top1}/{n} "
              f"| top5 overlap {overlap / (5 * n):.0%}")
        for m in misses:
            print("    MISS:", m)


if __name__ == "__main__":
    main()
