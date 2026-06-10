from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "电子课本站"
WECHAT_ID = "dzkbz6"
WECHAT_QUERY = "电子课本站"
PUBLIC_SITE = "https://www.dzkb.org/"
PUBLIC_RSS_URL = "https://inforadar.mana-mana.top/static/wechat-electronic-textbooks.rss.xml"
WECHAT_API_BASE = "http://127.0.0.1:5000"

CSV_PATH = ROOT / "data" / "deduped" / "wechat" / "folo_wechat_electronic_textbooks.csv"
RSS_PATH = ROOT / "web" / "frontend" / "wechat-electronic-textbooks.rss.xml"
OPML_PATH = ROOT / "sources" / "opml" / "folo_wechat_electronic_textbooks.opml"
REPORT_PATH = ROOT / "reports" / "wechat" / "电子课本站_接入状态.md"
STATUS_JSON = ROOT / "logs" / "wechat_electronic_textbooks_status.json"


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def request_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 InfoRadar/WechatSourceCheck",
            "Accept": "text/html,application/rss+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def request_json(url: str, timeout: int = 20) -> dict:
    text = request_text(url, timeout=timeout)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {"success": False, "error": "non_json_response", "raw": text[:500]}
    return value if isinstance(value, dict) else {"success": False, "error": "unexpected_json"}


def post_json(url: str, payload: dict, timeout: int = 20) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "InfoRadar/WechatSourceCheck"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": "non_json_response", "raw": raw[:500]}


def compact_text(value: str, limit: int = 800) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def parse_rss_datetime(value: str, fallback: dt.datetime) -> str:
    text = (value or "").strip()
    if not text:
        return fallback.strftime("%Y-%m-%d %H:%M:%S%z")
    try:
        parsed = dt.datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %z")
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    except ValueError:
        return text


def to_rfc2822_datetime(value: str, fallback: dt.datetime) -> str:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            return parsed.astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            pass
    return fallback.strftime("%a, %d %b %Y %H:%M:%S %z")


def fetch_rss_articles(rss_url: str, checked_at: dt.datetime, limit: int = 50) -> list[dict]:
    if not rss_url:
        return []
    try:
        rss_text = request_text(rss_url, timeout=30)
    except Exception:
        return []
    try:
        root = ElementTree.fromstring(rss_text.encode("utf-8"))
    except ElementTree.ParseError:
        return []
    rows: list[dict] = []
    for item in root.findall(".//item")[:limit]:
        title = compact_text(item.findtext("title") or "", 180)
        link = compact_text(item.findtext("link") or "", 500)
        description = compact_text(item.findtext("description") or "", 900)
        pub_date = parse_rss_datetime(item.findtext("pubDate") or "", checked_at)
        guid = compact_text(item.findtext("guid") or "", 500)
        if not title and not link:
            continue
        rows.append(
            {
                "标题": title or f"{SOURCE_NAME} 文章",
                "来源名称": SOURCE_NAME,
                "Folo订阅源名称": SOURCE_NAME,
                "Folo文件夹路径": "微信公众号/教育学习",
                "发布时间": pub_date,
                "原文URL": link,
                "订阅源URL": PUBLIC_RSS_URL,
                "可抓取RSS链接": PUBLIC_RSS_URL,
                "来源类型": "微信公众号RSS",
                "采集方式": "wechat-download-api rss poll",
                "微信号": WECHAT_ID,
                "标签": "微信公众号;电子课本;教育;学习资料;教材",
                "摘要": description,
                "状态": "active",
                "guid": guid,
            }
        )
    return rows


