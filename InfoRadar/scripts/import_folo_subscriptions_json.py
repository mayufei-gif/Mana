#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
ARCHIVE_FOLO_DIR = Path(r"G:\E盘\工作项目文件\NAS回传\InfoRadar_项目文件\07_Folo真实数据与订阅清单")
DEFAULT_SUBSCRIPTIONS = ROOT / "data" / "raw" / "folo_export" / "folo_subscriptions_current.json"
DEFAULT_ERROR_FEEDS = ROOT / "data" / "raw" / "folo_export" / "folo_error_feeds_current.csv"


SOURCE_HEADERS = [
    "序号",
    "源名称",
    "源类型",
    "RSS链接",
    "可抓取RSS链接",
    "官网链接",
    "Folo文件夹路径",
    "Folo订阅源名称",
    "主分类",
    "标签",
    "是否已加入Folo",
    "是否建议保留",
    "订阅优先级",
    "来源权威度",
    "更新频率",
    "最近更新时间",
    "长期价值评分",
    "是否失效",
    "失效原因",
    "错误类型",
    "Folo源ID",
    "Folo订阅ID",
    "Folo视图",
    "加入时间",
    "最后检查时间",
    "备注",
]


LIST_HEADERS = [
    "序号",
    "List名称",
    "ListID",
    "Feed数量",
    "Folo视图",
    "是否私有",
    "所有者",
    "描述",
    "创建时间",
    "更新时间",
    "处理建议",
    "备注",
]


ERROR_HEADERS = [
    "序号",
    "源名称",
    "源ID",
    "Folo文件夹路径",
    "RSS链接",
    "官网链接",
    "错误时间",
    "错误类型",
    "错误原因",
    "处理建议",
    "是否建议删除",
]


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def normalize_url(value: str) -> str:
    return (value or "").strip()


def rsshub_base_url() -> str:
    return os.environ.get("RSSHUB_BASE_URL", "https://rsshub.app").rstrip("/")


def to_fetchable_url(url: str) -> str:
    raw = normalize_url(url)
    if raw.startswith("rsshub://"):
        return f"{rsshub_base_url()}/{raw[len('rsshub://'):]}"
    return raw


def source_key(*parts: str) -> str:
    raw = "|".join(p.strip().lower() for p in parts if p and p.strip())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def category_tags(category: str, title: str, description: str) -> tuple[str, str, int]:
    hay = f"{category} {title} {description}".lower()
    hay_without_boilerplate = hay.replace("powered by rsshub", "")
    if any(k in hay for k in ["图片私密", "小姐姐", "擦边"]):
        return "低价值/私密", "低价值、过滤候选", 5
    if any(k in hay for k in ["新闻", "时政", "央视", "cctv", "观察者", "新华社"]):
        return "新闻时政", "时政、新闻、长期观察", 58
    if any(k in hay for k in ["热榜", "社媒", "微博", "知乎"]):
        return "社媒热榜", "热榜、舆情、信息差", 48
    if any(k in hay for k in ["财经", "商业", "金融", "华尔街"]):
        return "财经商业", "财经、商业、机会观察", 63
    if any(k in hay for k in ["影音", "娱乐", "音乐", "电影"]):
        return "影音娱乐", "娱乐、低优先级", 24
    if any(k in hay for k in ["学习", "教育", "课程", "教程", "知识"]):
        return "技术学习", "学习、教育、知识", 70
    if re.search(r"(^|[^a-z])ai([^a-z]|$)", hay_without_boilerplate) or any(
        k in hay_without_boilerplate for k in ["openai", "chatgpt", "codex", "github", "开源", "科技", "编程"]
    ):
        return "AI工具", "AI科技、开源、工具", 78
    return category or "待分类", category or "待分类", 50


