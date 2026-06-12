#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEDUPED_DIR = ROOT / "data" / "deduped"
RETURN_DIR = Path(
    os.environ.get(
        "INFORADAR_RETURN_DIR",
        "/home/mana/inforadar-return/FOLO" if os.name != "nt" else r"G:\E盘\工作项目文件\NAS回传\FOLO",
    )
)

SCHOOL_DOMAINS = {
    "sxjzit.edu.cn",
    "www.sxjzit.edu.cn",
    "jygl.sxjzit.edu.cn",
    "xtrlzyyfzghc.sxjzit.edu.cn",
}

SCHOOL_RELEVANT_TERMS = [
    "山西晋中理工",
    "晋中理工",
    "sxjzit",
    "学校",
    "教务",
    "学工",
    "团委",
    "奖学金",
    "助学金",
    "入团",
    "团员",
    "评优",
    "评先",
    "比赛",
    "竞赛",
    "创新创业",
    "招聘",
    "就业",
    "实习",
    "实践",
    "毕业",
]


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def pick(row: dict, *keys: str) -> str:
    for key in keys:
        value = compact(str(row.get(key, "") or ""))
        if value:
            return value
    return ""


def latest_school_csv() -> Path | None:
    paths = sorted(DEDUPED_DIR.glob("FOLO_我的学校_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_rows(rows: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for row in rows:
        title = pick(row, "标题", "title")
        url = pick(row, "原文URL", "article_url", "official_url", "url")
        source = pick(row, "来源名称", "source", "source_name")
        published_at = pick(row, "published_at", "发布时间")
        detected_at = pick(row, "detected_at", "检测时间")
        school_category = pick(row, "school_category", "学校分类")
        normalized.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "published_at": published_at,
                "detected_at": detected_at,
                "school_category": school_category,
                "raw": row,
            }
        )
    return normalized


