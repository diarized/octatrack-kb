from build.assemble import assemble
import pathlib, frontmatter


def test_assemble_concatenates_pages_with_frontmatter(tmp_path):
    pages = tmp_path / "pages"; pages.mkdir()
    (pages / "page-0015.md").write_text("Alpha.")
    (pages / "page-0016.md").write_text("Beta.")
    toc = tmp_path / "toc.yaml"
    toc.write_text(
        'sections:\n'
        '  - id: demo\n    title: "Demo"\n    chapter: 2\n'
        '    section: "2.2"\n    pages: [15, 16]\n')
    out = tmp_path / "reference"
    assemble(str(pages), str(toc), str(out))

    post = frontmatter.load(out / "demo.md")
    assert post["id"] == "demo"
    assert post["chapter"] == 2
    assert post["source_pages"] == [15, 16]
    assert post["concepts"] == []          # filled in Phase D
    assert "Alpha." in post.content and "Beta." in post.content
