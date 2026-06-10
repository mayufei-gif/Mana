from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "web" / "frontend" / "app.js"
INDEX_HTML = ROOT / "web" / "frontend" / "index.html"
STYLE_CSS = ROOT / "web" / "frontend" / "style.css"


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> int:
    app_js = APP_JS.read_text(encoding="utf-8")
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    style_css = STYLE_CSS.read_text(encoding="utf-8")

    assert_contains(app_js, "function headerVisibilityForScroll", "pure scroll-direction decision")
    assert_contains(app_js, 'document.addEventListener("scroll"', "app scroll listener")
    assert_contains(app_js, "state.lastHeaderScrollY", "last scroll position state")
    assert_contains(app_js, "state.headerScrollPinnedUntil", "tap/focus pin guard")
    assert_contains(app_js, "headerVisibilityForScroll(state.lastHeaderScrollY", "scroll listener uses decision")

    assert_contains(index_html, "function headerVisibilityForScroll", "inline fallback scroll-direction decision")
    assert_contains(index_html, 'document.addEventListener("scroll"', "inline fallback scroll listener")
    assert_contains(index_html, "lastHeaderScrollY", "inline fallback last scroll position")

    collapsed = re.search(r"\.app-shell\.header-collapsed\s+\.site-header\s*\{([^}]*)\}", style_css, re.S)
    if not collapsed:
        raise AssertionError("missing collapsed site-header CSS")
    if "translateY(-100%)" not in collapsed.group(1):
        raise AssertionError("collapsed header must fully leave the viewport instead of leaving a tappable sliver")

    zone = re.search(r"\.header-hover-zone\s*\{([^}]*)\}", style_css, re.S)
    if not zone:
        raise AssertionError("missing header hover zone CSS")
    if "height: 34px" in zone.group(1):
        raise AssertionError("hover zone must not keep a large visible/tappable top strip on tablets")

    print({"ok": True, "checked": ["app.js", "index.html", "style.css"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
