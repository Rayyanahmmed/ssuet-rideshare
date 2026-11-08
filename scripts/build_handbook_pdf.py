"""Render documentation/22-operations-handbook.md to a print-ready PDF.

The handbook is written for a ride-share office, not for developers: it ends up printed,
signed and filed. So the PDF is generated from the same Markdown that lives in the
repository (one source of truth) through a self-contained HTML page — no external CSS, no
web fonts — and printed with Chromium's PDF engine.

    python scripts/build_handbook_pdf.py        # → documentation/22-operations-handbook.pdf
    (needs: markdown-it-py, playwright-core's chromium — both already used by this repo)
"""

from __future__ import annotations

import pathlib
import sys

from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "documentation" / "22-operations-handbook.md"
TARGET_HTML = ROOT / "documentation" / ".handbook.html"
TARGET_PDF = ROOT / "documentation" / "22-operations-handbook.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
  font-size: 10.2pt; line-height: 1.5; color: #12233b; margin: 0;
}
h1 {
  font-size: 22pt; color: #0B1F3A; margin: 0 0 4mm; padding-bottom: 3mm;
  border-bottom: 3px solid #0E9156; letter-spacing: -0.3pt;
}
h2 {
  font-size: 14pt; color: #0B1F3A; margin: 9mm 0 3mm; padding-top: 2mm;
  border-top: 1px solid #E3E9F2; page-break-after: avoid;
}
h1 + p + p + p { }
h3 { font-size: 11.5pt; color: #0E9156; margin: 6mm 0 2mm; page-break-after: avoid; }
p { margin: 0 0 3mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1.6mm; }
strong { color: #0B1F3A; }
code {
  font-family: "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: 9pt;
  background: #F1F5F9; padding: 0.4mm 1.2mm; border-radius: 2px; color: #0B1F3A;
}
pre {
  background: #0B1F3A; color: #E7F8F0; padding: 3.5mm 4mm; border-radius: 3mm;
  font-size: 8.6pt; line-height: 1.45; overflow-wrap: anywhere; white-space: pre-wrap;
  page-break-inside: avoid;
}
pre code { background: none; color: inherit; padding: 0; font-size: 8.6pt; }
table {
  width: 100%; border-collapse: collapse; margin: 0 0 4mm; font-size: 9pt;
  page-break-inside: avoid;
}
th {
  text-align: left; background: #F1F5F9; color: #0B1F3A; font-weight: 600;
  padding: 2mm 2.5mm; border-bottom: 1.5px solid #0B1F3A;
}
td { padding: 1.8mm 2.5mm; border-bottom: 1px solid #E3E9F2; vertical-align: top; }
tr:nth-child(even) td { background: #FAFCFE; }
hr { border: none; border-top: 1px solid #E3E9F2; margin: 7mm 0; }
blockquote { border-left: 3px solid #0E9156; margin: 0 0 3mm; padding-left: 4mm; color: #41536e; }
a { color: #0E9156; text-decoration: none; }
/* keep the sign-off block together on its own page */
h2:last-of-type, h2:last-of-type + table { page-break-inside: avoid; }
"""

FOOTER = """
<div style="width:100%;font-family:'DejaVu Sans',Arial,sans-serif;font-size:7.5pt;
            color:#5A6B85;padding:0 16mm;display:flex;justify-content:space-between;">
  <span>SSUET RideShare — Operations handbook · v1.0.0 · build 15</span>
  <span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>
"""


def build_html() -> str:
    markdown = MarkdownIt("commonmark", {"html": True}).enable("table").enable("strikethrough")
    body = markdown.render(SOURCE.read_text(encoding="utf-8"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>SSUET RideShare — Operations handbook</title>
<style>{CSS}</style></head>
<body>{body}</body></html>"""


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source: {SOURCE}")
        return 2
    html = build_html()
    TARGET_HTML.write_text(html, encoding="utf-8")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — wrote HTML only:", TARGET_HTML)
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(TARGET_HTML.as_uri(), wait_until="load")
        page.pdf(
            path=str(TARGET_PDF),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=FOOTER,
            margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()

    TARGET_HTML.unlink(missing_ok=True)
    size = TARGET_PDF.stat().st_size
    print(f"wrote {TARGET_PDF.relative_to(ROOT)} ({size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