def authority_score(title: str, url: str, site_url: str, category: str) -> int:
    hay = f"{title} {url} {site_url} {category}".lower()
    if any(k in hay for k in ["gov.cn", "edu.cn", "央视", "cctv", "新华社", "人民网"]):
        return 90
    if any(k in hay for k in ["github", "openai", "rsshub", "hellogithub"]):
        return 78
    if any(k in hay for k in ["bilibili", "youtube", "x.com", "twitter", "telegram"]):
        return 55
    if "rsshub://" in hay:
        return 62
    return 65


def priority(score: int, invalid: bool, category: str) -> str:
    if invalid:
        return "待修复"
    if category in ("低价值/私密", "影音娱乐"):
        return "低"
    if score >= 75:
        return "高"
    if score >= 55:
        return "中"
    return "低"


def error_type(message: str, url: str = "") -> tuple[str, str, str]:
    msg = (message or "").lower()
    target = f"{msg} {url.lower()}"
    if not message:
        return "", "", "保留"
    if "playwright version mismatch" in target or "patchright" in target:
        return "RSSHub渲染服务异常", "优先保留；尝试备用 RSSHub 实例或等待渲染服务版本同步。", "否"
    if "username_invalid" in target or "404 not found" in target:
        return "源地址失效", "核验原平台地址；若长期不可访问再删除或替换。", "观察"
    if "fetch failed" in target or "failed to fetch" in target or "<no response>" in target:
        return "网络/上游抓取失败", "先观察；可换 RSSHub 实例、换官方 RSS 或降级为监控源。", "否"
    if "400" in target or "unable to fetch" in target:
        return "平台接口限制", "核验是否需要登录、是否禁用预览；必要时替换来源。", "观察"
    return "未知错误", "保留错误样本，后续按同类错误聚合处理。", "否"


