#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import datetime as dt
import os
import json
import os
import re
import os
import socket
import os
import urllib.error
import os
import urllib.request
import os
import xml.etree.ElementTree as ET
import os
from pathlib import Path
from urllib.parse import urlsplit

import rsshub_tools
import os
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
INPUT_CSV = ROOT / "sources" / "all_domain_candidate_sources.csv"
LOG_DIR = ROOT / "logs"

IMPORT_READY_XLSX = RETURN_DIR / "all_domain_folo_import_ready.xlsx"
IMPORT_READY_OPML = RETURN_DIR / "all_domain_folo_import_ready.opml"
MANUAL_REVIEW_XLSX = RETURN_DIR / "all_domain_manual_review.xlsx"
MANUAL_FORWARD_XLSX = RETURN_DIR / "all_domain_manual_forward_sources.xlsx"
DISABLED_XLSX = RETURN_DIR / "all_domain_disabled_sources.xlsx"
SUMMARY_TXT = RETURN_DIR / "all_domain_source_verification_微信摘要.txt"

OUTPUT_HEADERS = [
    "序号",
    "源名称",
    "平台",
    "源URL",
    "RSS链接",
    "source_layer",
    "broad_category",
    "decision_scope",
    "acquisition_mode",
    "push_frequency",
    "risk_policy",
    "paywall_policy",
    "推荐Folo文件夹",
    "source_status",
    "是否可导入Folo",
    "是否需要人工核验",
    "是否需要手动转发",
    "是否禁用",
    "推荐原因",
    "风险说明",
    "建议处理方式",
    "备注",
]

MANUAL_FORWARD_PLATFORMS = {
    "微信公众号",
    "视频号",
    "抖音",
    "快手",
    "小红书",
    "闲鱼",
    "淘宝",
    "拼多多",
    "京东",
    "付费知识",
}

MANUAL_FORWARD_MODES = {
    "manual_forward",
    "manual_import",
    "price_watch",
    "paid_metadata_only",
    "metadata_only",
}

WATCH_ONLY_MODES = {"official_page", "search_watch"}

DISABLED_TERMS = [
    "破解版",
    "学习版",
    "注册机",
    "免激活",
    "盗版",
    "灰产",
    "黑产",
    "刷单",
    "薅羊毛脚本",
    "绕过登录",
    "绕过付费",
    "绕过验证码",
    "绕过反爬",
    "cookie",
    "token",
    "付费墙绕过",
]

FOLDER_MAP = {
    "我的学校": "我的学校/官网通知",
    "学校通知": "我的学校/官网通知",
    "教务学业": "我的学校/教务学工",
    "学工团委": "我的学校/教务学工",
    "奖助评优": "我的学校/团委评优",
    "入团竞选": "我的学校/团委评优",
    "创新创业竞赛": "我的学校/比赛竞赛",
    "校园招聘实习": "我的学校/校园招聘",
    "毕业档案": "我的学校/教务学工",
    "就业招聘": "就业与证书/招聘就业",
    "职业证书": "就业与证书/职业证书",
    "考试升学": "就业与证书/职业证书",
    "政策风向": "时事与政策/政策风向",
    "本地山西": "时事与政策/本地山西",
    "时事政治": "时事与政策/时事政治",
    "热点新闻": "时事与政策/时事政治",
    "国际观察": "时事与政策/国际观察",
    "法律权益": "就业与证书/劳动权益",
    "工业技术": "专业成长/电气维修",
    "电气自动化": "专业成长/电气维修",
    "PLC变频器": "专业成长/PLC",
    "工业机器人": "专业成长/工业机器人",
    "CAD_EPLAN": "专业成长/AutoCAD_EPLAN",
    "AI工具": "AI与科技/AI工具",
    "科技新闻": "AI与科技/科技新闻",
    "开源仓库": "AI与科技/开源仓库",
    "编程开发": "AI与科技/自动化工具",
    "网络安全": "AI与科技/网络安全",
    "NAS自动化": "AI与科技/自动化工具",
    "3D打印硬件": "机会与风险/低成本实践",
    "学习资源": "资源与消费/学习资源",
    "语言学习": "资源与消费/学习资源",
    "论文文档": "资源与消费/学习资源",
    "财经商业": "时事与政策/政策风向",
    "投资理财": "时事与政策/政策风向",
    "消费购物": "资源与消费/购物资源",
    "数码装备": "资源与消费/购物资源",
    "工具软件": "资源与消费/工具软件",
    "付费知识": "资源与消费/付费知识",
    "课程资源": "资源与消费/付费知识",
    "内容平台": "AI与科技/科技新闻",
    "微信公众号": "资源与消费/学习资源",
    "视频号": "资源与消费/学习资源",
    "抖音快手": "资源与消费/学习资源",
    "B站YouTube": "资源与消费/学习资源",
    "知乎小红书微博": "资源与消费/学习资源",
    "个人项目": "机会与风险/项目机会",
    "机会观察": "机会与风险/项目机会",
    "副业观察": "机会与风险/项目机会",
    "创业扶持": "机会与风险/项目机会",
    "健康医学": "资源与消费/学习资源",
    "心理成长": "资源与消费/学习资源",
    "生活服务": "机会与风险/风险避坑",
    "交通出行": "机会与风险/风险避坑",
    "住房租房": "机会与风险/风险避坑",
    "文化历史": "资源与消费/学习资源",
    "读书影视": "资源与消费/学习资源",
    "游戏娱乐": "资源与消费/学习资源",
    "体育赛事": "资源与消费/学习资源",
    "风险避坑": "机会与风险/风险避坑",
    "诈骗灰产": "机会与风险/风险避坑",
    "虚假招聘": "机会与风险/风险避坑",
    "培训贷": "机会与风险/风险避坑",
    "账号隐私": "机会与风险/风险避坑",
    "盗版破解风险": "机会与风险/风险避坑",
}


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit((value or "").strip())
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def norm(value: object) -> str:
    return str(value or "").strip()


