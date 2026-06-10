from __future__ import annotations

from web.backend import app


def main() -> None:
    added_fingerprints: list[str] = []
    try:
        summary = app.collector_adapter_summary(limit=80)
        assert len(summary.get("presets") or []) >= 7, summary
        data = app.discover_collector_adapters("YouTube", limit=1)
        assert len(data.get("added") or []) >= 1, data
        item = data["added"][0]
        assert item.get("platform") == "YouTube", item
        assert str(item.get("repo_url") or "").startswith("https://github.com/"), item
        added_fingerprints = [entry.get("fingerprint") for entry in data["added"] if entry.get("fingerprint")]
        print("COLLECTOR_ADAPTER_DISCOVERY_OK")
        print(f"name={item.get('name')}")
        print(f"repo={item.get('repo_url')}")
    finally:
        if added_fingerprints:
            rows = [item for item in app.read_collector_adapters() if item.get("fingerprint") not in added_fingerprints]
            app.write_collector_adapters(rows)
            print("COLLECTOR_ADAPTER_TEST_CLEANED")


if __name__ == "__main__":
    main()