def error_indexes(rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_url: dict[str, dict] = {}
    for row in rows:
        fid = (row.get("id") or "").strip()
        url = normalize_url(row.get("url", ""))
        if fid:
            by_id[fid] = row
        if url:
            by_url[url] = row
    return by_id, by_url


def load_subscriptions(path: Path) -> list[dict]:
    data = read_json(path)
    root = data.get("data", data)
    return root.get("subscriptions", []) if isinstance(root, dict) else []


def build_feed_rows(subscriptions: list[dict], errors: list[dict]) -> tuple[list[dict], list[dict], dict]:
    by_error_id, by_error_url = error_indexes(errors)
    now = now_text()
    feed_rows: list[dict] = []
    list_rows: list[dict] = []
    stats = Counter()

    for sub in subscriptions:
        feed = sub.get("feeds") if isinstance(sub.get("feeds"), dict) else None
        list_obj = sub.get("lists") if isinstance(sub.get("lists"), dict) else None
        if list_obj:
            owner = list_obj.get("owner") if isinstance(list_obj.get("owner"), dict) else {}
            list_rows.append(
                {
                    "List名称": list_obj.get("title") or sub.get("title") or "",
                    "ListID": list_obj.get("id") or sub.get("listId") or sub.get("feedId") or "",
                    "Feed数量": len(list_obj.get("feedIds") or []),
                    "Folo视图": sub.get("view", ""),
                    "是否私有": sub.get("isPrivate", ""),
                    "所有者": owner.get("name", ""),
                    "描述": list_obj.get("description") or "",
                    "创建时间": sub.get("createdAt") or "",
                    "更新时间": list_obj.get("updatedAt") or "",
                    "处理建议": "作为 Folo 合集保留；后续单独展开 feedIds 做内容追踪。",
                    "备注": "",
                }
            )
            stats["list_count"] += 1
            continue

        if not feed:
            stats["unknown_count"] += 1
            continue

        fid = str(feed.get("id") or sub.get("feedId") or "")
        title = feed.get("title") or sub.get("title") or ""
        url = normalize_url(feed.get("url") or "")
        site_url = normalize_url(feed.get("siteUrl") or "")
        category = sub.get("category") or ""
        description = feed.get("description") or ""
        error_row = by_error_id.get(fid) or by_error_url.get(url) or {}
        error_message = feed.get("errorMessage") or error_row.get("errorMessage") or ""
        err_type, suggestion, delete_label = error_type(error_message, url)
        invalid = bool(error_message or feed.get("errorAt") or error_row.get("errorAt"))
        main_category, tags, base_score = category_tags(category, title, description)
        authority = authority_score(title, url, site_url, category)
        if url.startswith("rsshub://"):
            stats["rsshub_count"] += 1
        else:
            stats["http_feed_count"] += 1
        if invalid:
            stats["error_feed_count"] += 1
        long_score = max(5, min(100, int(base_score * 0.65 + authority * 0.35 - (18 if invalid else 0))))
        keep = "否" if main_category == "低价值/私密" else "是"
        if invalid and delete_label == "观察":
            keep = "观察"

        feed_rows.append(
            {
                "源名称": title,
                "源类型": "Folo feed",
                "RSS链接": url,
                "可抓取RSS链接": to_fetchable_url(url),
                "官网链接": site_url,
                "Folo文件夹路径": category or "待定位",
                "Folo订阅源名称": title,
                "主分类": main_category,
                "标签": tags,
                "是否已加入Folo": "是",
                "是否建议保留": keep,
                "订阅优先级": priority(long_score, invalid, main_category),
                "来源权威度": authority,
                "更新频率": "待观察",
                "最近更新时间": "",
                "长期价值评分": long_score,
                "是否失效": "是" if invalid else "否",
                "失效原因": error_message,
                "错误类型": err_type,
                "Folo源ID": fid,
                "Folo订阅ID": sub.get("feedId") or "",
                "Folo视图": sub.get("view", ""),
                "加入时间": sub.get("createdAt") or "",
                "最后检查时间": now,
                "备注": suggestion if invalid else description,
            }
        )
        stats["feed_count"] += 1

    feed_rows.sort(key=lambda r: (r["是否失效"] == "是", {"高": 0, "中": 1, "低": 2, "待修复": 3}.get(r["订阅优先级"], 9), -int(r["长期价值评分"])))
    for idx, row in enumerate(feed_rows, 1):
        row["序号"] = idx
    for idx, row in enumerate(list_rows, 1):
        row["序号"] = idx
    return feed_rows, list_rows, dict(stats)


def build_error_report(errors: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for row in errors:
        typ, suggestion, delete_label = error_type(row.get("errorMessage", ""), row.get("url", ""))
        rows.append(
            {
                "源名称": row.get("title", ""),
                "源ID": row.get("id", ""),
                "Folo文件夹路径": row.get("category", ""),
                "RSS链接": row.get("url", ""),
                "官网链接": row.get("siteUrl", ""),
                "错误时间": row.get("errorAt", ""),
                "错误类型": typ,
                "错误原因": row.get("errorMessage", ""),
                "处理建议": suggestion,
                "是否建议删除": delete_label,
            }
        )
    rows.sort(key=lambda r: (r["是否建议删除"], r["错误类型"], r["Folo文件夹路径"], r["源名称"]))
    for idx, row in enumerate(rows, 1):
        row["序号"] = idx
    return rows


def copy_to_return(path: Path, name: str | None = None) -> Path:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    dest = RETURN_DIR / (name or path.name)
    dest.write_bytes(path.read_bytes())
    return dest


def write_summary(path: Path, result: dict, categories: Counter) -> None:
    lines = [
        "【InfoRadar Folo真实订阅导入】",
        "",
        f"任务ID：{result['task_id']}",
        f"Feed：{result['feed_count']}",
        f"List：{result['list_count']}",
        f"RSSHub源：{result['rsshub_count']}",
        f"普通HTTP源：{result['http_feed_count']}",
        f"错误/红源：{result['error_feed_count']}",
        "",
        "主要分类：",
    ]
    for name, count in categories.most_common(8):
        lines.append(f"- {name or '未分类'}：{count}")
    lines.extend(
        [
            "",
            "输出文件：",
            f"- {result['return_xlsx']}",
            f"- {result['return_lists_xlsx']}",
            f"- {result['return_error_report_xlsx']}",
            "",
            "下一步：抓取真实RSS更新 / 生成真实Folo表格",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import real Folo subscription JSON into InfoRadar source pool")
    parser.add_argument("--subscriptions", default="")
    parser.add_argument("--error-feeds", default="")
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()

    task_id = args.task_id or f"folo_subscriptions_{stamp()}"
    subscriptions_path = Path(args.subscriptions) if args.subscriptions else first_existing(
        DEFAULT_SUBSCRIPTIONS,
        ARCHIVE_FOLO_DIR / "folo_subscriptions_current.json",
    )
    error_path = Path(args.error_feeds) if args.error_feeds else first_existing(
        DEFAULT_ERROR_FEEDS,
        ARCHIVE_FOLO_DIR / "folo_error_feeds_current.csv",
    )

    subscriptions = load_subscriptions(subscriptions_path)
    errors = read_csv(error_path)
    feed_rows, list_rows, stats = build_feed_rows(subscriptions, errors)
    error_rows = build_error_report(errors)
    categories = Counter(row.get("Folo文件夹路径", "") for row in feed_rows)

    sources_dir = ROOT / "sources"
    output_csv = sources_dir / "source_pool_from_folo.csv"
    output_xlsx = sources_dir / "source_pool_from_folo.xlsx"
    lists_csv = sources_dir / "folo_lists_from_json.csv"
    lists_xlsx = sources_dir / "folo_lists_from_json.xlsx"
    error_csv = sources_dir / "folo_error_feeds_report.csv"
    error_xlsx = sources_dir / "folo_error_feeds_report.xlsx"

    write_csv(output_csv, SOURCE_HEADERS, feed_rows)
    write_xlsx(output_xlsx, SOURCE_HEADERS, feed_rows, "source_pool_from_folo")
    write_csv(lists_csv, LIST_HEADERS, list_rows)
    write_xlsx(lists_xlsx, LIST_HEADERS, list_rows, "folo_lists")
    write_csv(error_csv, ERROR_HEADERS, error_rows)
    write_xlsx(error_xlsx, ERROR_HEADERS, error_rows, "folo_error_feeds")

    return_csv = copy_to_return(output_csv, f"source_pool_from_folo_{task_id}.csv")
    return_xlsx = copy_to_return(output_xlsx, f"source_pool_from_folo_{task_id}.xlsx")
    return_lists_xlsx = copy_to_return(lists_xlsx, f"folo_lists_from_json_{task_id}.xlsx")
    return_error_report_xlsx = copy_to_return(error_xlsx, f"folo_error_feeds_report_{task_id}.xlsx")

    result = {
        "success": True,
        "task_id": task_id,
        "subscriptions_input": str(subscriptions_path),
        "error_feeds_input": str(error_path),
        "feed_count": stats.get("feed_count", 0),
        "list_count": stats.get("list_count", 0),
        "rsshub_count": stats.get("rsshub_count", 0),
        "http_feed_count": stats.get("http_feed_count", 0),
        "error_feed_count": stats.get("error_feed_count", 0),
        "unknown_count": stats.get("unknown_count", 0),
        "csv": str(output_csv),
        "xlsx": str(output_xlsx),
        "lists_csv": str(lists_csv),
        "lists_xlsx": str(lists_xlsx),
        "error_report_csv": str(error_csv),
        "error_report_xlsx": str(error_xlsx),
        "return_csv": str(return_csv),
        "return_xlsx": str(return_xlsx),
        "return_lists_xlsx": str(return_lists_xlsx),
        "return_error_report_xlsx": str(return_error_report_xlsx),
    }
    summary = RETURN_DIR / f"import_folo_subscriptions_{task_id}_微信摘要.txt"
    result["return_summary"] = str(summary)
    result["output_files"] = [
        str(return_xlsx),
        str(return_lists_xlsx),
        str(return_error_report_xlsx),
        str(return_csv),
        str(summary),
    ]
    write_summary(summary, result, categories)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
