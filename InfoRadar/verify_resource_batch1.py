from __future__ import annotations

from web.backend import app


def main() -> None:
    data = app.discover_resource_batch(
        {
            "queries": [{"query": "artificial intelligence", "type": "书籍"}],
            "limit_per_query": 1,
            "auto_add": False,
        }
    )
    assert data.get("ok") is True, data
    assert len(data.get("queries") or []) == 1, data
    assert isinstance(data.get("items"), list), data
    assert data.get("count", 0) >= 1, data
    print("RESOURCE_BATCH_DISCOVERY_OK")
    print(f"count={data.get('count')}")
    print(f"first={data['items'][0].get('name')}")


if __name__ == "__main__":
    main()
