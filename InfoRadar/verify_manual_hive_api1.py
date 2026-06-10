from __future__ import annotations

from uuid import uuid4

from web.backend import app as backend


def main() -> None:
    suffix = uuid4().hex
    name = f"Codex 手动信息测试源 {suffix}"
    payload = {
        "platform": "公众号",
        "name": name,
        "url": f"https://mp.weixin.qq.com/s/codex-manual-hive-{suffix}",
        "score": 65,
    }
    try:
        first = backend.upsert_manual_hive_entry(payload)
        second = backend.upsert_manual_hive_entry(payload)
        summary = backend.manual_hive_summary(limit=300)
        found = next((item for item in summary.get("items", []) if item.get("fingerprint") == first.get("fingerprint")), None)
        assert first.get("seen_count") == 1, first
        assert second.get("seen_count") == 2, second
        assert found and found.get("seen_count") == 2, found
        assert found.get("platform") == "公众号", found
        print("MANUAL_HIVE_WRITE_READ_OK")
        print(f"fingerprint={found.get('fingerprint')}")
        print(f"seen_count={found.get('seen_count')}")
        print(f"total={summary.get('total')}")
        print(f"path={summary.get('path')}")
    finally:
        rows = [
            item
            for item in backend.read_manual_hive_entries()
            if item.get("name") != name and item.get("fingerprint") != payload.get("fingerprint")
        ]
        backend.write_manual_hive_entries(rows)
        print("MANUAL_HIVE_TEST_CLEANED")


if __name__ == "__main__":
    main()
