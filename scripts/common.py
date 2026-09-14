"""Shared helpers for all generator scripts."""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "generated"
ASSETS = ROOT / "assets"

FG = "#e6e6e6"      # primary text/line color
FG_DIM = "#8a8a8a"  # secondary/dim color
BG = "#0d1117"      # GitHub dark-mode background (transparent works too)
ACCENT = "#58a6ff"

FONT_FAMILY = "JetBrains Mono, ui-monospace, SFMono-Regular, Consolas, monospace"

_FONT_PATH = ASSETS / "fonts" / "JetBrainsMono-Regular-subset.woff2"
_font_css_cache: str | None = None


def embedded_font_style() -> str:
    """
    Return a <style> block that @font-face-embeds the subsetted, base64-
    encoded JetBrains Mono WOFF2 directly inside the SVG (see
    assets/fonts/JetBrainsMono-Regular-subset.woff2, generated from the
    upstream release and subset to basic-Latin only -- the full character
    set these SVGs ever draw). Because the font data is inlined as a data
    URI, the SVG makes zero external requests and renders identically
    everywhere, instead of silently falling back to whatever monospace
    font happens to be installed on the viewer's system (which would
    break the fixed character-grid geometry the portrait relies on).
    License: SIL Open Font License 1.1, see assets/fonts/JetBrainsMono-OFL.txt.
    """
    global _font_css_cache
    if _font_css_cache is not None:
        return _font_css_cache
    import base64
    if not _FONT_PATH.exists():
        _font_css_cache = ""
        return _font_css_cache
    b64 = base64.b64encode(_FONT_PATH.read_bytes()).decode("ascii")
    _font_css_cache = (
        "<style>"
        "@font-face{"
        "font-family:'JetBrains Mono';"
        "font-style:normal;font-weight:400;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
        "}"
        "text{font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Consolas,monospace;}"
        "</style>"
    )
    return _font_css_cache


def svg_header(width: int, height: int, extra: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}">{extra}'
    )


def write_if_changed(path: Path, content: str) -> bool:
    """Write file only if content actually changed. Returns True if written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        print(f"Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return val
