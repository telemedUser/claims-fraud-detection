"""Prints metadata and text of generated test documents and renders page 1 of each to PNG for review."""
from pathlib import Path

from pypdf import PdfReader

root = Path(__file__).resolve().parent.parent / "test_documents"
for pdf in sorted(root.rglob("*.pdf")):
    r = PdfReader(pdf)
    meta = {k: v for k, v in (r.metadata or {}).items() if k != "/Nonce"}
    print(f"=== {pdf.relative_to(root)}  pages={len(r.pages)}")
    print("   meta:", meta)
    print("   text:", " ".join(r.pages[0].extract_text().split())[:260])
    try:
        import pypdfium2 as pdfium
        img = pdfium.PdfDocument(str(pdf))[0].render(scale=1.3).to_pil()
        img.save(pdf.with_suffix(".preview.png"))
    except ImportError:
        pass
