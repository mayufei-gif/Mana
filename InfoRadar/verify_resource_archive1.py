from __future__ import annotations

from web.backend import app


def check(resource_type: str, query: str) -> None:
    data = app.discover_resource_batch(
        {
            "queries": [{"query": query, "type": resource_type}],
            "limit_per_query": 1,
            "auto_add": False,
        }
    )
    assert data.get("count", 0) >= 1, data
    item = data["items"][0]
    assert item.get("source") == "internet-archive-api", item
    assert str(item.get("link") or "").startswith("https://archive.org/details/"), item
    print(f"ARCHIVE_{resource_type}_DISCOVERY_OK")
    print(f"name={item.get('name')}")


def main() -> None:
    check("解密档案", "declassified technology policy")
    check("题库", "exam questions electrical engineering")


if __name__ == "__main__":
    main()