def contains_disabled_terms(text: str) -> bool:
    lower = (text or "").lower()
    return any(term.lower() in lower for term in DISABLED_TERMS)


def probe_rss(url: str, timeout: int = 5, max_bytes: int = 65536) -> tuple[bool, str]:
    if not is_http_url(url):
        return False, "URL不是HTTP/HTTPS"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "InfoRadarSourceVerifier/0.1",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            data = resp.read(max_bytes)
            head = data[:2048].decode("utf-8", errors="ignore").lower()
            if status and int(status) >= 400:
                return False, f"HTTP {status}"
            if any(mark in head for mark in ("<rss", "<feed", "<rdf")):
                return True, f"RSS可访问，HTTP {status}"
            return False, f"HTTP {status} 但不像 RSS/Atom"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return False, f"网络错误：{repr(exc)[:160]}"
    except Exception as exc:
        return False, f"探测失败：{repr(exc)[:160]}"


def recommend_folo_folder(row: dict) -> str:
    category = norm(row.get("broad_category"))
    if category in FOLDER_MAP:
        return FOLDER_MAP[category]
    scope = norm(row.get("decision_scope"))
    if scope == "学校行动":
        return "我的学校/官网通知"
    if scope == "职业成长":
        return "就业与证书/招聘就业"
    if scope == "工具/技术选择":
        return "AI与科技/AI工具"
    if scope == "购买/学习决策":
        return "资源与消费/学习资源"
    if scope == "风险规避":
        return "机会与风险/风险避坑"
    return "时事与政策/政策风向"


def source_url(row: dict) -> str:
    return norm(row.get("候选URL") or row.get("源URL") or row.get("官网链接"))


def rss_url(row: dict) -> str:
    return norm(row.get("RSS候选") or row.get("RSS链接") or row.get("可抓取RSS链接"))


def platform(row: dict) -> str:
    return norm(row.get("平台") or row.get("platform"))


def source_text(row: dict) -> str:
    return " ".join(
        norm(row.get(key))
        for key in [
            "源名称",
            "候选URL",
            "RSS候选",
            "平台",
            "source_layer",
            "acquisition_mode",
            "broad_category",
            "risk_policy",
            "paywall_policy",
            "建议动作",
            "备注",
        ]
    )


def resolve_rss_candidate(row: dict) -> tuple[str, str]:
    raw = rss_url(row)
    if not raw:
        return "", ""
    if raw.startswith("rsshub://"):
        return rsshub_tools.resolve_rsshub_url(raw), "RSSHub路由已转换"
    return raw, "使用原始RSS候选"