def is_http_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def host_of(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except Exception:
        return ""


def is_school_domain(url: str) -> bool:
    host = host_of(url)
    return bool(host) and (host in SCHOOL_DOMAINS or host.endswith(".sxjzit.edu.cn"))


def looks_school_related(row: dict) -> bool:
    hay = f"{row['title']} {row['source']} {row['url']} {row['school_category']}"
    return any(term.lower() in hay.lower() for term in SCHOOL_RELEVANT_TERMS)


def looks_other_school(row: dict) -> bool:
    hay = f"{row['title']} {row['source']} {row['url']}"
    if any(term in hay for term in ["山西晋中理工", "晋中理工", "sxjzit.edu.cn"]):
        return False
    return any(term in hay for term in ["大学", "学院", "学校", "中学", "小学", "高职", "职院"])


def check_url(row: dict, timeout: float = 6.0) -> dict:
    url = row["url"]
    if not is_http_url(url):
        return {"ok": False, "status": "invalid_url", "error": "非 HTTP/HTTPS URL"}
    headers = {
        "User-Agent": "InfoRadarSchoolWatchAudit/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    context = ssl.create_default_context()
    for method in ["HEAD", "GET"]:
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            if method == "GET":
                req.add_header("Range", "bytes=0-2048")
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                status = getattr(resp, "status", 0) or 0
                return {"ok": 200 <= status < 400, "status": str(status), "error": ""}
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405, 429, 500, 501}:
                continue
            return {"ok": 200 <= exc.code < 400, "status": str(exc.code), "error": compact(str(exc.reason))}
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            if method == "HEAD":
                continue
            return {"ok": False, "status": "network_error", "error": compact(str(exc))[:160]}
        except Exception as exc:
            if method == "HEAD":
                continue
            return {"ok": False, "status": "unknown_error", "error": compact(str(exc))[:160]}
    return {"ok": False, "status": "unknown_error", "error": "URL 检查未返回结果"}


def check_urls(rows: list[dict]) -> list[dict]:
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        future_map = {pool.submit(check_url, row): row for row in rows}
        for future in as_completed(future_map):
            row = future_map[future]
            try:
                checked = future.result()
            except Exception as exc:
                checked = {"ok": False, "status": "unknown_error", "error": compact(str(exc))[:160]}
            results.append({**row, **checked})
    return results


def duplicate_titles(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        title = compact(row["title"]).lower()
        if not title:
            continue
        counts[title] = counts.get(title, 0) + 1
    return {title: count for title, count in counts.items() if count > 1}


def write_report(source_path: Path, rows: list[dict], checked_rows: list[dict]) -> Path:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RETURN_DIR / f"school_watch_quality_audit_{today_stamp()}.md"

    total = len(rows)
    url_ok = sum(1 for row in checked_rows if row.get("ok"))
    url_bad = len(checked_rows) - url_ok
    dupes = duplicate_titles(rows)
    school_domain_count = sum(1 for row in rows if is_school_domain(row["url"]))
    other_school_rows = [row for row in rows if looks_other_school(row)]
    published_count = sum(1 for row in rows if row["published_at"])
    detected_count = sum(1 for row in rows if row["detected_at"])
    front30 = rows[:30]
    front30_related = sum(1 for row in front30 if looks_school_related(row))

    bad_samples = [row for row in checked_rows if not row.get("ok")][:12]
    other_school_samples = other_school_rows[:12]
    missing_published_samples = [row for row in rows if not row["published_at"]][:12]

    lines: list[str] = [
        "# 学校观察源质量抽检",
        "",
        f"- 生成时间：{now_text()}",
        f"- 输入文件：`{source_path}`",
        f"- 总条数：{total}",
        f"- URL 可打开数量：{url_ok}",
        f"- URL 异常数量：{url_bad}",
        f"- 标题重复数量：{sum(dupes.values()) - len(dupes) if dupes else 0}",
        f"- 山西晋中理工学院相关域名数量：{school_domain_count}",
        f"- 其他学校疑似误入数量：{len(other_school_rows)}",
        f"- 有发布时间数量：{published_count}",
        f"- 有 detected_at 数量：{detected_count}",
        f"- 前 30 条学校事务相关数量：{front30_related}/{len(front30)}",
        "",
        "## 结论",
        "",
    ]

    if total == 0:
        lines.append("- 红灯：我的学校输出为空，需要先修复 watch_only 生成链路。")
    elif front30_related >= max(1, len(front30) - 3) and detected_count == total:
        lines.append("- 绿灯：学校观察源已经能稳定进入输出，并且前排结果基本贴合学校事务。")
    else:
        lines.append("- 黄灯：学校观察源已进入输出，但仍需要继续治理异常 URL、误入来源或缺失字段。")

    lines.extend(
        [
            "",
            "## URL 异常样例",
            "",
        ]
    )
    if bad_samples:
        for row in bad_samples:
            lines.append(f"- `{row.get('status')}` {row['title']}  ")
            lines.append(f"  URL：{row['url']}  ")
            lines.append(f"  错误：{row.get('error') or '无'}")
    else:
        lines.append("- 暂无 URL 异常样例。")

    lines.extend(["", "## 其他学校疑似误入样例", ""])
    if other_school_samples:
        for row in other_school_samples:
            lines.append(f"- {row['title']}  ")
            lines.append(f"  来源：{row['source']}  ")
            lines.append(f"  URL：{row['url']}")
    else:
        lines.append("- 未发现明显其他学校误入。")

    lines.extend(["", "## 缺发布时间样例", ""])
    if missing_published_samples:
        for row in missing_published_samples:
            lines.append(f"- {row['title']}  ")
            lines.append(f"  detected_at：{row['detected_at'] or '待补'}  ")
            lines.append("  说明：页面未提供可解析发布时间，未用检测时间冒充发布时间。")
    else:
        lines.append("- 当前样例均有发布时间。")

    lines.extend(["", "## 前 30 条抽检", ""])
    for index, row in enumerate(front30, 1):
        mark = "相关" if looks_school_related(row) else "待复核"
        published = row["published_at"] or "无发布时间"
        detected = row["detected_at"] or "无 detected_at"
        lines.append(f"{index}. [{mark}] {row['title']}  ")
        lines.append(f"   分类：{row['school_category'] or '待分类'}；发布时间：{published}；检测时间：{detected}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    source_path = latest_school_csv()
    if not source_path:
        print("status=fail")
        print(f"reason=no_school_csv in {DEDUPED_DIR}")
        return 2
    rows = normalize_rows(read_csv(source_path))
    checked_rows = check_urls(rows)
    report_path = write_report(source_path, rows, checked_rows)
    print("status=success")
    print(f"source={source_path}")
    print(f"report={report_path}")
    print(f"total={len(rows)}")
    print(f"url_ok={sum(1 for row in checked_rows if row.get('ok'))}")
    print(f"url_bad={sum(1 for row in checked_rows if not row.get('ok'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
