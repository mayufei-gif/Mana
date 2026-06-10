from __future__ import annotations

from uuid import uuid4

from web.backend import app


def main() -> None:
    suffix = uuid4().hex
    item = app.upsert_resource_hive_entry(
        {
            "type": "书籍",
            "name": f"Codex NAS 归档计划测试 {suffix}",
            "link": f"https://openlibrary.org/test/{suffix}",
            "status": "candidate",
            "source": "codex-smoke-test",
        }
    )
    fingerprint = item.get("fingerprint")
    try:
        plan = app.resource_hive_archive_plan(limit=200)
        found = next((row for row in plan.get("items", []) if row.get("fingerprint") == fingerprint), None)
        assert found, plan
        assert found.get("safe_to_auto_download") is False, found
        assert found.get("suggested_nas_path"), found
        assert found.get("suggested_nas_path", "").endswith(".url"), found
        print("RESOURCE_ARCHIVE_PLAN_OK")
        print(f"suggested={found.get('suggested_nas_path')}")
        print(f"safe_to_auto_download={found.get('safe_to_auto_download')}")
    finally:
        rows = [row for row in app.read_resource_hive_entries() if row.get("fingerprint") != fingerprint]
        app.write_resource_hive_entries(rows)
        print("RESOURCE_ARCHIVE_PLAN_TEST_CLEANED")


if __name__ == "__main__":
    main()
