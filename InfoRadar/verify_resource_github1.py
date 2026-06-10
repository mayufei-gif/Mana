from __future__ import annotations

from web.backend import app


def main() -> None:
    data = app.discover_resource_batch(
        {
            "queries": [{"query": "open source agent framework", "type": "软件包"}],
            "limit_per_query": 1,
            "auto_add": False,
        }
    )
    assert data.get("count", 0) >= 1, data
    item = data["items"][0]
    assert item.get("source") == "github-search-api", item
    assert str(item.get("link") or "").startswith("https://github.com/"), item
    print("GITHUB_RESOURCE_DISCOVERY_OK")
    print(f"name={item.get('name')}")
    print(f"link={item.get('link')}")


if __name__ == "__main__":
    main()
