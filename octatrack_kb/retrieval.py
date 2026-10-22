"""Hybrid retrieval (vector + FTS) and concept-graph access.

MAGIC: final score = normalized vector similarity + 0.5 * normalized FTS score
+ 0.25 per query-term concept match. Vector handles conceptual paraphrase, FTS
handles exact terminology, the concept boost favours chunks tagged with the
queried idea. get_concept is the cross-correlation entrypoint: it returns the
definition chunk plus every chunk the concept is mentioned in, plus related
concepts, so callers can pull a whole topic neighbourhood in one hop.
"""
from __future__ import annotations
import sqlite3, struct
from dataclasses import dataclass
import sqlite_vec, yaml
from .corpus import load_corpus, load_guides
from .index import embed_query
from .schema import USAGE_MODES


@dataclass
class Hit:
    id: str
    title: str
    score: float
    layer: str = "reference"


class Retriever:
    def __init__(self, db_path: str, reference_dir: str, concepts_path: str,
                 guides_dir: str | None = None):
        self.con = sqlite3.connect(db_path)
        self.con.enable_load_extension(True)
        sqlite_vec.load(self.con)
        self.chunks = {c.id: c for c in load_corpus(reference_dir)}
        self.guides = {g.id: g for g in load_guides(guides_dir)} if guides_dir else {}
        # Unified view for hit resolution + concept boost; guides win on (no) collision.
        self.all = {**self.chunks, **self.guides}
        with open(concepts_path) as f:
            self.concepts = yaml.safe_load(f) or {}

    def search(self, query: str, k: int = 5) -> list[Hit]:
        qvec = struct.pack("384f", *embed_query(query))
        vec_rows = self.con.execute(
            "SELECT id, distance FROM vec_chunks "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (qvec, k * 4),
        ).fetchall()
        # distance is L2 on normalized vectors -> smaller is better; invert.
        scores: dict[str, float] = {i: 1.0 / (1.0 + d) for i, d in vec_rows}
        try:
            fts_rows = self.con.execute(
                "SELECT id, rank FROM fts_chunks WHERE fts_chunks MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, k * 4),
            ).fetchall()
            # bm25 rank is negative, lower (larger |rank|) is better; normalize
            # against the best row so the top FTS match scores 0.5.
            best = fts_rows[0][1] if fts_rows else 0.0
            for i, rank in fts_rows:
                scores[i] = scores.get(i, 0.0) + (0.5 * rank / best if best else 0.0)
        except sqlite3.OperationalError:
            pass  # FTS syntax error on odd queries -- vector results still stand
        terms = {t.lower() for t in query.split()}
        query_lower = query.lower()
        for cid, c in self.all.items():
            # Single-token slugs match via set intersection; multi-word/hyphenated
            # slugs ("parameter-lock" -> "parameter lock") match as a substring of
            # the query, since whitespace-splitting would never reassemble them.
            chunk_concepts_spaces = {cc.lower().replace("-", " ") for cc in c.concepts}
            if terms & {cc.lower() for cc in c.concepts} or \
               any(cs in query_lower for cs in chunk_concepts_spaces):
                scores[cid] = scores.get(cid, 0.0) + 0.25
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [
            Hit(cid, self.all[cid].title, s,
                layer="guide" if cid in self.guides else "reference")
            for cid, s in ranked
            if cid in self.all
        ]

    def get_chunk(self, chunk_id: str) -> dict | None:
        c = self.all.get(chunk_id)
        if not c:
            return None
        layer = "guide" if chunk_id in self.guides else "reference"
        return {
            "id": c.id,
            "title": c.title,
            "layer": layer,
            "chapter": c.chapter,
            "section": c.section,
            "source_pages": c.source_pages,
            "concepts": c.concepts,
            "related": c.related,
            "body": c.body,
        }

    def get_concept(self, name: str) -> dict | None:
        entry = self.concepts.get(name)
        if not entry:
            return None
        return {"concept": name, **entry}

    # --- Workflow (guide) layer -------------------------------------------------

    def list_workflows(self) -> list[dict]:
        """Every spine micro-guide: id, title, the usage modes it spans."""
        return [{"id": g.id, "title": g.title, "modes": g.usage_modes}
                for g in self.guides.values()]

    def get_workflow(self, workflow_id: str) -> dict | None:
        """Full guide: title, modes, concepts, cited source chunk ids, body."""
        g = self.guides.get(workflow_id)
        if not g:
            return None
        return {"id": g.id, "title": g.title, "modes": g.usage_modes,
                "concepts": g.concepts, "sources": g.related, "body": g.body}

    # --- Usage-mode layer -------------------------------------------------------

    def list_usage_modes(self) -> list[dict]:
        """The controlled usage-mode vocabulary with how many items tag each."""
        out = []
        for mode in sorted(USAGE_MODES):
            n = sum(1 for c in self.all.values() if mode in c.usage_modes)
            out.append({"mode": mode, "count": n})
        return out

    def by_usage_mode(self, mode: str) -> list[dict]:
        """Reference sections AND guides tagged with a usage mode."""
        return [{"id": c.id, "title": c.title,
                 "layer": "guide" if c.id in self.guides else "reference"}
                for c in self.all.values() if mode in c.usage_modes]

    def compare_approaches(self, task: str, k: int = 3) -> list[dict]:
        """Different ways to accomplish a task: top guides matching it, each with
        its usage modes and body so callers can compare alternatives."""
        guide_ids = set(self.guides)
        hits = [h for h in self.search(task, k=k * 6) if h.id in guide_ids][:k]
        out = []
        for h in hits:
            g = self.guides[h.id]
            out.append({"id": g.id, "title": g.title, "modes": g.usage_modes,
                        "score": round(h.score, 4), "body": g.body})
        return out
