from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from web.backend import app


def main() -> None:
    suffix = uuid4().hex
    item = app.upsert_resource_hive_entry(
        {
            "type": "书籍",
            "name": f"Codex URL 归档测试 {suffix}",
            "link": f"https://openlibrary.org/test/archive-link-{suffix}",
            "status": "candidate",
            "source": "codex-smoke-test",
        }
    )
    fingerprint = item.get("fingerprint")
    written_path: Path | None = None
    try:
        data = app.resource_hive_archive_links(limit=200)
        found = next((row for row in data.get("items", []) if row.get("fingerprint") == fingerprint), None)
        assert found, data
        written_path = Path(found["nas_path"])
        assert written_path.exists(), found
        text = written_path.read_text(encoding="utf-8")
        assert "[InternetShortcut]" in text, text
        assert item["link"] in text, text
        summary = app.resource_hive_summary(limit=500)
        stored = next((row for row in summary.get("items", []) if row.get("fingerprint") == fingerprint), None)
        assert stored and stored.get("nas_path") == str(written_path), stored
        print("RESOURCE_ARCHIVE_LINKS_OK")
        print(f"path={written_path}")
    finally:
        rows = [row for row in app.read_resource_hive_entries() if row.get("fingerprint") != fingerprint]
        app.write_resource_hive_entries(rows)
        if written_path and written_path.exists():
            written_path.unlink()
        print("RESOURCE_ARCHIVE_LINKS_TEST_CLEANED")


if __name__ == "__main__":
    main()