def extract_meta(content: str) -> dict:
    def meta(name: str) -> str:
        patterns = [
            rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"',
            rf'<meta\s+property="{re.escape(name)}"\s+content="([^"]*)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.I)
            if match:
                return html.unescape(match.group(1)).strip()
        return ""

    title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
    title = compact_text(title_match.group(1), 120) if title_match else SOURCE_NAME
    description = meta("description") or meta("og:description")
    keywords = meta("keywords")
    canonical = ""
    canonical_match = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', content, re.I)
    if canonical_match:
        canonical = canonical_match.group(1).strip()
    stats = {}
    for label in ["电子课本数量", "教材版本", "年级分类", "科目分类"]:
        pattern = rf'([0-9]{{1,6}})</div><div[^>]*>{re.escape(label)}'
        found = re.search(pattern, content)
        if found:
            stats[label] = found.group(1)
    return {
        "title": title or SOURCE_NAME,
        "description": compact_text(description, 500),
        "keywords": keywords,
        "canonical": canonical or PUBLIC_SITE,
        "stats": stats,
    }


def try_wechat_subscription() -> dict:
    query_url = f"{WECHAT_API_BASE}/api/public/searchbiz?query={urllib.parse.quote(WECHAT_QUERY)}"
    try:
        search_result = request_json(query_url, timeout=20)
    except Exception as exc:
        return {"ok": False, "stage": "searchbiz", "error": str(exc)}
    if not search_result.get("success"):
        return {"ok": False, "stage": "searchbiz", "error": search_result.get("error", "search_failed"), "raw": search_result}
    accounts = (search_result.get("data") or {}).get("list") or []
    selected = None
    for account in accounts:
        name = str(account.get("nickname") or "")
        alias = str(account.get("alias") or "")
        if WECHAT_QUERY in name or WECHAT_ID.lower() in alias.lower():
            selected = account
            break
    if not selected and accounts:
        selected = accounts[0]
    if not selected or not selected.get("fakeid"):
        return {"ok": False, "stage": "select_fakeid", "error": "no_matching_fakeid", "accounts": accounts}

    fakeid = selected["fakeid"]
    sub_payload = {"fakeid": fakeid, "nickname": selected.get("nickname") or SOURCE_NAME}
    try:
        subscribe_result = post_json(f"{WECHAT_API_BASE}/api/rss/subscribe", sub_payload, timeout=20)
    except Exception as exc:
        return {"ok": False, "stage": "subscribe", "error": str(exc), "account": selected}
    try:
        poll_result = post_json(f"{WECHAT_API_BASE}/api/rss/poll", {}, timeout=30)
    except Exception as exc:
        poll_result = {"success": False, "error": str(exc)}
    return {
        "ok": True,
        "stage": "subscribed",
        "account": selected,
        "subscribe_result": subscribe_result,
        "poll_result": poll_result,
        "rss_url": f"{WECHAT_API_BASE}/api/rss/{urllib.parse.quote(fakeid)}",
    }


def build_rows(meta: dict, checked_at: dt.datetime, wechat_status: dict) -> list[dict]:
    article_rows = fetch_rss_articles(str(wechat_status.get("rss_url", "")), checked_at) if wechat_status.get("ok") else []
    if article_rows:
        return article_rows

    summary_bits = [
        meta.get("description") or "电子课本站提供中小学电子课本目录，支持按教材版本、年级和科目筛选。",
        f"微信号：{WECHAT_ID}",
    ]
    if meta.get("stats"):
        summary_bits.append("站点数据：" + "；".join(f"{k}{v}" for k, v in meta["stats"].items()))
    if not wechat_status.get("ok"):
        summary_bits.append(f"微信 searchbiz 当前未打通：{wechat_status.get('error') or wechat_status.get('stage')}")
    return [
        {
            "标题": "电子课本站：微信公众号与电子课本资源源",
            "来源名称": SOURCE_NAME,
            "Folo订阅源名称": SOURCE_NAME,
            "Folo文件夹路径": "微信公众号/教育学习",
            "发布时间": checked_at.strftime("%Y-%m-%d %H:%M:%S%z"),
            "原文URL": meta.get("canonical") or PUBLIC_SITE,
            "订阅源URL": PUBLIC_RSS_URL,
            "可抓取RSS链接": PUBLIC_RSS_URL,
            "来源类型": "微信公众号预备RSS",
            "采集方式": "wechat-download-api searchbiz + public-site fallback",
            "微信号": WECHAT_ID,
            "标签": "微信公众号;电子课本;教育;学习资料;教材",
            "摘要": " ".join(summary_bits),
            "状态": "active" if wechat_status.get("ok") else "wechat_search_pending",
        }
    ]


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "标题",
        "来源名称",
        "Folo订阅源名称",
        "Folo文件夹路径",
        "发布时间",
        "原文URL",
        "订阅源URL",
        "可抓取RSS链接",
        "来源类型",
        "采集方式",
        "微信号",
        "标签",
        "摘要",
        "状态",
        "guid",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_rss(rows: list[dict], checked_at: dt.datetime) -> None:
    RSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for row in rows:
        title = escape(row["标题"])
        link = escape(row["原文URL"])
        description = escape(row["摘要"])
        pub_date = to_rfc2822_datetime(row.get("发布时间", ""), checked_at)
        guid_value = row.get("guid") or row.get("原文URL") or f"inforadar-wechat-{WECHAT_ID}-{row['标题']}"
        guid = escape(guid_value)
        items.append(
            f"<item><title>{title}</title><link>{link}</link><guid isPermaLink=\"false\">{guid}</guid>"
            f"<pubDate>{pub_date}</pubDate><description>{description}</description>"
            f"<category>微信公众号</category><category>教育学习</category></item>"
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(SOURCE_NAME)} - InfoRadar</title>
    <link>{escape(PUBLIC_SITE)}</link>
    <description>InfoRadar 生成的电子课本站微信公众号预备 RSS。</description>
    <lastBuildDate>{checked_at.strftime("%a, %d %b %Y %H:%M:%S %z")}</lastBuildDate>
    {''.join(items)}
  </channel>
</rss>
"""
    RSS_PATH.write_text(content, encoding="utf-8")


def write_opml() -> None:
    OPML_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = now_local().strftime("%a, %d %b %Y %H:%M:%S %z")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>InfoRadar 微信公众号源 - 电子课本站</title>
    <dateCreated>{escape(now)}</dateCreated>
  </head>
  <body>
    <outline text="微信公众号" title="微信公众号">
      <outline type="rss" text="{escape(SOURCE_NAME)}" title="{escape(SOURCE_NAME)}" xmlUrl="{escape(PUBLIC_RSS_URL)}" htmlUrl="{escape(PUBLIC_SITE)}"/>
    </outline>
  </body>
</opml>
"""
    OPML_PATH.write_text(content, encoding="utf-8")


def write_report(rows: list[dict], meta: dict, wechat_status: dict, checked_at: dt.datetime) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 电子课本站 微信公众号接入状态",
        "",
        f"- 检查时间：{checked_at.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- 微信公众号：{SOURCE_NAME}",
        f"- 微信号：{WECHAT_ID}",
        f"- 公开站点：{meta.get('canonical') or PUBLIC_SITE}",
        f"- Folo 可导入 RSS：{PUBLIC_RSS_URL}",
        f"- OPML：{OPML_PATH}",
        f"- InfoRadar 索引 CSV：{CSV_PATH}",
        f"- 微信 API 状态：{'已订阅' if wechat_status.get('ok') else 'searchbiz 未打通'}",
    ]
    if not wechat_status.get("ok"):
        lines.append(f"- 微信 API 失败阶段：{wechat_status.get('stage')}")
        lines.append(f"- 微信 API 错误：{wechat_status.get('error')}")
    lines.extend(["", "## 已写入记录", ""])
    for row in rows:
        lines.append(f"- {row['标题']}｜{row['发布时间']}｜{row['状态']}")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    checked_at = now_local()
    try:
        site_html = request_text(PUBLIC_SITE, timeout=25)
        meta = extract_meta(site_html)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        meta = {
            "title": SOURCE_NAME,
            "description": f"公开站点抓取失败：{exc}",
            "canonical": PUBLIC_SITE,
            "stats": {},
        }

    wechat_status = try_wechat_subscription()
    rows = build_rows(meta, checked_at, wechat_status)
    write_csv(rows)
    write_rss(rows, checked_at)
    write_opml()
    write_report(rows, meta, wechat_status, checked_at)
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(
        json.dumps(
            {
                "ok": True,
                "checked_at": checked_at.isoformat(),
                "source": SOURCE_NAME,
                "wechat_id": WECHAT_ID,
                "wechat_status": wechat_status,
                "csv": str(CSV_PATH),
                "rss": str(RSS_PATH),
                "public_rss_url": PUBLIC_RSS_URL,
                "opml": str(OPML_PATH),
                "report": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "wechat_ok": bool(wechat_status.get("ok")), "csv": str(CSV_PATH), "rss": str(RSS_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
