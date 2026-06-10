from __future__ import annotations

from uuid import uuid4

from web.backend import app as backend


def main() -> None:
    key = f"codex-folo-timeline-test-{uuid4().hex}"
    payload = {
        "key": key,
        "title": "Codex Folo 时间线测试源",
        "source": "codex-smoke-test",
        "url": "https://app.folo.is/?test=codex-folo-timeline",
    }
    try:
        first = backend.record_folo_timeline_click(payload)
        backend.record_folo_timeline_click(payload)
        third = backend.record_folo_timeline_click(payload)
        summary = backend.folo_timeline_summary(limit=300)
        found = next((item for item in summary.get("items", []) if item.get("key") == key), None)
        starred = next((item for item in summary.get("stars", []) if item.get("key") == key), None)
        assert first.get("count") == 1, first
        assert third.get("count") == 3, third
        assert found and found.get("count") == 3, found
        assert starred and starred.get("count") == 3, starred
        print("FOLO_TIMELINE_WRITE_READ_OK")
        print(f"key={key}")
        print(f"count={found.get('count')}")
        print(f"star_count={summary.get('star_count')}")
        print(f"path={summary.get('path')}")
    finally:
        rows = [item for item in backend.read_folo_timeline_entries() if item.get("key") != key]
        backend.write_folo_timeline_entries(rows)
        print("FOLO_TIMELINE_TEST_CLEANED")


if __name__ == "__main__":
    main()
