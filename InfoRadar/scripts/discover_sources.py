#!/usr/bin/env python3
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
import socket
import os
import sys
import os
import urllib.error
import os
import urllib.parse
import os
import urllib.request
import os
import xml.etree.ElementTree as ET
import os
from html.parser import HTMLParser
from pathlib import Path

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
SEED_FILE = ROOT / "data" / "samples" / "source_seed_urls.csv"
DEFAULT_OUTPUT_CSV = ROOT / "sources" / "candidate_sources.csv"
DEFAULT_OUTPUT_XLSX = ROOT / "sources" / "candidate_sources.xlsx"
DEFAULT_WATCHLIST_CSV = ROOT / "sources" / "source_watchlist.csv"
DEFAULT_WATCHLIST_XLSX = ROOT / "sources" / "source_watchlist.xlsx"


CANDIDATE_HEADERS = [
    "序号",
    "源名称",
    "源类型",
    "RSS链接",
    "官网链接",
    "平台",
    "推荐Folo文件夹",
    "主分类",
    "标签",
    "推荐原因",
    "适合你的原因",
    "是否一手源",
    "是否可被Folo添加",
    "是否需要核验",
    "订阅优先级",
    "风险说明",
    "发现时间",
    "发现任务ID",
    "RSS探测状态",
    "RSS探测方式",
    "HTTP状态",
    "内容类型",
    "状态",
    "备注",
    "源ID",
]

WATCHLIST_HEADERS = [
    "序号",
    "源名称",
    "官网链接",
    "推荐Folo文件夹",
    "主分类",
    "推荐原因",
    "为什么值得监控",
    "是否有RSS",
    "后续处理方式",
    "状态",
    "发现时间",
    "发现任务ID",
    "备注",
]


FEED_CONTENT_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/xml",
    "text/xml",
)


COMMON_FEED_PATHS = (
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/index.xml",
)


QUERY_EXPANSIONS = {
    "电工证": ["电工证", "低压电工", "高压电工", "特种作业", "职业技能", "技能等级", "等级认定", "证书", "技能补贴", "人社"],
    "山西焦煤": ["山西焦煤", "山西", "煤矿", "矿山", "国企", "招聘", "校招", "设备维修"],
    "abb acs800": ["ABB", "ACS800", "ACS880", "变频器", "故障代码", "参数", "电气维修"],
    "acs800": ["ABB", "ACS800", "ACS880", "变频器", "故障代码", "参数", "电气维修"],
    "plc": ["PLC", "西门子", "三菱", "汇川", "自动化", "梯形图"],
    "招聘": ["招聘", "校招", "实习", "岗位", "就业", "山西", "国企"],
    "政策": ["政策", "人社", "教育", "工信", "补贴", "证书", "职业技能"],
}


class FeedLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        rel = data.get("rel", "").lower()
        typ = data.get("type", "").lower()
        href = data.get("href", "").strip()
        title = data.get("title", "").strip()
        if not href:
            return
        if "alternate" in rel and (
            "rss" in typ
            or "atom" in typ
            or "feed" in typ
            or "xml" in typ
            or "json" in typ
        ):
            self.links.append((href, title or typ or "alternate"))


def source_id(row: dict) -> str:
    raw = "|".join([row.get("源名称", ""), row.get("RSS链接", ""), row.get("官网链接", "")]).lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def source_key(row: dict) -> str:
    name = normalize_text(row.get("源名称", ""))
    homepage = normalize_text(row.get("官网链接", ""))
    rss = normalize_text(row.get("RSS链接", ""))
    if homepage:
        return f"{name}|{homepage}"
    if rss:
        return f"{name}|{rss}"
    return name


