from __future__ import annotations

from web.backend import app


def main() -> None:
    item = app.upsert_collector_adapter(
        {
            "platform": "GitHub审核门测试",
            "name": "deepset-ai/haystack",
            "repo_url": "https://github.com/deepset-ai/haystack",
            "source": "verify_collector_review1",
            "status": "候选",
            "notes": "temporary review gate test",
        }
    )
    fingerprint = item.get("fingerprint")
    assert fingerprint, item
    try:
        data = app.review_collector_adapter(str(fingerprint))
        reviewed = data.get("item") or {}
        assert reviewed.get("github_full_name") == "deepset-ai/haystack", reviewed
        assert reviewed.get("github_license"), reviewed
        assert reviewed.get("allow_execute") is False, reviewed
        assert str(reviewed.get("status") or "").startswith("reviewed-"), reviewed
        print("COLLECTOR_ADAPTER_REVIEW_OK")
        print(f"repo={reviewed.get('github_full_name')}")
        print(f"license={reviewed.get('github_license')}")
        print(f"allow_execute={reviewed.get('allow_execute')}")
    finally:
        rows = [row for row in app.read_collector_adapters() if row.get("fingerprint") != fingerprint]
        app.write_collector_adapters(rows)
        print("COLLECTOR_ADAPTER_REVIEW_TEST_CLEANED")


if __name__ == "__main__":
    main()
