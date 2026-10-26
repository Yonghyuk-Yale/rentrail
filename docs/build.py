"""Build the self-contained report.html and slides.html (every image embedded as a data URI).

    python docs/build.py

Sources: docs/report_src.html, docs/slides_src.html, docs/img/*.jpg. Output: report.html and slides.html
in the repo root, which open by double-click on any computer.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
MAX_W = 1500


def data_uri(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build(src: str, out: str) -> None:
    html = (DOCS / src).read_text(encoding="utf-8")
    cache: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name not in cache:
            cache[name] = data_uri(DOCS / "img" / name)
        return f'src="{cache[name]}"'

    html = re.sub(r'src="img/([^"]+)"', repl, html)
    (ROOT / out).write_text(html, encoding="utf-8")
    print(f"{out}: {len(html) / 1e6:.1f} MB, {len(cache)} images embedded")


if __name__ == "__main__":
    build("report_src.html", "report.html")
    build("slides_src.html", "slides.html")