def read_seed(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def match_keyword(row: dict, keyword: str) -> bool:
    if not keyword:
        return True
    hay = " ".join(str(v) for v in row.values())
    normalized_keyword = keyword.lower().strip()
    terms = QUERY_EXPANSIONS.get(normalized_keyword, [keyword])
    if keyword not in terms:
        terms = [keyword, *terms]
    return any(term.lower() in hay.lower() for term in terms if term)


def normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", text).strip("_") or "全部"


def request_url(url: str, timeout: int) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "InfoRadar/0.2 (+local RSS discovery)",
            "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = int(getattr(resp, "status", 200))
        content_type = resp.headers.get("content-type", "")
        data = resp.read(512 * 1024)
        return status, content_type, data


def looks_like_feed(content_type: str, data: bytes) -> bool:
    lower_type = content_type.lower()
    if any(t in lower_type for t in FEED_CONTENT_TYPES):
        return True
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<?xml") or head.startswith(b"<rss") or head.startswith(b"<feed")


def validate_feed(url: str, timeout: int) -> tuple[bool, str, str]:
    try:
        status, content_type, data = request_url(url, timeout)
    except Exception as exc:
        return False, "", f"请求失败：{type(exc).__name__}"

    if status >= 400:
        return False, str(status), "HTTP状态异常"
    if not looks_like_feed(content_type, data):
        return False, str(status), f"不像订阅源：{content_type or 'unknown'}"

    try:
        root = ET.fromstring(data)
        tag = root.tag.lower()
        if tag.endswith("rss") or tag.endswith("feed"):
            return True, str(status), content_type
        channel = root.find("channel")
        if channel is not None:
            return True, str(status), content_type
        return False, str(status), f"XML根节点不像RSS/Atom：{root.tag}"
    except ET.ParseError:
        # 一些站点的 RSS XML 不够干净，Folo 仍可能能解析；内容类型和头部像 feed 时保守放行。
        return True, str(status), content_type or "XML解析有瑕疵"


def candidate_feed_urls(home_url: str) -> list[tuple[str, str]]:
    parsed = urllib.parse.urlparse(home_url)
    if not parsed.scheme or not parsed.netloc:
        return []

    out: list[tuple[str, str]] = []
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.strip("/")

    if "github.com" in parsed.netloc.lower():
        pieces = [p for p in parsed.path.split("/") if p]
        if len(pieces) >= 2:
            repo = f"{base}/{pieces[0]}/{pieces[1]}"
            out.extend(
                [
                    (f"{repo}/releases.atom", "github releases atom"),
                    (f"{repo}/commits.atom", "github commits atom"),
                ]
            )

    for suffix in COMMON_FEED_PATHS:
        out.append((urllib.parse.urljoin(base, suffix), "常见RSS路径"))
    if path:
        for suffix in COMMON_FEED_PATHS:
            out.append((urllib.parse.urljoin(home_url.rstrip("/") + "/", suffix.lstrip("/")), "当前栏目常见RSS路径"))

    seen = set()
    deduped = []
    for url, method in out:
        if url not in seen:
            seen.add(url)
            deduped.append((url, method))
    return deduped


def discover_from_html(home_url: str, timeout: int) -> list[tuple[str, str, str, str]]:
    status, content_type, data = request_url(home_url, timeout)
    parser = FeedLinkParser()
    encoding = "utf-8"
    match = re.search(r"charset=([^;\s]+)", content_type, re.I)
    if match:
        encoding = match.group(1).strip("\"'")
    html = data.decode(encoding, errors="replace")
    parser.feed(html)
    out = []
    for href, title in parser.links:
        out.append((urllib.parse.urljoin(home_url, href), f"HTML alternate: {title}", str(status), content_type))
    return out


def probe_rss(home_url: str, timeout: int, max_feed_candidates: int = 4) -> dict:
    result = {
        "rss": "",
        "status": "未探测",
        "method": "",
        "http_status": "",
        "content_type": "",
        "note": "",
    }
    if not home_url:
        result["status"] = "无官网链接"
        return result

    try:
        html_candidates = discover_from_html(home_url, timeout)
    except urllib.error.HTTPError as exc:
        result["status"] = "官网请求失败"
        result["http_status"] = str(exc.code)
        result["note"] = f"HTTPError：{exc.code}"
        html_candidates = []
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        result["status"] = "官网请求失败"
        result["note"] = f"网络异常：{type(exc).__name__}"
        html_candidates = []
    except Exception as exc:
        result["status"] = "官网解析失败"
        result["note"] = f"{type(exc).__name__}: {exc}"
        html_candidates = []

    for url, method, http_status, content_type in html_candidates:
        ok, feed_status, feed_type = validate_feed(url, timeout)
        if ok:
            result.update(
                {
                    "rss": url,
                    "status": "已发现RSS",
                    "method": method,
                    "http_status": feed_status or http_status,
                    "content_type": feed_type or content_type,
                }
            )
            return result

    for url, method in candidate_feed_urls(home_url)[: max(0, max_feed_candidates)]:
        ok, feed_status, feed_type = validate_feed(url, timeout)
        if ok:
            result.update(
                {
                    "rss": url,
                    "status": "已发现RSS",
                    "method": method,
                    "http_status": feed_status,
                    "content_type": feed_type,
                }
            )
            return result

    if result["status"] in ("未探测", "官网请求失败", "官网解析失败"):
        if not result["note"]:
            result["note"] = "未在HTML alternate或常见路径中发现可用RSS/Atom"
        if result["status"] == "未探测":
            result["status"] = "未发现RSS"
    return result


def is_watchlist_candidate(row: dict, probe_result: dict, score: int) -> bool:
    if probe_result.get("rss"):
        return False
    if row.get("源类型") == "官网" and (row.get("是否一手源") == "是" or score >= 75):
        return True
    if score >= 80:
        return True
    return False


def infer_addable(row: dict) -> str:
    rss = row.get("RSS链接", "").strip()
    if rss:
        return "是"
    probe_status = row.get("RSS探测状态", "")
    if probe_status == "已发现RSS":
        return "是"
    return "待发现RSS"


def build_candidates(
    seed_rows: list[dict],
    keyword: str,
    task_id: str,
    should_probe: bool,
    timeout: int,
    max_probe_sources: int,
    max_feed_candidates: int,
) -> list[dict]:
    discovered_at = now_text()
    out: list[dict] = []
    probed_sources = 0
    for row in seed_rows:
        if not match_keyword(row, keyword):
            continue
        item = {header: "" for header in CANDIDATE_HEADERS}
        for key, value in row.items():
            if key in item:
                item[key] = value
        authority = int(row.get("来源权威度", "0") or 0) if str(row.get("来源权威度", "")).strip().isdigit() else 75
        if should_probe and not item.get("RSS链接", "").strip() and (max_probe_sources <= 0 or probed_sources < max_probe_sources):
            probed_sources += 1
            probe = probe_rss(item.get("官网链接", "").strip(), timeout, max_feed_candidates)
            if probe["rss"]:
                item["RSS链接"] = probe["rss"]
            item["RSS探测状态"] = probe["status"]
            item["RSS探测方式"] = probe["method"]
            item["HTTP状态"] = probe["http_status"]
            item["内容类型"] = probe["content_type"]
            probe_note = probe["note"]
            if not probe["rss"] and is_watchlist_candidate(row, probe, authority):
                item["RSS探测状态"] = "无RSS但值得监控"
                item["状态"] = "监控候选"
        elif item.get("RSS链接", "").strip():
            item["RSS探测状态"] = "种子表已有RSS"
            item["RSS探测方式"] = "seed"
            probe_note = ""
        else:
            item["RSS探测状态"] = "未探测" if not should_probe else "已跳过探测"
            probe_note = "达到本次探测数量上限，保留为监控候选" if should_probe else ""
            if is_watchlist_candidate(row, {"rss": ""}, authority):
                item["状态"] = "监控候选"

        item["是否可被Folo添加"] = infer_addable(item)
        item["发现时间"] = discovered_at
        item["发现任务ID"] = task_id
        if not item.get("状态"):
            item["状态"] = "候选"
        if item.get("RSS链接"):
            item["备注"] = "可尝试加入Folo"
        else:
            item["备注"] = probe_note or "候选源；RSS链接待自动发现或人工补充"
        item["源ID"] = source_id(item)
        out.append(item)
    for idx, item in enumerate(out, 1):
        item["序号"] = idx
    return out


def merge_existing(path: Path, rows: list[dict]) -> list[dict]:
    existing = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    by_id: dict[str, dict] = {}
    for row in existing:
        if not row.get("源名称"):
            continue
        key = source_key(row)
        by_id[key] = row
    for row in rows:
        key = source_key(row)
        if key in by_id:
            current = by_id[key]
            for field in CANDIDATE_HEADERS:
                new_value = row.get(field, "")
                old_value = current.get(field, "")
                if field in {"序号"}:
                    continue
                if field in {"发现时间", "发现任务ID", "RSS探测状态", "RSS探测方式", "HTTP状态", "内容类型", "状态", "备注", "RSS链接", "是否可被Folo添加"}:
                    if new_value != "":
                        current[field] = new_value
                elif not old_value and new_value:
                    current[field] = new_value
            current["源ID"] = row.get("源ID") or current.get("源ID") or source_id(current)
        else:
            by_id[key] = row
    merged = list(by_id.values())
    for idx, row in enumerate(merged, 1):
        row["序号"] = idx
        for header in CANDIDATE_HEADERS:
            row.setdefault(header, "")
    return merged


def build_watchlist(candidate_rows: list[dict], task_id: str) -> list[dict]:
    discovered_at = now_text()
    watch_rows: list[dict] = []
    seen: set[str] = set()
    for row in candidate_rows:
        if row.get("RSS链接"):
            continue
        if row.get("RSS探测状态") not in {"无RSS但值得监控", "未发现RSS", "官网请求失败", "官网解析失败"}:
            continue
        key = source_key(row)
        if key in seen:
            continue
        seen.add(key)
        watch = {header: "" for header in WATCHLIST_HEADERS}
        watch["源名称"] = row.get("源名称", "")
        watch["官网链接"] = row.get("官网链接", "")
        watch["推荐Folo文件夹"] = row.get("推荐Folo文件夹", "")
        watch["主分类"] = row.get("主分类", "")
        watch["推荐原因"] = row.get("推荐原因", "")
        watch["为什么值得监控"] = row.get("适合你的原因", "") or row.get("备注", "")
        watch["是否有RSS"] = "否"
        watch["后续处理方式"] = "定期人工核验 / RSSHub 路由尝试 / 官网栏目监控"
        watch["状态"] = "监控中"
        watch["发现时间"] = discovered_at
        watch["发现任务ID"] = task_id
        watch["备注"] = row.get("RSS探测状态", "")
        watch_rows.append(watch)
    for idx, row in enumerate(watch_rows, 1):
        row["序号"] = idx
    return watch_rows


def write_watchlist_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WATCHLIST_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATE_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def write_wechat_summary(path: Path, rows: list[dict], keyword: str, xlsx_path: Path) -> None:
    addable = sum(1 for row in rows if row.get("是否可被Folo添加") == "是")
    top = rows[:8]
    lines = [
        "【InfoRadar 候选订阅源】",
        "",
        f"关键词：{keyword or '全部'}",
        f"候选源数量：{len(rows)}",
        f"可尝试加入Folo：{addable}",
        f"候选源表：{xlsx_path}",
        "",
        "前8个候选源：",
    ]
    for row in top:
        lines.append(f"{row['序号']}. {row['源名称']}")
        lines.append(f"   推荐文件夹：{row['推荐Folo文件夹']}")
        lines.append(f"   Folo状态：{row['是否可被Folo添加']} / {row.get('RSS探测状态', '')}")
        if row.get("RSS链接"):
            lines.append(f"   RSS：{row['RSS链接']}")
        lines.append(f"   原因：{row['适合你的原因']}")
    lines.extend(["", "下一步：把可添加的RSS加入Folo；未发现RSS的官网先保留人工核验或后续走RSSHub路线。"])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_watchlist_summary(path: Path, rows: list[dict], xlsx_path: Path) -> None:
    lines = [
        "# InfoRadar 监控候选摘要",
        "",
        f"监控候选数量：{len(rows)}",
        f"表格：{xlsx_path}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"- {row['序号']}. {row['源名称']}",
                f"  - 官网：{row['官网链接']}",
                f"  - 文件夹：{row['推荐Folo文件夹']}",
                f"  - 为什么值得监控：{row['为什么值得监控']}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_to_return(path: Path, dest_name: str | None = None) -> Path:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    dest = RETURN_DIR / (dest_name or path.name)
    dest.write_bytes(path.read_bytes())
    return dest


def log_result(name: str, result: dict) -> None:
    log_path = ROOT / "logs" / name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate RSS/Folo sources from seed table")
    parser.add_argument("--keyword", default="")
    parser.add_argument("--seed", default=str(SEED_FILE))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-xlsx", default=str(DEFAULT_OUTPUT_XLSX))
    parser.add_argument("--watchlist-csv", default=str(DEFAULT_WATCHLIST_CSV))
    parser.add_argument("--watchlist-xlsx", default=str(DEFAULT_WATCHLIST_XLSX))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--probe", action="store_true", help="probe homepage HTML and common RSS/Atom paths")
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--max-probe-sources", type=int, default=8, help="maximum matched sources to probe per run; <=0 means no limit")
    parser.add_argument("--max-feed-candidates", type=int, default=4, help="maximum common feed paths to test per source")
    args = parser.parse_args()

    task_id = args.task_id or f"discover_{stamp()}"
    try:
        seed_rows = read_seed(Path(args.seed))
        candidates = build_candidates(
            seed_rows,
            args.keyword,
            task_id,
            args.probe,
            args.timeout,
            args.max_probe_sources,
            args.max_feed_candidates,
        )
        output_csv = Path(args.output_csv)
        merged = merge_existing(output_csv, candidates)
        output_xlsx = Path(args.output_xlsx)
        watch_rows = build_watchlist(merged, task_id)
        watchlist_csv = Path(args.watchlist_csv)
        watchlist_xlsx = Path(args.watchlist_xlsx)
        write_csv(output_csv, merged)
        write_xlsx(output_xlsx, CANDIDATE_HEADERS, merged, "候选订阅源")
        summary = ROOT / "reports" / "source_discovery" / f"{task_id}_微信摘要.txt"
        write_wechat_summary(summary, candidates, args.keyword, output_xlsx)
        write_watchlist_csv(watchlist_csv, watch_rows)
        write_xlsx(watchlist_xlsx, WATCHLIST_HEADERS, watch_rows, "source_watchlist")
        watch_summary = ROOT / "reports" / "source_discovery" / f"{task_id}_监控候选摘要.md"
        write_watchlist_summary(watch_summary, watch_rows, watchlist_xlsx)

        return_xlsx = copy_to_return(output_xlsx, f"{output_xlsx.stem}_{task_id}{output_xlsx.suffix}")
        return_summary = copy_to_return(summary)
        return_watchlist_xlsx = copy_to_return(watchlist_xlsx, f"{watchlist_xlsx.stem}_{task_id}{watchlist_xlsx.suffix}")
        return_watchlist_summary = copy_to_return(watch_summary, f"{watch_summary.stem}_{task_id}{watch_summary.suffix}")

        result = {
            "success": True,
            "task_id": task_id,
            "keyword": args.keyword,
            "probe": args.probe,
            "new_candidates": len(candidates),
            "total_candidates": len(merged),
            "addable_candidates": sum(1 for row in candidates if row.get("是否可被Folo添加") == "是"),
            "watchlist_candidates": len(watch_rows),
            "csv": str(output_csv),
            "xlsx": str(output_xlsx),
            "watchlist_csv": str(watchlist_csv),
            "watchlist_xlsx": str(watchlist_xlsx),
            "wechat_summary": str(summary),
            "return_xlsx": str(return_xlsx),
            "return_summary": str(return_summary),
            "return_watchlist_xlsx": str(return_watchlist_xlsx),
            "return_watchlist_summary": str(return_watchlist_summary),
        }
        log_result("run.log", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        err = {
            "success": False,
            "task_id": task_id,
            "keyword": args.keyword,
            "error": repr(exc),
        }
        log_result("error.log", err)
        print(json.dumps(err, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
