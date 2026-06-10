from __future__ import annotations

from web.backend import app


def main() -> None:
    added_fingerprints: list[str] = []
    try:
        data = app.discover_resource_batch(
            {
                "queries": [{"query": "artificial intelligence", "type": "书籍"}],
                "limit_per_query": 1,
                "auto_add": True,
            }
        )
        assert data.get("count", 0) >= 1, data
        assert len(data.get("added") or []) >= 1, data
        added_fingerprints = [item.get("fingerprint") for item in data["added"] if item.get("fingerprint")]
        summary = app.resource_hive_summary(limit=500)
        found = [item for item in summary.get("items", []) if item.get("fingerprint") in added_fingerprints]
        assert found, {"added": added_fingerprints, "summary_total": summary.get("total")}
        print("RESOURCE_BATCH_AUTOADD_OK")
        print(f"added={len(added_fingerprints)}")
        print(f"first={found[0].get('name')}")
    finally:
        if added_fingerprints:
            rows = [item for item in app.read_resource_hive_entries() if item.get("fingerprint") not in added_fingerprints]
            app.write_resource_hive_entries(rows)
            print("RESOURCE_BATCH_AUTOADD_TEST_CLEANED")


if __name__ == "__main__":
    main()
