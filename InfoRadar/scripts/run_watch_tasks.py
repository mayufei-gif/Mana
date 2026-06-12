#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import datetime as dt
import os
import hashlib
import os
import json
import os
import re
import os
import urllib.request
import os
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from local_search import query_terms, score_text
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
WATCH_DIR = ROOT / "data" / "watch"
SNAPSHOT_DIR = WATCH_DIR / "snapshots"
UPDATE_DIR = WATCH_DIR / "updates"
ERROR_DIR = WATCH_DIR / "errors"
HISTORY_DIR = WATCH_DIR / "history"
WATCH_REQUESTS = ROOT / "sources" / "watch_only_requests.csv"

CORE_WATCH_REQUESTS = [
    "山西晋中理工学院 通知 公告 教务 学工 奖学金 入团 竞赛 就业",
    "山西晋中理工学院 校园招聘 实习 就业 双选会",
    "山西人社 技能补贴 电工证 职业技能 报名",
    "山西焦煤 霍州煤电 晋能控股 潞安 太重 招聘 校招 岗位",
    "PLC 变频器 ABB ACS800 工业机器人 电气维修 控制柜",
]

UPDATE_HEADERS = [
    "序号",
    "update_id",
    "watch_id",
    "watch_keyword",
    "source_name",
    "title",
    "url",
    "published_at",
    "detected_at",
    "broad_category",
    "source_layer",
    "decision_scope",
    "risk_level",
    "why_relevant",
    "suggested_action",
    "status",
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page_title = ""
        self._in_title = False
        self._current_href = ""
        self._current_text: list[str] = []
        self.links: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "a":
            self._current_href = attrs_dict.get("href", "")
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page_title += data
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "a" and self._current_href:
            text = compact("".join(self._current_text))
            if text:
                self.links.append({"title": text, "href": self._current_href})
            self._current_href = ""
            self._current_text = []


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def sha(text: str, length: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:length]


def visible_date_from_title(title: str) -> str:
    text = compact(title)
    # Some school pages render titles like "12 2025.06 标题", meaning 2025-06-12.
    match = re.search(r"^\s*(\d{1,2})\s+(20\d{2})[./-](\d{1,2})\b", text)
    if match:
        day, year, month = match.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            return ""
    match = re.search(r"\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            return ""
    return ""


def ensure_dirs() -> None:
    for path in [SNAPSHOT_DIR, UPDATE_DIR, ERROR_DIR, HISTORY_DIR, RETURN_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_watch_requests() -> list[dict]:
    rows = read_csv(WATCH_REQUESTS)
    existing = {compact(row.get("关键词", "")) for row in rows}
    for keyword in CORE_WATCH_REQUESTS:
        if keyword in existing:
            continue
        rows.append(
            {
                "task_id": "builtin_core_watch",
                "关键词": keyword,
                "状态": "builtin",
                "创建时间": "",
                "备注": "核心刚需默认观察词",
            }
        )
    return rows


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_http_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def infer_builtin_sources(keyword: str) -> list[dict]:
    rows: list[dict] = []
    if any(term in keyword for term in ["山西晋中理工", "晋中理工", "奖学金", "入团", "团委", "学工"]):
        rows.extend(
            [
                {
                    "源名称": "山西晋中理工学院官网",
                    "官网链接": "https://www.sxjzit.edu.cn/",
                    "推荐Folo文件夹": "我的学校/通知公告",
                    "主分类": "我的学校",
                    "推荐原因": "学校官方公开主页，适合作为奖学金、入团、比赛和通知线索入口",
                    "状态": "builtin_watch",
                    "备注": "公开官网，不需要登录",
                },
                {
                    "源名称": "山西晋中理工学院智慧就业系统",
                    "官网链接": "https://jygl.sxjzit.edu.cn/",
                    "推荐Folo文件夹": "我的学校/校园招聘",
                    "主分类": "我的学校",
                    "推荐原因": "学校就业系统公开入口，适合作为校园招聘、宣讲会、双选会观察源",
                    "状态": "builtin_watch",
                    "备注": "公开官网，不需要登录",
                },
                {
                    "源名称": "山西晋中理工学院职位信息",
                    "官网链接": "https://jygl.sxjzit.edu.cn/index/index/employjob.html",
                    "推荐Folo文件夹": "我的学校/校园招聘",
                    "主分类": "我的学校",
                    "推荐原因": "学校就业系统职位页面，适合跟踪岗位、实习、校园招聘",
                    "状态": "builtin_watch",
                    "备注": "公开官网，不需要登录",
                },
                {
                    "源名称": "山西晋中理工学院人力资源通知公告",
                    "官网链接": "https://xtrlzyyfzghc.sxjzit.edu.cn/tongzhigonggao.html",
                    "推荐Folo文件夹": "我的学校/通知公告",
                    "主分类": "我的学校",
                    "推荐原因": "学校人力资源公开通知公告入口",
                    "状态": "builtin_watch",
                    "备注": "公开官网，不需要登录",
                },
            ]
        )
    return rows


def candidate_source_rows() -> list[dict]:
    rows: list[dict] = []
    for path in [
        ROOT / "sources" / "source_watchlist.csv",
        ROOT / "sources" / "candidate_sources.csv",
        ROOT / "sources" / "all_domain_candidate_sources.csv",
        ROOT / "sources" / "source_pool_strategy.csv",
    ]:
        for row in read_csv(path):
            rows.append(row)
    return rows


def row_url(row: dict) -> str:
    for key in ["官网链接", "URL", "RSS链接", "实际抓取URL"]:
        value = compact(row.get(key, ""))
        if is_http_url(value):
            return value
    note = compact(row.get("备注", ""))
    match = re.search(r"实际抓取URL=(https?://[^\s;；]+)", note)
    if match:
        return match.group(1)
    return ""


def match_sources(keyword: str, limit: int = 5) -> list[dict]:
    terms = query_terms(keyword)
    scored: list[tuple[int, dict]] = []
    for row in infer_builtin_sources(keyword) + candidate_source_rows():
        url = row_url(row)
        if not url:
            continue
        text = " ".join(str(value) for value in row.values() if value)
        score, _ = score_text(keyword, terms, text)
        if score > 0 or row.get("状态") == "builtin_watch":
            scored.append((score + (20 if row.get("状态") == "builtin_watch" else 0), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for _, row in scored:
        url = row_url(row)
        key = f"{row.get('源名称')}|{url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def fetch_page(url: str, timeout: int = 10) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "InfoRadar/0.1 public watch checker; no login bypass",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(500000)
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    return raw.decode(encoding, errors="replace")


def parse_items(html: str, source_url: str, keyword: str) -> list[dict]:
    parser = LinkParser()
    parser.feed(html)
    terms = query_terms(keyword)
    items: list[dict] = []
    for link in parser.links:
        title = compact(link.get("title", ""))
        if len(title) < 4 or len(title) > 120:
            continue
        text = f"{title} {link.get('href', '')}"
        score, _ = score_text(keyword, terms, text)
        if score <= 0 and not any(term in title for term in ["通知", "公告", "奖学金", "比赛", "竞赛", "入团", "评优", "招聘", "报名"]):
            continue
        url = urljoin(source_url, link.get("href", ""))
        item_hash = sha(f"{title}|{url}", 20)
        items.append({"title": title, "url": url, "published_at": visible_date_from_title(title), "summary": title, "hash": item_hash})
    if not items:
        page_title = compact(parser.page_title) or source_url
        title = f"{keyword} 监控源快照：{page_title}"
        items.append({"title": title, "url": source_url, "published_at": "", "summary": "当前页面暂无可精确提取的匹配列表项，已保存为观察基线。", "hash": sha(f"{title}|{source_url}", 20)})
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if item["hash"] in seen:
            continue
        seen.add(item["hash"])
        deduped.append(item)
    return deduped[:30]


def snapshot_path(watch_id: str) -> Path:
    return SNAPSHOT_DIR / f"{watch_id}_latest.json"


def load_previous_hashes(watch_id: str) -> set[str]:
    path = snapshot_path(watch_id)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return set()
    return {item.get("hash", "") for item in data.get("items", []) if item.get("hash")}


def write_snapshot(watch_id: str, snapshot: dict) -> None:
    path = snapshot_path(watch_id)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    history_path = HISTORY_DIR / f"{watch_id}_{stamp()}.json"
    history_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def broad_category(keyword: str, source_row: dict) -> str:
    text = f"{keyword} {source_row.get('源名称', '')} {source_row.get('官网链接', '')} {source_row.get('主分类', '')} {source_row.get('推荐Folo文件夹', '')}"
    if any(word in text for word in ["山西晋中理工", "晋中理工", "sxjzit.edu.cn"]):
        return "我的学校"
    if any(word in text for word in ["招聘", "校招", "岗位"]):
        return "就业招聘"
    if any(word in text for word in ["电工证", "证书", "补贴", "报名"]):
        return "职业证书"
    if any(word in text for word in ["政策", "人社", "教育", "工信"]):
        return "政策风向"
    return source_row.get("主分类") or "长期观察"


def update_row(keyword: str, source_row: dict, item: dict, watch_id: str, first_seen: bool) -> dict:
    broad = broad_category(keyword, source_row)
    detected = now_text()
    update_id = "watch_" + sha(f"{watch_id}|{item.get('hash')}|{detected}", 16)
    source_layer = "A_core" if broad in {"我的学校", "就业招聘", "职业证书", "政策风向"} else "B_observe"
    decision_scope = "学校行动" if broad == "我的学校" else ("职业成长" if broad in {"就业招聘", "职业证书"} else "环境判断")
    return {
        "update_id": update_id,
        "watch_id": watch_id,
        "watch_keyword": keyword,
        "source_name": source_row.get("源名称", "未命名观察源"),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at", ""),
        "detected_at": detected,
        "last_seen_at": detected,
        "broad_category": broad,
        "source_layer": source_layer,
        "decision_scope": decision_scope,
        "risk_level": "低",
        "why_relevant": "该观察源与你登记的监控关键词相关，可能影响学校事务、证书、招聘、政策或机会判断。",
        "suggested_action": "打开公开原文核验发布时间、截止时间和适用条件；重要事项加入今日情报或深挖。",
        "status": "initial_detected" if first_seen else "new",
    }


def run_watch(timeout: int = 10) -> dict:
    ensure_dirs()
    requests = read_watch_requests()
    all_updates: list[dict] = []
    errors: list[dict] = []
    checked = 0
    success = 0
    for request in requests:
        keyword = compact(request.get("关键词", ""))
        if not keyword:
            continue
        sources = match_sources(keyword)
        for source in sources:
            source_url = row_url(source)
            watch_id = sha(f"{keyword}|{source.get('源名称')}|{source_url}", 16)
            checked += 1
            try:
                html = fetch_page(source_url, timeout)
                items = parse_items(html, source_url, keyword)
                previous_hashes = load_previous_hashes(watch_id)
                first_seen = not previous_hashes
                new_items = [item for item in items if item.get("hash") not in previous_hashes]
                snapshot = {
                    "watch_id": watch_id,
                    "watch_keyword": keyword,
                    "source_name": source.get("源名称", "未命名观察源"),
                    "source_url": source_url,
                    "fetched_at": now_text(),
                    "items": items,
                }
                write_snapshot(watch_id, snapshot)
                for item in new_items:
                    all_updates.append(update_row(keyword, source, item, watch_id, first_seen))
                success += 1
            except Exception as exc:
                errors.append({"watch_keyword": keyword, "source_name": source.get("源名称", ""), "source_url": source_url, "error": repr(exc), "detected_at": now_text()})
    append_jsonl(ERROR_DIR / f"watch_errors_{today_stamp()}.jsonl", errors)
    append_jsonl(UPDATE_DIR / f"watch_updates_{today_stamp()}.jsonl", all_updates)
    rows = []
    for idx, row in enumerate(all_updates, 1):
        out = {"序号": idx, **row}
        rows.append(out)
    task_stamp = stamp()
    return_xlsx = RETURN_DIR / f"watch_updates_{today_stamp()}.xlsx"
    return_csv = RETURN_DIR / f"watch_updates_{today_stamp()}.csv"
    report = RETURN_DIR / f"watch_report_{task_stamp}.md"
    summary = RETURN_DIR / f"watch_report_{task_stamp}_微信摘要.txt"
    write_csv(return_csv, UPDATE_HEADERS, rows)
    write_xlsx(return_xlsx, UPDATE_HEADERS, rows, "watch_updates")
    report_lines = ["# InfoRadar 监控执行报告", "", f"生成时间：{now_text()}", "", f"- 监控请求：{len(requests)}", f"- 实际检查源：{checked}", f"- 成功：{success}", f"- 失败：{len(errors)}", f"- 发现新增：{len(all_updates)}", "", "## 新增前10条", ""]
    for row in rows[:10]:
        report_lines.append(f"- {row.get('title')} | {row.get('source_name')} | {row.get('url')}")
    report.write_text("\n".join(report_lines), encoding="utf-8")
    summary_lines = ["【InfoRadar 监控执行完成】", "", f"监控请求：{len(requests)} 个", f"实际检查源：{checked} 个", f"成功：{success} 个", f"失败：{len(errors)} 个", f"发现新增：{len(all_updates)} 条", "", "新增前5条："]
    if rows:
        for row in rows[:5]:
            summary_lines.append(f"{row.get('序号')}. {row.get('title')}")
            summary_lines.append(f"   来源：{row.get('source_name')}")
    else:
        summary_lines.append("- 暂无新增")
    summary_lines.extend(["", f"完整报告：{report}"])
    summary.write_text("\n".join(summary_lines), encoding="utf-8")
    result = {
        "success": True,
        "watch_request_count": len(requests),
        "checked_source_count": checked,
        "watch_success_count": success,
        "watch_failed_count": len(errors),
        "watch_update_count": len(all_updates),
        "return_xlsx": str(return_xlsx),
        "return_csv": str(return_csv),
        "report": str(report),
        "return_summary": str(summary),
        "error_log": str(ERROR_DIR / f"watch_errors_{today_stamp()}.jsonl"),
        "output_files": [str(return_xlsx), str(return_csv), str(report), str(summary)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run InfoRadar watch_only monitoring tasks")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()
    result = run_watch(args.timeout)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
