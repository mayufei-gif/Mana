from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except Exception:
    TestClient = None


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


os.environ["WEB_ACCESS_TOKEN"] = ""
os.environ["WEB_TOTP_SECRET"] = ""

import web.backend.app as backend_app  # noqa: E402

app = backend_app.app
app.dependency_overrides[backend_app.require_access] = lambda: None


def assert_wechat_result_shape(item: dict) -> None:
    required = ["fakeid", "nickname", "alias", "actions"]
    missing = [key for key in required if key not in item]
    if missing:
        raise AssertionError(f"missing result fields: {missing}; item={item}")
    action_keys = {action.get("key") for action in item.get("actions") or []}
    expected_actions = {"subscribe_wechat", "poll_articles", "open_rss", "open_folo", "search_inforadar"}
    missing_actions = expected_actions - action_keys
    if missing_actions:
        raise AssertionError(f"missing actions: {sorted(missing_actions)}; item={item}")


def main() -> int:
    calls: list[tuple[str, str, dict | None]] = []
    subscribed_fakeids: set[str] = set()
    fake_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>人民日报</title>
<link>http://127.0.0.1:5000/api/rss/MjM5MjAxNDM4MA==</link>
<item><title>测试文章</title><link>https://mp.weixin.qq.com/s/test</link><pubDate>Wed, 10 Jun 2026 00:00:00 +0000</pubDate><description>测试摘要</description></item>
</channel></rss>"""

    def fake_wechat_api_json(path: str, method: str = "GET", payload: dict | None = None, timeout: int = 40) -> dict:
        calls.append((path, method, payload))
        if path.startswith("/api/public/searchbiz"):
            return {
                "success": True,
                "data": {
                    "list": [
                        {
                            "fakeid": "MjM5MjAxNDM4MA==",
                            "nickname": "人民日报",
                            "alias": "rmrbwx",
                            "round_head_img": "",
                            "service_type": 0,
                        }
                    ]
                },
            }
        if path == "/api/rss/subscriptions":
            return {"success": True, "data": [{"fakeid": item} for item in sorted(subscribed_fakeids)]}
        if path == "/api/rss/subscribe":
            if not payload or payload.get("fakeid") != "MjM5MjAxNDM4MA==":
                raise AssertionError(f"bad subscribe payload: {payload}")
            subscribed_fakeids.add(payload["fakeid"])
            return {"success": True, "data": {"fakeid": payload["fakeid"]}}
        if path == "/api/rss/poll":
            return {"success": True, "data": {"articles": 3}}
        raise AssertionError(f"unexpected wechat api call: {method} {path} {payload}")

    def fake_wechat_api_text(path: str, timeout: int = 40) -> str:
        if path.startswith("/api/rss/"):
            return fake_rss
        raise AssertionError(f"unexpected wechat rss call: {path}")

    backend_app.wechat_api_json = fake_wechat_api_json
    backend_app.wechat_api_text = fake_wechat_api_text
    with tempfile.TemporaryDirectory() as temp_dir:
        backend_app.FOLO_MANUAL_ENTRIES_PATH = Path(temp_dir) / "manual_entries.jsonl"
        backend_app.import_wechat_rss_articles = lambda fakeid, nickname="", rebuild_index=True: {
            "ok": True,
            "fakeid": fakeid,
            "nickname": nickname,
            "article_count": 1,
            "csv": str(Path(temp_dir) / "folo_wechat_test.csv"),
            "rss_url": backend_app.wechat_rss_url(fakeid),
            "index": {"ok": True, "rebuilt": True},
        }
        if TestClient:
            client = TestClient(app)
            response = client.post("/api/manual-hive/wechat/search", json={"query": "人民日报"})
            if response.status_code != 200:
                raise AssertionError(f"wechat search endpoint failed: {response.status_code} {response.text[:500]}")
            data = response.json()
        else:
            data = backend_app.search_wechat_accounts("人民日报")
        if not data.get("ok"):
            raise AssertionError(f"wechat search not ok: {json.dumps(data, ensure_ascii=False)[:500]}")
        items = data.get("items") or []
        if not items:
            raise AssertionError(f"wechat search returned no items: {data}")
        assert_wechat_result_shape(items[0])
        if "127.0.0.1" in items[0].get("rss_url", "") or not items[0].get("rss_url", "").startswith("/api/manual-hive/wechat/rss"):
            raise AssertionError(f"rss_url should be same-origin proxy: {items[0].get('rss_url')}")
        if not items[0].get("rss_view_url", "").startswith("/api/manual-hive/wechat/rss-view"):
            raise AssertionError(f"rss_view_url should be human-readable proxy: {items[0].get('rss_view_url')}")

        if TestClient:
            rss_response = client.get("/api/manual-hive/wechat/rss", params={"fakeid": items[0]["fakeid"]})
            if rss_response.status_code != 200 or "测试文章" not in rss_response.text:
                raise AssertionError(f"wechat rss proxy failed: {rss_response.status_code} {rss_response.text[:300]}")
            view_response = client.get("/api/manual-hive/wechat/rss-view", params={"fakeid": items[0]["fakeid"]})
            if view_response.status_code != 200 or "测试文章" not in view_response.text or "打开微信原文" not in view_response.text:
                raise AssertionError(f"wechat rss view failed: {view_response.status_code} {view_response.text[:300]}")
            subscribe = client.post(
                "/api/manual-hive/wechat/subscribe",
                json={"fakeid": items[0]["fakeid"], "nickname": items[0]["nickname"], "poll": True},
            )
            if subscribe.status_code != 200:
                raise AssertionError(f"wechat subscribe endpoint failed: {subscribe.status_code} {subscribe.text[:500]}")
            subscribed = subscribe.json()
            folo_open = client.post(
                "/api/manual-hive/wechat/folo-open",
                json={"fakeid": items[0]["fakeid"], "nickname": items[0]["nickname"], "poll": True},
                headers={"host": "inforadar.mana-mana.top", "x-forwarded-proto": "https"},
            )
            if folo_open.status_code != 200:
                raise AssertionError(f"wechat folo-open endpoint failed: {folo_open.status_code} {folo_open.text[:500]}")
            folo_data = folo_open.json()
            if "/api/folo/wechat-feed" not in folo_data.get("feed_url", ""):
                raise AssertionError(f"folo-open must return public feed_url: {folo_data}")
            if "app.folo.is" not in folo_data.get("folo_open_url", ""):
                raise AssertionError(f"folo-open must return Folo open URL: {folo_data}")
            if folo_data.get("clipboard_text") != folo_data.get("feed_url"):
                raise AssertionError(f"folo-open clipboard_text must equal feed_url: {folo_data}")
            feed_response = client.get(
                "/api/folo/wechat-feed",
                params={"fakeid": items[0]["fakeid"]},
                headers={"host": "inforadar.mana-mana.top", "x-forwarded-proto": "https"},
            )
            if feed_response.status_code != 200 or "测试文章" not in feed_response.text:
                raise AssertionError(f"public Folo feed failed: {feed_response.status_code} {feed_response.text[:300]}")
            if "https://inforadar.mana-mana.top/api/folo/wechat-feed" not in feed_response.text:
                raise AssertionError(f"public Folo feed must rewrite self URL to public feed: {feed_response.text[:500]}")
        else:
            subscribed = backend_app.subscribe_wechat_account(items[0]["fakeid"], items[0]["nickname"], poll=True)
        if not subscribed.get("ok") or not subscribed.get("rss_url") or not subscribed.get("manual_entry"):
            raise AssertionError(f"wechat subscribe bad response: {json.dumps(subscribed, ensure_ascii=False)[:500]}")
        if subscribed.get("import_result", {}).get("article_count") != 1:
            raise AssertionError(f"wechat subscribe did not import articles: {subscribed}")
        if not backend_app.FOLO_MANUAL_ENTRIES_PATH.exists():
            raise AssertionError("manual entry file was not created")

    print({"ok": True, "count": len(items), "first": items[0].get("nickname"), "calls": len(calls)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