def decide_source(row: dict) -> tuple[str, str, str, str]:
    text = source_text(row)
    mode = norm(row.get("acquisition_mode"))
    cat = norm(row.get("broad_category"))
    plat = platform(row)
    paywall = norm(row.get("paywall_policy"))
    raw_rss = rss_url(row)
    resolved_rss, rss_note = resolve_rss_candidate(row)

    if contains_disabled_terms(text):
        return (
            "disabled",
            "命中破解/灰产/绕过限制等风险词，不进入 Folo 导入清单。",
            "涉及盗版、灰产、绕过登录/付费/验证码/反爬等高风险边界。",
            "禁用；如确需保留，只能作为风险避坑案例手动记录。",
        )

    if paywall in {"forbidden_bypass"}:
        return (
            "disabled",
            "候选源标记为禁止绕过付费墙或访问控制。",
            "不得绕过付费墙、DRM、验证码、登录或平台访问控制。",
            "禁用或仅保留公开元信息。",
        )

    if source_url(row).startswith("manual://") or plat in MANUAL_FORWARD_PLATFORMS or mode in MANUAL_FORWARD_MODES:
        return (
            "manual_forward",
            "属于封闭平台、购物平台、付费知识或手动线索池，适合由你转发/手动导入。",
            "只处理公开标题、链接、价格、目录、摘要或你主动转发的内容；不自动硬抓平台数据。",
            "放入手动转发清单；后续可由微信转发文章/链接/截图触发归档。",
        )

    if not raw_rss:
        if mode in WATCH_ONLY_MODES or "官网" in plat or "政府" in plat or "学校" in plat or "企业" in plat:
            return (
                "watch_only",
                "一手官网/机构入口价值高，但当前没有可导入 RSS。",
                "官网页面只做人工核验或后续公开监控，不绕过访问限制。",
                "保留为观察源；需要人工找 RSS、公告栏目或后续做官网监控。",
            )
        return (
            "manual_review",
            "来源可能有价值，但没有明确 RSS 候选。",
            "无法确认能否稳定订阅。",
            "人工核验来源质量和可订阅地址，再决定是否加入 Folo。",
        )

    if resolved_rss and resolved_rss != raw_rss:
        ok, detail = probe_rss(resolved_rss)
    else:
        ok, detail = probe_rss(raw_rss)

    if ok:
        return (
            "import_ready",
            f"RSS/Atom 当前可访问；{rss_note or detail}。",
            "仅使用公开 RSS/Atom，不涉及登录、Cookie、付费墙或验证码。",
            "可导入 Folo；导入后再观察 3-7 天更新质量。",
        )

    if raw_rss.startswith("rsshub://"):
        return (
            "manual_review",
            f"RSSHub 路由存在但本轮未稳定通过：{detail}",
            "不强抓失败路由；需要核验 RSSHub 实例或换公开源。",
            "人工核验 RSSHub 路由、备用实例或自建 RSSHub 后再导入。",
        )

    if cat in {"开源仓库"} and "{owner}" in raw_rss:
        return (
            "manual_review",
            "这是 GitHub Releases Atom 模板，不是具体仓库订阅源。",
            "模板不能直接导入 Folo。",
            "替换 owner/repo 为真实仓库后再导入。",
        )

    return (
        "manual_review",
        f"有 RSS 候选但本轮探测未通过：{detail}",
        "不绕过 403、登录、验证码、付费墙或平台反爬。",
        "人工复核 RSS 是否失效；必要时改用官网、RSSHub 或替代源。",
    )


def output_row(idx: int, row: dict) -> dict:
    status, reason, risk, action = decide_source(row)
    src_url = source_url(row)
    raw_rss = rss_url(row)
    resolved_rss, _ = resolve_rss_candidate(row)
    import_rss = resolved_rss if status == "import_ready" else raw_rss
    out = {
        "序号": idx,
        "源名称": norm(row.get("源名称")),
        "平台": platform(row),
        "源URL": src_url,
        "RSS链接": import_rss,
        "source_layer": norm(row.get("source_layer")),
        "broad_category": norm(row.get("broad_category")),
        "decision_scope": norm(row.get("decision_scope")),
        "acquisition_mode": norm(row.get("acquisition_mode")),
        "push_frequency": norm(row.get("push_frequency")),
        "risk_policy": norm(row.get("risk_policy")),
        "paywall_policy": norm(row.get("paywall_policy")),
        "推荐Folo文件夹": recommend_folo_folder(row),
        "source_status": status,
        "是否可导入Folo": "是" if status == "import_ready" else "否",
        "是否需要人工核验": "是" if status in {"manual_review", "watch_only"} else "否",
        "是否需要手动转发": "是" if status == "manual_forward" else "否",
        "是否禁用": "是" if status == "disabled" else "否",
        "推荐原因": reason,
        "风险说明": risk,
        "建议处理方式": action,
        "备注": norm(row.get("备注") or row.get("建议动作")),
    }
    return out


