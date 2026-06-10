from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
RSS_PATH = ROOT / "web" / "frontend" / "wechat-electronic-textbooks.rss.xml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_child() -> int:
    from web.backend.file_index import append_folo_article_link, build_search_index, search_personal_radar

    payload = {
        "entry": {
            "id": "test-entry-wechat-001",
            "feedId": "test-feed-wechat-001",
            "title": "张雪峰账号突然更新，网友泪崩",
            "url": "https://mp.weixin.qq.com/s/1eq90bKV__qh6HCWqs9JqQ",
        },
        "feed": {"title": "电子课本站"},
    }
    append_folo_article_link(payload)
    build_result = build_search_index(force=True)
    if not build_result.get("ok"):
        raise AssertionError(f"search index rebuild failed: {build_result}")

    result = search_personal_radar("张雪峰账号突然更新", "all", 5, 0, "smart")
    first = result.get("results", [{}])[0] if result.get("results") else {}
    folo_url = str(first.get("folo_url") or "")
    if "timeline/articles/test-feed-wechat-001/test-entry-wechat-001" not in folo_url:
        raise AssertionError(f"missing Folo article deep link: {first}")
    if first.get("folo_label") != "Folo 看原条":
        raise AssertionError(f"wrong Folo label: {first}")

    if not RSS_PATH.exists():
        raise AssertionError(f"missing public RSS: {RSS_PATH}")
    root = ElementTree.parse(RSS_PATH).getroot()
    guids = [item.findtext("guid") or "" for item in root.findall(".//item")]
    if not guids:
        raise AssertionError("public RSS has no items")
    if len(guids) != len(set(guids)):
        raise AssertionError("public RSS item guid values must be unique")

    print(
        {
            "ok": True,
            "query": result.get("query"),
            "folo_url": folo_url,
            "rss_items": len(guids),
            "unique_guids": len(set(guids)),
        }
    )
    return 0


def main() -> int:
    if "--child" in sys.argv:
        return run_child()

    test_cache = ROOT / "data" / "cache" / "redgreen_tests"
    test_cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="folo-links-", dir=str(test_cache)) as link_dir, tempfile.TemporaryDirectory(
        prefix="search-index-", dir=str(test_cache)
    ) as index_dir:
        env = os.environ.copy()
        env["INFORADAR_FOLO_LINK_DIR"] = link_dir
        env["INFORADAR_SEARCH_INDEX_DIR"] = index_dir
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child"],
            cwd=str(ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
