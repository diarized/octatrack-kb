from octatrack_kb.corpus import load_corpus
from octatrack_kb.index import build_index, EMBED_DIM
import sqlite3, sqlite_vec

def test_build_index_populates_vec_and_fts(tmp_path):
    db = tmp_path / "kb.db"
    chunks = load_corpus("tests/fixtures/reference")
    build_index(chunks, str(db))

    con = sqlite3.connect(db)
    con.enable_load_extension(True); sqlite_vec.load(con)
    n_vec = con.execute("SELECT count(*) FROM vec_chunks").fetchone()[0]
    n_fts = con.execute("SELECT count(*) FROM fts_chunks").fetchone()[0]
    assert n_vec == len(chunks) == n_fts
    dim = len(con.execute("SELECT embedding FROM vec_chunks LIMIT 1").fetchone()[0]) // 4
    assert dim == EMBED_DIM  # float32 bytes / 4