def split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = {
        "import_ready": [],
        "manual_review": [],
        "manual_forward": [],
        "watch_only": [],
        "disabled": [],
    }
    for row in rows:
        grouped.setdefault(row.get("source_status", "manual_review"), []).append(row)
    return grouped


def write_opml(path: Path, rows: list[dict]) -> None:
    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "InfoRadar 全域可导入 Folo 源"
    ET.SubElement(head, "dateCreated").text = now_text()
    body = ET.SubElement(opml, "body")
    folders: dict[str, ET.Element] = {}

    for row in rows:
        folder_path = row.get("推荐Folo文件夹") or "InfoRadar/未分类"
        parent = body
        current = ""
        for part in [item for item in folder_path.split("/") if item.strip()]:
            current = f"{current}/{part}" if current else part
            if current not in folders:
                folders[current] = ET.SubElement(parent, "outline", {"text": part, "title": part})
            parent = folders[current]
        attrs = {
            "type": "rss",
            "text": row.get("源名称", ""),
            "title": row.get("源名称", ""),
            "xmlUrl": row.get("RSS链接", ""),
        }
        if row.get("源URL"):
            attrs["htmlUrl"] = row.get("源URL", "")
        ET.SubElement(parent, "outline", attrs)

    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(opml).write(path, encoding="utf-8", xml_declaration=True)


def status_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        status = row.get("source_status") or "未标记"
        out[status] = out.get(status, 0) + 1
    return out


