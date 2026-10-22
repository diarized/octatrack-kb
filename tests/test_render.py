import fitz
import json
from build.render import render_pdf


def test_render_writes_png_and_text_per_page(tmp_path):
    """Render a 2-page PDF to PNG + extract text layer to manifest."""
    # Build a 2-page PDF with known text.
    src = tmp_path / "mini.pdf"
    doc = fitz.open()
    for t in ("PAGE ONE TEXT", "PAGE TWO TEXT"):
        p = doc.new_page()
        p.insert_text((72, 72), t)
    doc.save(src)
    doc.close()

    out = tmp_path / "out"
    manifest = render_pdf(str(src), str(out), dpi=200)

    assert len(manifest) == 2
    assert (out / "page-0001.png").exists()
    assert (out / "page-0001.txt").exists()
    assert (out / "page-0002.txt").exists()
    assert (out / "page-0002.png").exists()

    # Check text content
    text_one = (out / "page-0001.txt").read_text().strip()
    assert text_one.startswith("PAGE ONE")

    # manifest entries carry page number + file paths
    assert manifest[0]["page"] == 1
    assert manifest[0]["png"].endswith("page-0001.png")
    assert manifest[0]["txt"].endswith("page-0001.txt")

    assert manifest[1]["page"] == 2
    assert manifest[1]["png"].endswith("page-0002.png")
    assert manifest[1]["txt"].endswith("page-0002.txt")

    # Check manifest.json was written
    manifest_file = out / "manifest.json"
    assert manifest_file.exists()
    with open(manifest_file) as f:
        saved_manifest = json.load(f)
    assert saved_manifest == manifest
