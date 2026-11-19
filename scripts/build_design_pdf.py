"""Renders docs/SOLUTION_DESIGN.md (including its Mermaid diagrams) to docs/SOLUTION_DESIGN.pdf.

Usage:  python scripts/build_design_pdf.py
Needs:  Playwright (in requirements.txt) and Microsoft Edge, plus internet access for marked and mermaid from
        cdn.jsdelivr.net. Run it again after editing the Markdown.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "SOLUTION_DESIGN.md"
OUT = ROOT / "docs" / "SOLUTION_DESIGN.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #1e293b; font-size: 10.5pt; line-height: 1.5; }
h1 { color: #003864; font-size: 24pt; margin: 0 0 4pt; border-bottom: 3px solid #0071c2; padding-bottom: 6pt; }
h2 { color: #003864; font-size: 15pt; margin: 22pt 0 6pt; border-bottom: 1px solid #d6eafa; padding-bottom: 3pt;
     break-after: avoid; }
h3 { color: #005c9f; font-size: 12pt; margin: 14pt 0 4pt; break-after: avoid; }
p { margin: 5pt 0; }
a { color: #0071c2; }
hr { border: 0; border-top: 1px solid #d6eafa; margin: 14pt 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #0071c2; color: #fff; text-align: left; padding: 4pt 6pt; font-weight: 600; }
td { border-bottom: 1px solid #e2e8f0; padding: 4pt 6pt; vertical-align: top; }
tr:nth-child(even) td { background: #f4f8fc; }
code { font-family: Consolas, monospace; font-size: 8.8pt; background: #eef6fd; padding: 0 3pt; border-radius: 3px; }
pre { background: #002444; color: #e2e8f0; padding: 8pt 10pt; border-radius: 4px; font-size: 8.6pt;
      white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
ul, ol { margin: 4pt 0 4pt 18pt; padding: 0; }
li { margin: 2pt 0; }
.mermaid { text-align: center; margin: 10pt 0; break-inside: avoid; }
.mermaid svg { max-width: 100%; height: auto; }
blockquote { border-left: 3px solid #0071c2; margin: 8pt 0; padding: 2pt 10pt; color: #334155; background: #f4f8fc; }
"""

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head><body><main id="doc"></main>
<script>
  const md = {md};
  const html = marked.parse(md, {{ gfm: true }});
  const doc = document.getElementById('doc');
  doc.innerHTML = html;
  doc.querySelectorAll('pre code.language-mermaid').forEach((c) => {{
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = c.textContent;
    c.parentElement.replaceWith(div);
  }});
  mermaid.initialize({{ startOnLoad: false, theme: 'base', securityLevel: 'strict',
    themeVariables: {{ primaryColor: '#eef6fd', primaryBorderColor: '#0071c2', primaryTextColor: '#002444',
                      lineColor: '#005c9f', fontFamily: 'Segoe UI, Arial, sans-serif' }} }});
  mermaid.run({{ querySelector: '.mermaid' }}).then(() => {{ document.body.dataset.ready = '1'; }})
    .catch((e) => {{ document.body.dataset.ready = 'error:' + e; }});
</script></body></html>"""

FOOTER = ('<div style="width:100%;font-size:8px;color:#64748b;padding:0 16mm;display:flex;justify-content:space-between;">'
          '<span>ClaimShield: Solution Design</span>'
          '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


def main() -> None:
    html = HTML.format(css=CSS, md=json.dumps(SRC.read_text(encoding="utf-8")))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.wait_for_function("document.body.dataset.ready", timeout=60000)
        state = page.evaluate("document.body.dataset.ready")
        if state != "1":
            sys.exit(f"Diagram rendering failed: {state}")
        page.pdf(path=str(OUT), format="A4", print_background=True, display_header_footer=True,
                 header_template="<div></div>", footer_template=FOOTER,
                 margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
        browser.close()
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