def write_report(path: Path, rows: list[dict], grouped: dict[str, list[dict]]) -> None:
    counts = status_counts(rows)
    by_folder: dict[str, int] = {}
    for row in rows:
        folder = row.get("推荐Folo文件夹") or "未分类"
        by_folder[folder] = by_folder.get(folder, 0) + 1

    lines = [
        "# InfoRadar MVP-2.6 全域候选源核验报告",
        "",
        f"生成时间：{now_text()}",
        "",
        "## 总览",
        "",
        f"- 输入候选源：{len(rows)}",
        f"- 可导入 Folo：{counts.get('import_ready', 0)}",
        f"- 需要人工核验：{counts.get('manual_review', 0)}",
        f"- 只适合手动转发/手动导入：{counts.get('manual_forward', 0)}",
        f"- 观察源：{counts.get('watch_only', 0)}",
        f"- 禁用/风险源：{counts.get('disabled', 0)}",
        "",
        "## 输出文件",
        "",
        f"- Folo 可导入清单：{IMPORT_READY_XLSX}",
        f"- Folo OPML：{IMPORT_READY_OPML}",
        f"- 人工核验清单：{MANUAL_REVIEW_XLSX}",
        f"- 手动转发清单：{MANUAL_FORWARD_XLSX}",
        f"- 禁用/风险清单：{DISABLED_XLSX}",
        "",
        "## 推荐 Folo 文件夹分布",
        "",
    ]
    for folder, count in sorted(by_folder.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {folder}：{count}")

    lines.extend(
        [
            "",
            "## 可导入 Folo 的前20个源",
            "",
        ]
    )
    for row in grouped.get("import_ready", [])[:20]:
        lines.append(f"- {row.get('源名称')} -> {row.get('推荐Folo文件夹')} -> {row.get('RSS链接')}")
    if not grouped.get("import_ready"):
        lines.append("- 本轮没有自动判定为可直接导入的源，需要先人工核验 RSS。")

    lines.extend(
        [
            "",
            "## 需要人工处理的重点",
            "",
            "- `manual_review`：有价值但 RSS 不确定，适合人工打开核验。",
            "- `watch_only`：政府、学校、企业等官网入口，当前无 RSS，不自动硬抓。",
            "- `manual_forward`：公众号、抖音、小红书、购物、付费知识等封闭/半封闭平台，只接收用户主动转发或公开元信息。",
            "- `disabled`：破解、灰产、绕过登录/付费/验证码/反爬等高风险源，不进入 OPML。",
            "",
            "## 边界规则",
            "",
            "- 不读取或使用 Folo token、Cookie、账号凭证。",
            "- 不绕过登录、验证码、付费墙、DRM、访问控制或平台反爬。",
            "- OPML 只包含 `source_status=import_ready` 的公开 RSS/Atom 源。",
            "- 候选源不等于正式源；导入 Folo 后还需要观察更新质量。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_wechat_summary(path: Path, rows: list[dict], report_path: Path) -> None:
    counts = status_counts(rows)
    lines = [
        "【InfoRadar 全域源核验】",
        "",
        f"候选源：{len(rows)}",
        f"可导入Folo：{counts.get('import_ready', 0)}",
        f"人工核验：{counts.get('manual_review', 0)}",
        f"手动转发：{counts.get('manual_forward', 0)}",
        f"观察源：{counts.get('watch_only', 0)}",
        f"禁用/风险：{counts.get('disabled', 0)}",
        "",
        "已生成：",
        f"- {IMPORT_READY_XLSX}",
        f"- {IMPORT_READY_OPML}",
        f"- {MANUAL_REVIEW_XLSX}",
        f"- {MANUAL_FORWARD_XLSX}",
        f"- {DISABLED_XLSX}",
        f"- {report_path}",
        "",
        "下一步：把 OPML 导入 Folo 后，再跑 全域情报 做质量验收。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"缺少候选源文件：{INPUT_CSV}")

    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    raw_rows = read_csv(INPUT_CSV)
    rows = [output_row(idx, row) for idx, row in enumerate(raw_rows, 1)]
    grouped = split_rows(rows)

    import_ready = grouped.get("import_ready", [])
    manual_review = grouped.get("manual_review", []) + grouped.get("watch_only", [])
    manual_forward = grouped.get("manual_forward", [])
    disabled = grouped.get("disabled", [])

    write_xlsx(IMPORT_READY_XLSX, OUTPUT_HEADERS, import_ready, sheet_name="Folo导入")
    write_xlsx(MANUAL_REVIEW_XLSX, OUTPUT_HEADERS, manual_review, sheet_name="人工核验")
    write_xlsx(MANUAL_FORWARD_XLSX, OUTPUT_HEADERS, manual_forward, sheet_name="手动转发")
    write_xlsx(DISABLED_XLSX, OUTPUT_HEADERS, disabled, sheet_name="禁用风险")
    write_opml(IMPORT_READY_OPML, import_ready)

    report_path = RETURN_DIR / f"InfoRadar_MVP2_6_全域候选源核验报告_{today_stamp()}.md"
    write_report(report_path, rows, grouped)
    write_wechat_summary(SUMMARY_TXT, rows, report_path)

    append_jsonl(
        LOG_DIR / "all_domain_source_verification.jsonl",
        {
            "time": now_text(),
            "input": str(INPUT_CSV),
            "counts": status_counts(rows),
            "output_files": [
                str(IMPORT_READY_XLSX),
                str(IMPORT_READY_OPML),
                str(MANUAL_REVIEW_XLSX),
                str(MANUAL_FORWARD_XLSX),
                str(DISABLED_XLSX),
                str(report_path),
                str(SUMMARY_TXT),
            ],
        },
    )

    result = {
        "success": True,
        "input": str(INPUT_CSV),
        "source_count": len(rows),
        "import_ready_count": len(import_ready),
        "manual_review_count": len(grouped.get("manual_review", [])),
        "watch_only_count": len(grouped.get("watch_only", [])),
        "manual_forward_count": len(manual_forward),
        "disabled_count": len(disabled),
        "return_xlsx": str(IMPORT_READY_XLSX),
        "return_opml": str(IMPORT_READY_OPML),
        "return_summary": str(SUMMARY_TXT),
        "report": str(report_path),
        "output_files": [
            str(IMPORT_READY_XLSX),
            str(IMPORT_READY_OPML),
            str(MANUAL_REVIEW_XLSX),
            str(MANUAL_FORWARD_XLSX),
            str(DISABLED_XLSX),
            str(report_path),
            str(SUMMARY_TXT),
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
