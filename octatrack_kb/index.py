"""Build the SQLite retrieval index: sqlite-vec vectors + FTS5 keyword table.

MAGIC: bge-small-en-v1.5 is 384-dim and asymmetric — queries get the
"Represent this sentence for searching relevant passages: " prefix, passages
do not. Embeddings are stored as raw float32 bytes in a vec0 virtual table;
keyword search uses a parallel FTS5 table. Both are keyed by chunk id so
results from either side merge cleanly.
"""
from __future__ import annotations
import sqlite3, struct
import sqlite_vec
from sentence_transformers import SentenceTransformer
from .schema import Chunk

EMBED_DIM = 384
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    return get_model().encode([QUERY_PREFIX + text],
                              normalize_embeddings=True)[0].tolist()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def build_index(chunks: list[Chunk], db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.enable_load_extension(True); sqlite_vec.load(con)
    con.execute("DROP TABLE IF EXISTS vec_chunks")
    con.execute("DROP TABLE IF EXISTS fts_chunks")
    con.execute(f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
                f"id TEXT PRIMARY KEY, embedding float[{EMBED_DIM}])")
    con.execute("CREATE VIRTUAL TABLE fts_chunks USING fts5(id, title, body)")
    vecs = embed_passages([f"{c.title}\n{c.body}" for c in chunks])
    for c, v in zip(chunks, vecs):
        con.execute("INSERT INTO vec_chunks(id, embedding) VALUES (?, ?)",
                    (c.id, _pack(v)))
        con.execute("INSERT INTO fts_chunks(id, title, body) VALUES (?, ?, ?)",
                    (c.id, c.title, c.body))
    con.commit(); con.close()
