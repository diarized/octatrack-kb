"""Render every PDF page to PNG + extract its text layer.

MAGIC: dpi=200 keeps an A4 page's long edge (~2339px) under the Opus 4.8
2576px vision cap, so the model sees full resolution with no server-side
downscale. The text layer is saved alongside each PNG and later handed to the
vision model as a label hint, which anchors diagram labels without OCR.
"""
from __future__ import annotations

import json
import pathlib

import fitz  # PyMuPDF


def render_pdf(pdf_path: str, out_dir: str, dpi: int = 200) -> list[dict]:
    """Render PDF pages to PNG and extract text layers.

    Args:
        pdf_path: Path to input PDF file.
        out_dir: Output directory for PNG files and manifest.
        dpi: Render DPI (default 200).

    Returns:
        List of manifest entries, each with page number, PNG path, and text path.
    """
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    manifest = []
    for i, page in enumerate(doc, start=1):
        stem = f"page-{i:04d}"
        png_path = out / f"{stem}.png"
        txt_path = out / f"{stem}.txt"

        # Render page to PNG
        page.get_pixmap(matrix=matrix).save(str(png_path))

        # Extract text layer
        txt_path.write_text(page.get_text("text"), encoding="utf-8")

        manifest.append(
            {
                "page": i,
                "png": str(png_path),
                "txt": str(txt_path),
            }
        )

    doc.close()

    # Write manifest
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return manifest
