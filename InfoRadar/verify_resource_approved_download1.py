from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from web.backend import app


TEST_URL = "https://www.rfc-editor.org/rfc/rfc9110.txt"


def main() -> None:
    suffix = uuid4().hex
    item = app.upsert_resource_hive_entry(
        {
            "type": "文档",
            "name": f"Codex 批准下载测试 {suffix}",
            "link": TEST_URL,
            "status": "candidate",
            "source": "codex-smoke-test",
        }
    )
    fingerprint = item.get("fingerprint")
    downloaded_path: Path | None = None
    try:
        blocked = app.resource_hive_download_approved(limit=20)
        assert not any(row.get("fingerprint") == fingerprint for row in blocked.get("items", [])), blocked
        approved = app.resource_hive_approve_download(fingerprint)
        approved_item = next(row for row in approved.get("items", []) if row.get("fingerprint") == fingerprint)
        assert approved_item.get("status") == "download-approved", approved_item
        data = app.resource_hive_download_approved(limit=20)
        found = next((row for row in data.get("items", []) if row.get("fingerprint") == fingerprint), None)
        assert found, data
        downloaded_path = Path(found["nas_path"])
        assert downloaded_path.exists(), found
        assert downloaded_path.suffix == ".txt", found
        assert downloaded_path.stat().st_size > 0, found
        print("RESOURCE_APPROVED_DOWNLOAD_OK")
        print(f"path={downloaded_path}")
        print(f"bytes={downloaded_path.stat().st_size}")
    finally:
        rows = [row for row in app.read_resource_hive_entries() if row.get("fingerprint") != fingerprint]
        app.write_resource_hive_entries(rows)
        if downloaded_path and downloaded_path.exists():
            downloaded_path.unlink()
        print("RESOURCE_APPROVED_DOWNLOAD_TEST_CLEANED")


if __name__ == "__main__":
    main()
