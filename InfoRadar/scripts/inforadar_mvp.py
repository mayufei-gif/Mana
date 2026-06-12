#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
import zipfile
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape as xml_escape

import all_domain_rules
import load_folo_link_items
import load_manual_items
import load_watch_updates


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
WEIGHTS_FILE = ROOT / "config" / "interest_weights.yaml"


OUTPUT_COLUMNS = [
    "序号",
    "标题",
    "标准化标题",
    "主分类",
    "标签",
    "全域分类",
    "源层级",
    "平台",
    "采集方式",
    "来源类型",
    "school_category",
    "detected_at",
    "last_seen_at",
    "is_new",
    "决策范围",
    "推送频率",
    "风险策略",
    "付费边界",
    "全域栏目",
    "来源名称",
    "订阅源URL",
    "原文URL",
    "URL异常",
    "URL异常说明",
    "Folo文件夹路径",
    "Folo订阅源名称",
    "发布时间",
    "发现时间",
    "相关度评分",
    "来源权威度",
    "行动价值",
    "机会价值",
    "风险等级",
    "决策影响类型",
    "决策影响/信息差说明",
    "为什么与你有关",
    "建议行动",
    "是否需要官方核验",
    "核验状态",
    "官方原文链接",
    "重复来源/备用链接",
    "去重ID",
    "source_trace_id",
    "dedupe_key",
    "用户备注",
    "原始内容保存路径",
    "是否进入今日情报",
    "是否进入长期知识库",
    "备注",
]


HIGH_RISK_SOFTWARE_WORDS = [
    "学习版",
    "破解版",
    "破解",
    "激活版",
    "激活工具",
    "免激活",
    "注册机",
    "序列号",
    "盗版",
    "绿色版",
    "特别版",
    "解锁版",
    "Keygen",
    "Crack",
    "Patch",
    "Activation",
    "Activation Tool",
    "Adobe Activation",
    "Activator",
    "在线影视站",
    "影视站",
    "侵权资源",
]

HIGH_RISK_SOFTWARE_SCORE_CAP = 35
LOW_SIGNAL_PROMO_SCORE_CAP = 40
LONG_TERM_OBSERVATION_SCORE_CAP = 52
URL_ANOMALY_SCORE_CAP = 52
HIGH_AUTHORITY_URL_ANOMALY_SCORE_CAP = 65

LOW_SIGNAL_PROMO_WORDS = [
    "速速关注",
    "关注 @",
    "新电报频道",
    "发现频道",
    "热门排行榜",
    "交流群",
    "抽奖",
    "福利",
]


CATEGORY_RULES = [
    ("国家政策", ["国务院", "国务院办公厅", "国家发展改革委", "人社部", "教育部", "工信部", "市场监管总局", "国家标准委"]),
    ("地方政策", ["山西省人社厅", "山西省教育厅", "山西省工信厅", "太原市人社局", "长治市人社局", "忻州市人社局", "地方政策"]),
    ("就业招聘", ["招聘", "岗位", "校招", "实习", "投递", "技术员", "山西焦煤", "霍州煤电", "晋能控股", "太重"]),
    ("职业证书", ["证书", "电工证", "低压电工", "高压电工", "职业资格", "职业技能等级", "等级认定"]),
    ("技能补贴", ["补贴", "申领", "就业补贴", "技能补贴"]),
    ("学校通知", ["学校", "山西机电", "教务", "毕业", "实习材料", "就业指导"]),
    ("PLC自动化", ["PLC", "西门子", "三菱", "汇川", "梯形图"]),
    ("变频器维修", ["变频器", "ACS800", "ACS880", "ABB", "故障代码", "参数"]),
    ("工业机器人", ["工业机器人", "机器人", "运维", "ABB机器人", "发那科", "安川"]),
    ("AutoCAD/EPLAN", ["AutoCAD", "CAD", "EPLAN", "电气图", "制图"]),
    ("电气维修", ["电气维修", "控制柜", "控制箱", "电路板", "矿用开关"]),
    ("风险提醒", HIGH_RISK_SOFTWARE_WORDS + ["骗局", "避坑", "高风险"]),
    ("AI工具", ["AI", "Codex", "ChatGPT", "OpenClaw", "RSSHub", "Folo", "Follow", "自动化"]),
    ("NAS与远程控制", ["NAS", "Tailscale", "RustDesk", "远程", "回传"]),
    ("3D打印", ["3D打印", "建模", "创客"]),
    ("赚钱机会", ["副业", "接单", "月入", "赚钱"]),
    ("新闻时政", ["时政", "新华网", "人民网", "中新网", "新闻", "国际频道"]),
]


FOLDER_RULES = [
    ("就业招聘/国企矿山", ["山西焦煤", "霍州煤电", "晋能控股", "潞安", "煤矿", "矿山", "国企"]),
    ("就业招聘/山西本地", ["山西", "太原", "长治", "忻州", "太重"]),
    ("就业招聘/电气自动化", ["电气", "自动化", "PLC", "技术员", "设备维修"]),
    ("政策证书/电工证", ["电工证", "低压电工", "高压电工", "特种作业"]),
    ("政策证书/技能补贴", ["技能补贴", "就业补贴", "补贴申领"]),
    ("政策证书/职业技能等级", ["职业技能等级", "技能等级", "等级认定"]),
    ("政策证书/学校通知", ["山西机电", "学校", "教务", "实习材料", "校园招聘"]),
    ("技术学习/PLC", ["PLC", "西门子", "三菱", "汇川", "梯形图"]),
    ("技术学习/变频器", ["变频器", "ACS800", "ACS880", "ABB", "故障代码"]),
    ("技术学习/工业机器人", ["工业机器人", "机器人运维", "ABB机器人"]),
    ("技术学习/AutoCAD_EPLAN", ["AutoCAD", "CAD", "EPLAN", "电气图"]),
    ("技术学习/电气维修", ["电气维修", "控制柜", "控制箱", "电路板"]),
    ("AI工具/Codex", ["Codex", "ChatGPT", "AI编程"]),
    ("AI工具/OpenClaw", ["OpenClaw", "微信指令", "gateway"]),
    ("AI工具/NAS自动化", ["NAS", "Tailscale", "RustDesk", "远程控制"]),
    ("AI工具/Folo_RSS", ["Folo", "Follow", "RSS", "OPML", "RSSHub"]),
    ("个人项目/3D打印", ["3D打印", "建模", "创客"]),
    ("个人项目/低成本项目", ["低成本项目", "个人项目", "接单"]),
    ("长期观察/风险提醒", ["风险", "营销", "夸大", "骗局", "月入过万"]),
]


AUTHORITY_RULES = [
    (100, ["人社部", "教育部", "工信部", "国家", "政府", "gov.cn"]),
    (92, ["省人社厅", "山西省", "官方", "edu.cn", "学校", "学院"]),
    (85, ["官网", "集团", "山西焦煤", "霍州煤电", "太重", "晋能控股", "潞安"]),
    (72, ["社区", "技术", "案例库", "教程", "观察"]),
    (45, ["博客", "转载", "公众号"]),
    (15, ["副业", "营销", "月入过万"]),
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def today_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    for path in [
        ROOT / "logs",
        ROOT / "data" / "normalized",
        ROOT / "data" / "deduped",
        ROOT / "reports" / "daily",
        ROOT / "memory" / "task_history",
        RETURN_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def log_line(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title or "")
    text = text.lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[【】\\[\\]（）()「」『』《》:：,，.!！?？;；|｜/_\\-—~·\"'“”‘’]", "", text)
    text = re.sub(r"(202[0-9]|20[0-9]{2})年?\\d{0,2}月?\\d{0,2}日?", "", text)
    noise = ["最新", "重磅", "必看", "速看", "收藏", "干货", "建议收藏", "全文"]
    for word in noise:
        text = text.replace(word, "")
    return text.strip()


def dedup_id(normalized_title: str) -> str:
    return hashlib.sha1(normalized_title.encode("utf-8")).hexdigest()[:12]


def contains_word(text: str, word: str) -> bool:
    if not word:
        return False
    if re.fullmatch(r"[A-Za-z0-9+#.]{1,4}", word):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, re.I))
    return word.lower() in text.lower()


def contains_any(text: str, words: list[str]) -> bool:
    return any(contains_word(text, w) for w in words)


def infer_policy_category(hay: str) -> tuple[str, list[str], str] | None:
    policy_terms = ["政策", "规划", "通知", "意见", "办法", "条例", "方案", "决定", "公告", "实施", "十五五"]
    national_sources = ["国务院", "国务院办公厅", "人社部", "教育部", "工信部", "国家发展改革委", "市场监管总局", "国家标准委", "gov.cn"]
    local_sources = ["山西省", "太原市", "长治市", "忻州市", "省人社厅", "省教育厅", "省工信厅", "人社局"]
    if contains_any(hay, national_sources) and contains_any(hay, policy_terms):
        tags = [word for word in national_sources + policy_terms if word.lower() in hay.lower()][:5]
        return "国家政策", tags or ["国家政策"], "政策环境"
    if contains_any(hay, local_sources) and contains_any(hay, policy_terms):
        tags = [word for word in local_sources + policy_terms if word.lower() in hay.lower()][:5]
        return "地方政策", tags or ["地方政策"], "政策环境"
    return None


def strong_text(item: dict) -> str:
    return " ".join(str(item.get(k, "")) for k in ["标题", "来源名称", "原文URL", "订阅源URL"])


def classify(item: dict) -> tuple[str, list[str], str]:
    # Folo folder is used for locating the item in Folo, not as primary evidence.
    # Otherwise every item inside an "AI" folder would be classified as AI.
    hay = strong_text(item)
    policy = infer_policy_category(hay)
    if policy:
        return policy
    for category, words in CATEGORY_RULES:
        if contains_any(hay, words):
            tags = [w for w in words if w.lower() in hay.lower()][:5]
            return category, tags or [category], infer_decision_type(category, hay)
    return "长期观察", ["长期观察"], "长期观察"


def infer_folder(item: dict) -> str:
    existing = (item.get("Folo文件夹路径") or "").strip()
    if existing:
        return existing
    hay = " ".join(str(item.get(k, "")) for k in ["标题", "摘要", "来源名称"])
    for folder, words in FOLDER_RULES:
        if contains_any(hay, words):
            return folder
    return "待定位"


def infer_decision_type(category: str, hay: str) -> str:
    if category == "风险提醒":
        return "风险规避"
    if category == "就业招聘":
        return "就业机会"
    if category in ("国家政策", "地方政策"):
        return "政策环境"
    if category in ("职业证书", "技能补贴", "学校通知"):
        return "证书规划" if category == "职业证书" else "政策补贴"
    if category in ("PLC自动化", "变频器维修", "工业机器人", "AutoCAD/EPLAN", "电气维修"):
        return "技能学习"
    if category in ("AI工具", "NAS与远程控制"):
        return "工具选择"
    if category in ("3D打印", "赚钱机会"):
        return "项目方向"
    if "风险" in hay or "营销" in hay or "月入" in hay:
        return "风险规避"
    return "长期观察"


def source_authority(item: dict) -> int:
    hay = " ".join(str(item.get(k, "")) for k in ["来源名称", "原文URL", "订阅源URL", "摘要"])
    for score, words in AUTHORITY_RULES:
        if contains_any(hay, words):
            return score
    return 55


def is_high_risk_software_item(item: dict) -> bool:
    hay = " ".join(str(item.get(k, "")) for k in ["标题", "摘要", "来源名称", "原文URL"])
    return contains_any(hay, HIGH_RISK_SOFTWARE_WORDS)


def is_low_signal_promo_item(item: dict) -> bool:
    hay = " ".join(str(item.get(k, "")) for k in ["标题", "摘要", "来源名称"])
    return contains_any(hay, LOW_SIGNAL_PROMO_WORDS)


def user_relevance(item: dict, category: str) -> int:
    hay = strong_text(item)
    high_words = ["山西", "电气", "PLC", "变频器", "ACS800", "电工证", "技能补贴", "招聘", "实习", "矿山", "Codex", "Folo", "NAS"]
    hits = sum(1 for w in high_words if w.lower() in hay.lower())
    base = 45 + min(hits * 8, 45)
    if category in ("就业招聘", "职业证书", "技能补贴", "变频器维修", "国家政策", "地方政策"):
        base += 8
    return min(base, 100)


def timeliness(item: dict) -> int:
    raw = (item.get("发布时间") or "").strip()
    if not raw:
        return 55
    try:
        day = dt.date.fromisoformat(raw[:10])
        age = (dt.date.today() - day).days
        if age <= 3:
            return 100
        if age <= 14:
            return 85
        if age <= 45:
            return 70
        return 45
    except Exception:
        return 55


def action_value(item: dict, category: str) -> int:
    hay = strong_text(item)
    if category == "风险提醒":
        return 20
    if category == "就业招聘":
        return 90
    if category in ("职业证书", "技能补贴", "学校通知", "国家政策", "地方政策"):
        return 86
    if contains_any(hay, ["报名", "申领", "投递", "截止", "招聘", "通知"]):
        return 88
    if category in ("PLC自动化", "变频器维修", "工业机器人", "AutoCAD/EPLAN", "电气维修"):
        return 76
    if category in ("赚钱机会",):
        return 35
    return 60


def opportunity_value(item: dict, category: str) -> int:
    hay = strong_text(item)
    if category == "风险提醒":
        return 20
    if contains_any(hay, ["截止", "报名", "招聘", "补贴", "校招", "申领"]):
        return 88
    if category in ("就业招聘", "技能补贴", "国家政策", "地方政策"):
        return 82
    if category in ("PLC自动化", "变频器维修", "AI工具"):
        return 65
    return 50


def risk_level(item: dict) -> tuple[str, int]:
    hay = " ".join(str(item.get(k, "")) for k in ["标题", "摘要", "来源名称"])
    if is_high_risk_software_item(item):
        return "高", 95
    if contains_any(hay, ["月入过万", "副业", "营销", "夸大", "三天学会"]):
        return "高", 90
    if contains_any(hay, ["转载", "公众号", "待核验"]):
        return "中", 60
    return "低", 20


def overall_score(parts: dict) -> int:
    risk_bonus = max(0, 100 - parts["risk_numeric"])
    score = (
        parts["source_authority"] * 0.25
        + parts["user_relevance"] * 0.25
        + parts["timeliness"] * 0.15
        + parts["action_value"] * 0.20
        + parts["opportunity_value"] * 0.10
        + risk_bonus * 0.05
    )
    return int(round(score))


def safe_key_part(text: str) -> str:
    text = re.sub(r"\s+", "_", (text or "").strip())
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text)
    return text.strip("_")[:80] or "unknown"


def make_weight_key(kind: str, value: str) -> str:
    return f"{kind}__{safe_key_part(value)}"


def load_interest_weights() -> dict[str, int]:
    if not WEIGHTS_FILE.exists():
        return {}
    weights: dict[str, int] = {}
    for line in WEIGHTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*([^:#][^:]*)\s*:\s*(-?\d+)\s*$", line)
        if match:
            weights[match.group(1).strip()] = int(match.group(2))
    return weights


def preference_bonus(item: dict, category: str, tags: list[str], weights: dict[str, int]) -> int:
    if not weights:
        return 0
    bonus = 0
    source = item.get("来源名称", "")
    source_key = make_weight_key("source", source)
    category_key = make_weight_key("category", category)
    bonus += int(weights.get(source_key, 0))
    bonus += int(weights.get(category_key, 0))
    hay = " ".join([item.get("标题", ""), item.get("摘要", ""), " ".join(tags), source])
    for key, value in weights.items():
        if not key.startswith("keyword__") or not value:
            continue
        keyword = key[len("keyword__") :].replace("_", " ")
        if contains_word(hay, keyword):
            bonus += int(value)
    return max(-12, min(12, bonus))


def need_verify(item: dict, category: str) -> tuple[str, str, str]:
    url = item.get("原文URL", "")
    if category == "风险提醒":
        return "是", "高风险线索，需谨慎核验", ""
    if category in ("就业招聘", "职业证书", "技能补贴", "学校通知", "国家政策", "地方政策"):
        if any(token in url for token in ["gov.cn", "edu.cn"]) or "官网" in item.get("来源名称", ""):
            return "是", "已核验官方来源", url
        return "是", "需官方核验", ""
    if "转载" in item.get("来源名称", "") or "公众号" in item.get("来源名称", ""):
        return "是", "仅线索", ""
    return "否", "无需强核验", ""


def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit((value or "").strip())
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_article_url(article_url: str, feed_url: str) -> tuple[str, str, str]:
    raw = (article_url or "").strip()
    feed = (feed_url or "").strip()
    if not raw:
        return raw, "是", "原文URL为空"
    if re.search(r"[\x00-\x1f<>\"{}|\\^`\s]", raw):
        return raw, "是", "URL包含非法字符"
    if raw.startswith(("/", "./", "../")):
        fixed = urljoin(feed, raw) if is_http_url(feed) else raw
        reason = "原文URL是相对路径，已尝试补全" if fixed != raw else "原文URL是相对路径"
        return fixed, "是", reason
    if not is_http_url(raw):
        return raw, "是", "原文URL不是http/https"
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw, "是", "URL无法解析"
    if not parsed.scheme or not parsed.netloc:
        return raw, "是", "URL无法解析"
    if feed and raw.rstrip("/") == feed.rstrip("/"):
        return raw, "是", "原文URL等于订阅源URL"
    return raw, "否", ""


def relationship_text(category: str, decision_type: str) -> str:
    mapping = {
        "就业机会": "与你当前实习和准就业阶段直接相关，可能影响投递方向和岗位准备。",
        "证书规划": "与你的电气、智能控制和就业证书规划相关，可能影响毕业前证书准备。",
        "政策补贴": "可能影响技能补贴、证书报名或就业政策窗口，需要及时核验。",
        "政策环境": "来自政策或官方公告类信息，可能影响行业方向、就业机会、证书规划或后续信息差判断。",
        "技能学习": "与你的 PLC、变频器、电气维修等专业能力积累相关，可沉淀到技术学习库。",
        "工具选择": "可能提升你现有 NAS、Codex、微信自动化和信息处理效率。",
        "项目方向": "可作为个人作品集或低成本项目观察，但需要控制投入和风险。",
        "风险规避": "这类信息可能涉及夸大收益、营销引导、盗版软件资源或安全风险，应降权并谨慎核验。",
    }
    return mapping.get(decision_type, "可作为长期观察信息，暂不建议投入过多精力。")


def action_text(category: str, decision_type: str, item: dict) -> str:
    if decision_type == "就业机会":
        return "保存岗位要求，核验官网原文；对照简历补齐电气、PLC、CAD或设备维修能力。"
    if decision_type == "证书规划":
        return "核验报名条件、考试时间和适用地区；加入证书路线表。"
    if decision_type == "政策补贴":
        return "优先打开官方链接核验适用对象、地区和截止时间；符合条件则加入监控。"
    if decision_type == "政策环境":
        return "先保存原文和发布时间；重点看是否影响就业、证书、智能制造、电气自动化或山西本地机会。"
    if decision_type == "技能学习":
        return "归档到对应技术库；选 1 个案例做成笔记或小练习。"
    if decision_type == "工具选择":
        return "先收藏并观察是否能接入现有 NAS/Codex/微信链路，不急于大改系统。"
    if decision_type == "项目方向":
        return "作为低成本项目观察，先评估材料、时间和能否形成作品集。"
    if decision_type == "风险规避":
        return "不建议下载、安装或按其指引操作；保留为风险样本，降低同类来源权重。"
    return "暂时收藏观察，后续有更多同类信息再判断是否提高优先级。"


TECH_CATEGORIES = {"PLC自动化", "变频器维修", "工业机器人", "AutoCAD/EPLAN", "电气维修"}
POLICY_CERT_CATEGORIES = {"国家政策", "地方政策", "学校通知", "职业证书", "技能补贴"}
AI_CATEGORIES = {"AI工具", "NAS与远程控制"}


def row_hay(row: dict) -> str:
    return " ".join(
        str(row.get(key, ""))
        for key in ["标题", "主分类", "标签", "全域分类", "来源名称", "摘要", "原文URL", "订阅源URL", "Folo文件夹路径", "平台"]
    )


def row_matches_report_topic(row: dict, topic: str) -> bool:
    topic = (topic or "").strip()
    if topic in ("", "今日", "今日情报", "全域情报", "全部", "样例"):
        return True
    category = row.get("主分类", "")
    broad = row.get("全域分类", "")
    section = row.get("全域栏目", "")
    hay = row_hay(row)
    if topic == "我的学校":
        return (
            category in {"我的学校", "学校通知"}
            or broad in {"我的学校", "学校通知", "教务学业", "学工团委", "奖助评优", "入团竞选", "创新创业竞赛", "校园招聘实习", "毕业档案"}
            or section == "我的学校"
            or contains_any(hay, ["山西晋中理工", "晋中理工", "教务", "学工", "团委", "奖学金", "入团", "比赛通知"])
        )
    if topic == "购物情报":
        return (
            broad in {"购物资源", "消费购物", "数码装备"}
            or category in {"购物资源"}
            or (contains_any(hay, ["淘宝", "拼多多", "京东", "闲鱼", "1688", "万用表", "示波器", "电烙铁", "工具耗材"]) and broad != "付费知识")
        )
    if topic == "付费资源":
        return broad == "付费知识" or category == "付费知识" or row.get("平台") == "paid_resource"
    if topic == "风险提醒":
        return (
            row.get("风险等级") == "高"
            or category == "风险提醒"
            or broad in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}
            or section == "风险提醒"
        )
    if topic == "AI":
        return category in AI_CATEGORIES or contains_any(hay, ["AI", "OpenAI", "ChatGPT", "Codex", "Folo", "RSSHub", "OpenClaw", "Agent", "模型", "API", "自动化"])
    if topic == "政策":
        return category in POLICY_CERT_CATEGORIES or contains_any(hay, ["政策", "人社", "教育", "工信", "政府", "通知", "补贴", "技能政策", "就业政策"])
    if topic == "招聘":
        return category == "就业招聘" or contains_any(hay, ["招聘", "校招", "实习", "岗位", "就业", "山西焦煤", "霍州煤电", "晋能控股", "太重", "潞安"])
    if topic == "技术":
        return category in TECH_CATEGORIES or contains_any(hay, ["PLC", "变频器", "ACS800", "ACS880", "工业机器人", "AutoCAD", "EPLAN", "电气维修", "控制柜", "矿用设备"])
    if topic == "证书":
        return category in {"职业证书", "技能补贴"} or contains_any(hay, ["证书", "电工证", "低压电工", "高压电工", "职业技能", "技能等级", "技能补贴", "计算机等级", "CAD证书", "考试报名"])
    all_domain_keywords = all_domain_rules.TOPIC_KEYWORDS.get(topic)
    if all_domain_keywords is not None:
        if not all_domain_keywords:
            return True
        return all_domain_rules.contains_any(hay, all_domain_keywords)
    return contains_any(hay, [topic])


def intel_bucket(row: dict) -> str:
    section = row.get("全域栏目", "")
    if section:
        return section
    category = row.get("主分类", "")
    hay = row_hay(row)
    if category in {"风险提醒"} or row.get("风险等级") == "高":
        return "风险提醒"
    if category in POLICY_CERT_CATEGORIES:
        return "政策证书"
    if category == "就业招聘":
        return "招聘就业"
    if category in TECH_CATEGORIES:
        return "技术学习"
    if category in AI_CATEGORIES:
        return "AI工具"
    if contains_any(hay, ["招聘", "岗位", "校招", "实习"]):
        return "招聘就业"
    if contains_any(hay, ["证书", "补贴", "人社", "政策"]):
        return "政策证书"
    if contains_any(hay, ["PLC", "变频器", "电气", "机器人", "CAD"]):
        return "技术学习"
    if contains_any(hay, ["AI", "Codex", "OpenAI", "Folo", "RSSHub"]):
        return "AI工具"
    return "长期观察"


def blocked_from_top10(row: dict) -> bool:
    remarks = row.get("备注", "")
    return (
        row.get("风险等级") == "高"
        or row.get("URL异常") == "是"
        or "高风险" in remarks
        or contains_any(row_hay(row), HIGH_RISK_SOFTWARE_WORDS)
    )


def composite_intel_sort(rows: list[dict]) -> list[dict]:
    quotas = {
        "我的学校": 6,
        "专业成长": 8,
        "热点与时事": 6,
        "AI与科技": 6,
        "学习成长": 4,
        "资源与购物": 2,
        "生活权益": 4,
        "机会观察": 2,
        "文化娱乐": 2,
        "风险提醒": 2,
    }
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        bucket = intel_bucket(row)
        row["备注"] = "；".join(part for part in [row.get("备注", ""), f"今日情报分组：{bucket}"] if part)
        buckets.setdefault(bucket, []).append(row)
    for bucket_rows in buckets.values():
        bucket_rows.sort(key=lambda r: int(r.get("相关度评分") or 0), reverse=True)

    selected: list[dict] = []
    used: set[str] = set()

    def take(bucket: str, limit: int, allow_blocked: bool = False) -> None:
        for row in buckets.get(bucket, []):
            if len([item for item in selected if intel_bucket(item) == bucket]) >= limit:
                return
            key = row.get("去重ID", "")
            if key in used:
                continue
            if not allow_blocked and blocked_from_top10(row):
                continue
            selected.append(row)
            used.add(key)

    for bucket in ["我的学校", "专业成长", "热点与时事", "AI与科技", "学习成长", "生活权益", "资源与购物", "机会观察", "文化娱乐"]:
        take(bucket, quotas[bucket], allow_blocked=False)

    safe_remaining = [row for row in rows if row.get("去重ID", "") not in used and not blocked_from_top10(row)]
    safe_remaining.sort(key=lambda r: int(r.get("相关度评分") or 0), reverse=True)
    for row in safe_remaining:
        if len(selected) >= 10:
            break
        selected.append(row)
        used.add(row.get("去重ID", ""))

    take("风险提醒", quotas["风险提醒"], allow_blocked=True)

    rest = [row for row in rows if row.get("去重ID", "") not in used]
    rest.sort(key=lambda r: (blocked_from_top10(r), -int(r.get("相关度评分") or 0)))
    selected.extend(rest)
    return selected


def read_csv_items(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def is_manual_item(item: dict) -> bool:
    return item.get("input_source") == "manual_inbox" or item.get("source_type") == "manual_collected"


def is_folo_link_item(item: dict) -> bool:
    return item.get("input_source") == "folo_article_links" or item.get("source_type") == "folo_webhook"


def is_watch_update_item(item: dict) -> bool:
    return item.get("input_source") == "watch_updates" or item.get("source_type") == "watch_update"


def is_curated_context_item(item: dict) -> bool:
    return is_manual_item(item) or is_watch_update_item(item)


def manual_daily_section(item: dict, fallback: str) -> str:
    broad = item.get("broad_category", "")
    risk = item.get("风险等级", "")
    if risk == "高" or broad in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}:
        return "风险提醒"
    if broad in {"我的学校", "学校通知", "教务学业", "学工团委", "奖助评优", "入团竞选", "创新创业竞赛", "校园招聘实习", "毕业档案"}:
        return "我的学校"
    if broad in {"购物资源", "消费购物", "数码装备", "工具软件", "付费知识", "课程资源"}:
        return "资源与购物"
    if broad in {"学习资源", "考试升学", "语言学习", "论文文档"}:
        return "学习成长"
    return fallback


def manual_risk_policy(item: dict, fallback: str) -> str:
    broad = item.get("broad_category", "")
    risk = item.get("风险等级", "")
    if risk == "高" or broad in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}:
        return "risk_only_no_opportunity"
    if broad in {"购物资源", "消费购物", "付费知识"}:
        return "metadata_public_only"
    return fallback


def manual_paywall_policy(item: dict, fallback: str) -> str:
    broad = item.get("broad_category", "")
    if broad in {"购物资源", "消费购物", "付费知识"}:
        return "metadata_only"
    return fallback


def merge_manual_domain(item: dict, domain: dict) -> dict:
    if not is_curated_context_item(item):
        return domain
    merged = dict(domain)
    if item.get("broad_category"):
        merged["broad_category"] = item["broad_category"]
    if item.get("source_layer"):
        merged["source_layer"] = item["source_layer"]
    if item.get("平台"):
        merged["platform"] = item["平台"]
    if item.get("decision_scope"):
        merged["decision_scope"] = item["decision_scope"]
    merged["acquisition_mode"] = "watch_only" if is_watch_update_item(item) else "manual_inbox"
    merged["daily_section"] = manual_daily_section(item, merged.get("daily_section", "长期观察"))
    merged["risk_policy"] = manual_risk_policy(item, merged.get("risk_policy", "normal"))
    merged["paywall_policy"] = manual_paywall_policy(item, merged.get("paywall_policy", "public_only"))
    if item.get("是否进入今日情报") == "no":
        merged["push_frequency"] = "on_demand"
    elif item.get("source_layer") == "A_core":
        merged["push_frequency"] = "daily"
    return merged


def process_items(items: list[dict], topic: str = "") -> tuple[list[dict], dict]:
    discovered = today_text()
    interest_weights = load_interest_weights()
    custom_weight_used = any(key.startswith(("source__", "category__", "keyword__")) for key in interest_weights)
    preference_adjusted_count = 0
    rows_by_id: dict[str, dict] = {}
    duplicate_count = 0
    url_anomaly_count = 0
    folo_link_input_count = sum(1 for item in items if is_folo_link_item(item))
    watch_input_count = sum(1 for item in items if is_watch_update_item(item))
    auto_input_count = sum(1 for item in items if not is_manual_item(item) and not is_folo_link_item(item) and not is_watch_update_item(item))
    manual_input_count = sum(1 for item in items if is_manual_item(item))
    for raw in items:
        title = (raw.get("标题") or "").strip()
        if not title:
            continue
        normalized = normalize_title(title)
        did = (raw.get("dedupe_key") or "").strip() if (is_manual_item(raw) or is_watch_update_item(raw)) else ""
        did = did or dedup_id(normalized)
        folder = infer_folder(raw)
        item = dict(raw)
        item["Folo文件夹路径"] = folder
        if is_manual_item(item) and not (item.get("原文URL") or "").strip():
            normalized_url, url_anomaly, url_anomaly_reason = "", "否", "手动文本无外部链接"
        else:
            normalized_url, url_anomaly, url_anomaly_reason = normalize_article_url(
                item.get("原文URL", ""),
                item.get("订阅源URL", ""),
            )
        item["原文URL"] = normalized_url
        if is_curated_context_item(item) and item.get("主分类"):
            category = item.get("主分类", "")
            label = "官网观察" if is_watch_update_item(item) else "手动收集"
            tags = [part for part in [item.get("broad_category", ""), item.get("平台", ""), label] if part]
            decision_type = item.get("decision_scope") or infer_decision_type(category, strong_text(item))
        else:
            category, tags, decision_type = classify(item)
        all_domain_text = strong_text(item)
        domain = merge_manual_domain(item, all_domain_rules.enrich_record(all_domain_text, category))
        if domain["decision_scope"] not in ("长期观察", ""):
            decision_type = {
                "学校行动": "政策环境",
                "职业成长": decision_type,
                "环境判断": "政策环境",
                "工具/技术选择": "工具选择",
                "购买/学习决策": "工具选择",
                "机会探索": "项目方向",
                "风险规避": "风险规避",
            }.get(domain["decision_scope"], decision_type)
        authority = source_authority(item)
        rel = user_relevance(item, category)
        time_score = timeliness(item)
        action = action_value(item, category)
        opp = opportunity_value(item, category)
        risk_text, risk_numeric = risk_level(item)
        if is_curated_context_item(item) and item.get("风险等级"):
            risk_text = item.get("风险等级", risk_text)
            risk_numeric = {"低": 20, "中": 60, "高": 95}.get(risk_text, risk_numeric)
        parts = {
            "source_authority": authority,
            "user_relevance": rel,
            "timeliness": time_score,
            "action_value": action,
            "opportunity_value": opp,
            "risk_numeric": risk_numeric,
        }
        total = overall_score(parts)
        pref_bonus = preference_bonus(item, category, tags, interest_weights)
        if pref_bonus:
            preference_adjusted_count += 1
            total += pref_bonus
        high_risk_software = is_high_risk_software_item(item)
        low_signal_promo = is_low_signal_promo_item(item)
        if high_risk_software:
            total = min(total, HIGH_RISK_SOFTWARE_SCORE_CAP)
        if low_signal_promo:
            total = min(total, LOW_SIGNAL_PROMO_SCORE_CAP)
        if category == "长期观察":
            total = min(total, LONG_TERM_OBSERVATION_SCORE_CAP)
        need_v, verify_status, official_url = need_verify(item, category)
        if is_curated_context_item(item) and item.get("是否需要核验"):
            need_v = item.get("是否需要核验", need_v)
            verify_status = "来自官网观察源，需打开原文核验" if is_watch_update_item(item) and need_v == "是" else ("来自手动收集，需按来源类型核验" if need_v == "是" else verify_status)
        if url_anomaly == "是":
            url_anomaly_count += 1
            need_v = "是"
            if authority >= 92:
                total = min(total, HIGH_AUTHORITY_URL_ANOMALY_SCORE_CAP)
                verify_status = f"高权威来源但URL异常：{url_anomaly_reason}"
            else:
                total = min(total, URL_ANOMALY_SCORE_CAP)
                verify_status = f"URL异常，已降权：{url_anomaly_reason}"
            official_url = official_url if is_http_url(official_url) and url_anomaly_reason != "原文URL等于订阅源URL" else ""
        if high_risk_software:
            need_v = "是"
            verify_status = "高风险软件资源，已强制降权"
        elif low_signal_promo:
            verify_status = "低信号推广/频道类内容，已降权"
        remarks = []
        if high_risk_software:
            remarks.append("高风险软件资源已降权，不建议下载或安装")
        if low_signal_promo:
            remarks.append("低信号推广/频道类内容已降权")
        if category == "长期观察":
            remarks.append("长期观察类内容不置顶")
        if url_anomaly == "是":
            remarks.append(f"URL异常：{url_anomaly_reason}；修复前不建议进入前10")
        if domain["paywall_policy"] in ("metadata_only", "forbidden_bypass"):
            remarks.append("付费/平台边界：仅处理公开元信息，不绕过访问控制")
        if domain["risk_policy"] == "risk_only_no_opportunity":
            remarks.append("风险类内容只进入风险提醒，不进入机会推荐")
        if is_manual_item(item):
            remarks.append("来自手动收集")
            if item.get("备注"):
                remarks.append(item.get("备注", ""))
        if is_watch_update_item(item):
            remarks.append("来自watch_only官网观察源，不等同于Folo原条")
            if item.get("备注"):
                remarks.append(item.get("备注", ""))
        school_category = item.get("school_category", "") if is_watch_update_item(item) else ""
        detected_at = item.get("detected_at", "") if is_watch_update_item(item) else ""
        last_seen_at = item.get("last_seen_at", "") if is_watch_update_item(item) else ""
        is_new = item.get("is_new", "") if is_watch_update_item(item) else ""
        row = {
            "标题": title,
            "标准化标题": normalized,
            "主分类": category,
            "标签": "、".join(tags),
            "全域分类": domain["broad_category"],
            "源层级": domain["source_layer"],
            "平台": domain["platform"],
            "采集方式": domain["acquisition_mode"],
            "来源类型": item.get("source_type", "folo_rss") if (is_manual_item(item) or is_folo_link_item(item) or is_watch_update_item(item)) else "folo_rss",
            "school_category": school_category,
            "detected_at": detected_at,
            "last_seen_at": last_seen_at,
            "is_new": is_new,
            "决策范围": domain["decision_scope"],
            "推送频率": domain["push_frequency"],
            "风险策略": domain["risk_policy"],
            "付费边界": domain["paywall_policy"],
            "全域栏目": domain["daily_section"],
            "来源名称": item.get("来源名称", ""),
            "订阅源URL": item.get("订阅源URL", ""),
            "原文URL": item.get("原文URL", ""),
            "URL异常": url_anomaly,
            "URL异常说明": url_anomaly_reason,
            "Folo文件夹路径": folder,
            "Folo订阅源名称": item.get("来源名称", ""),
            "发布时间": item.get("发布时间", ""),
            "发现时间": discovered,
            "相关度评分": total,
            "来源权威度": authority,
            "行动价值": action,
            "机会价值": opp,
            "风险等级": risk_text,
            "决策影响类型": decision_type,
            "决策影响/信息差说明": relationship_text(category, decision_type),
            "为什么与你有关": item.get("为什么与你有关") if is_curated_context_item(item) and item.get("为什么与你有关") else relationship_text(category, decision_type),
            "建议行动": item.get("建议行动") if is_curated_context_item(item) and item.get("建议行动") else action_text(category, decision_type, item),
            "是否需要官方核验": need_v,
            "核验状态": verify_status,
            "官方原文链接": official_url,
            "重复来源/备用链接": "",
            "去重ID": did,
            "source_trace_id": item.get("source_trace_id", ""),
            "dedupe_key": item.get("dedupe_key", ""),
            "用户备注": item.get("用户备注", ""),
            "原始内容保存路径": item.get("原始内容保存路径", ""),
            "是否进入今日情报": item.get("是否进入今日情报", ""),
            "是否进入长期知识库": item.get("是否进入长期知识库", ""),
            "备注": "；".join(remarks),
        }
        if did in rows_by_id:
            duplicate_count += 1
            existing = rows_by_id[did]
            if int(row["相关度评分"]) > int(existing["相关度评分"]):
                row["重复来源/备用链接"] = combine_duplicate(existing, row)
                rows_by_id[did] = row
            else:
                existing["重复来源/备用链接"] = combine_duplicate(existing, row)
        else:
            rows_by_id[did] = row

    rows = list(rows_by_id.values())
    before_topic_filter_count = len(rows)
    rows = [row for row in rows if row_matches_report_topic(row, topic)]
    rows.sort(key=lambda r: int(r["相关度评分"]), reverse=True)
    if topic in ("今日", "今日情报", "全域情报"):
        rows = composite_intel_sort(rows)
    for idx, row in enumerate(rows, 1):
        row["序号"] = idx
    stats = {
        "input_count": len(items),
        "auto_input_count": auto_input_count,
        "manual_input_count": manual_input_count,
        "watch_input_count": watch_input_count,
        "folo_link_input_count": folo_link_input_count,
        "output_count": len(rows),
        "manual_output_count": sum(1 for row in rows if row.get("来源类型") == "manual_collected"),
        "watch_output_count": sum(1 for row in rows if row.get("来源类型") == "watch_update"),
        "folo_link_output_count": sum(1 for row in rows if row.get("来源类型") == "folo_webhook"),
        "manual_enter_today_count": sum(1 for row in rows if row.get("来源类型") == "manual_collected" and row.get("是否进入今日情报") in {"yes", "pending", "risk_only"}),
        "manual_risk_count": sum(1 for row in rows if row.get("来源类型") == "manual_collected" and (row.get("风险等级") == "高" or row.get("全域栏目") == "风险提醒")),
        "manual_school_count": sum(1 for row in rows if row.get("来源类型") == "manual_collected" and row.get("全域栏目") == "我的学校"),
        "school_watch_output_count": sum(1 for row in rows if row.get("来源类型") == "watch_update" and row.get("全域栏目") == "我的学校"),
        "school_watch_new_count": sum(1 for row in rows if row.get("来源类型") == "watch_update" and row.get("全域栏目") == "我的学校" and row.get("is_new") == "yes"),
        "duplicate_count": duplicate_count,
        "topic_filtered_count": before_topic_filter_count - len(rows),
        "preference_weight_used": custom_weight_used,
        "preference_adjusted_count": preference_adjusted_count,
        "url_anomaly_count": url_anomaly_count,
    }
    return rows, stats


def combine_duplicate(existing: dict, row: dict) -> str:
    pieces = []
    old = existing.get("重复来源/备用链接", "")
    if old:
        pieces.append(old)
    pieces.append(f'{row.get("来源名称", "")}: {row.get("原文URL", "")}')
    return " | ".join(p for p in pieces if p.strip())


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def xlsx_col_name(idx: int) -> str:
    name = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def sheet_xml(rows: list[list[str]]) -> str:
    xml_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{xlsx_col_name(c_idx)}{r_idx}"
            text = xml_escape("" if value is None else str(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">' + "".join(cells) + "</row>")
    last_col = xlsx_col_name(len(OUTPUT_COLUMNS))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetData>'
        + "".join(xml_rows)
        + f'</sheetData><autoFilter ref="A1:{last_col}1"/></worksheet>'
    )


def write_xlsx(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = [OUTPUT_COLUMNS]
    for row in rows:
        table.append([row.get(col, "") for col in OUTPUT_COLUMNS])
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="InfoRadar" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet_xml(table),
        "docProps/app.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>InfoRadar</Application></Properties>',
        "docProps/core.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>InfoRadar</dc:creator><dc:title>InfoRadar Folo Report</dc:title><dcterms:created xsi:type="dcterms:W3CDTF">{dt.datetime.now(dt.UTC).isoformat()}</dcterms:created></cp:coreProperties>',
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)


def write_markdown(path: Path, rows: list[dict], stats: dict, xlsx_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top = rows[:5]
    lines = [
        "# InfoRadar Folo 表格摘要",
        "",
        f"生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Excel 文件：{xlsx_path}",
        "",
        "## 运行统计",
        "",
        f"- 输入条数：{stats['input_count']}",
        f"- 自动源条数：{stats.get('auto_input_count', 0)}",
        f"- 手动收集条数：{stats.get('manual_input_count', 0)}",
        f"- 官网观察条数：{stats.get('watch_input_count', 0)}",
        f"- Folo回流条数：{stats.get('folo_link_input_count', 0)}",
        f"- 进入表格手动条数：{stats.get('manual_output_count', 0)}",
        f"- 进入表格官网观察条数：{stats.get('watch_output_count', 0)}",
        f"- 进入表格Folo回流条数：{stats.get('folo_link_output_count', 0)}",
        f"- 手动学校信息：{stats.get('manual_school_count', 0)}",
        f"- 学校官网观察：{stats.get('school_watch_output_count', 0)}",
        f"- 学校官网新增：{stats.get('school_watch_new_count', 0)}",
        f"- 手动风险提醒：{stats.get('manual_risk_count', 0)}",
        f"- 输出条数：{stats['output_count']}",
        f"- 合并重复标题：{stats['duplicate_count']}",
        f"- 主题过滤条目：{stats.get('topic_filtered_count', 0)}",
        f"- URL异常条目：{stats.get('url_anomaly_count', 0)}",
        "",
        "## 前 5 条",
        "",
    ]
    for row in top:
        lines.extend(
            [
                f"### {row['序号']}. {row['标题']}",
                "",
                f"- 来源：{row['来源名称']}",
                f"- 分类：{row['主分类']} / {row['标签']}",
                f"- Folo 位置：{row['Folo文件夹路径']}",
                f"- 评分：{row['相关度评分']}",
                f"- 决策影响：{row['决策影响类型']}",
                f"- 为什么与你有关：{row['为什么与你有关']}",
                f"- 建议行动：{row['建议行动']}",
                f"- 核验状态：{row['核验状态']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_wechat_summary(path: Path, rows: list[dict], stats: dict, xlsx_path: Path, topic: str = "") -> None:
    if topic in ("今日", "今日情报", "全域情报"):
        write_daily_intel_wechat_summary(path, rows, stats, xlsx_path)
        return
    top = rows[:5]
    lines = [
        "【InfoRadar Folo 表格】",
        "",
        f"已生成：{xlsx_path.name}",
        f"保存位置：{xlsx_path.parent}",
        f"输入 {stats['input_count']} 条，输出 {stats['output_count']} 条，合并重复 {stats['duplicate_count']} 条，过滤 {stats.get('topic_filtered_count', 0)} 条，URL异常 {stats.get('url_anomaly_count', 0)} 条。",
        f"自动源 {stats.get('auto_input_count', 0)} 条，手动收集 {stats.get('manual_input_count', 0)} 条，官网观察 {stats.get('watch_input_count', 0)} 条，Folo回流 {stats.get('folo_link_input_count', 0)} 条；进入本表手动 {stats.get('manual_output_count', 0)} 条，官网观察 {stats.get('watch_output_count', 0)} 条，Folo回流 {stats.get('folo_link_output_count', 0)} 条。",
        f"学校官网观察 {stats.get('school_watch_output_count', 0)} 条，其中新增 {stats.get('school_watch_new_count', 0)} 条。",
        "",
    ]
    if not top:
        lines.extend(
            [
                "本次没有抓到匹配条目。",
                "",
                "可能原因：",
                "- Folo 当前源池里缺少该主题订阅源",
                "- RSSHub/上游源暂时不可访问",
                "- 主题关键词需要补充",
                "",
                "建议下一步：查源 关键词 / 导入Folo订阅 / 做源池",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.append("前5条：")
    for row in top:
        lines.append(f"{row['序号']}. {row['标题']}")
        lines.append(f"   关联：{row['决策影响类型']} / {row['Folo文件夹路径']}")
        lines.append(f"   建议：{row['建议行动']}")
    lines.extend(["", "可继续发送：深挖1 / 这个有用 / 这个没用 / 查看完整表格"])
    path.write_text("\n".join(lines), encoding="utf-8")


def first_rows_by_bucket(rows: list[dict], bucket: str, limit: int) -> list[dict]:
    out = []
    for row in rows:
        if intel_bucket(row) == bucket:
            out.append(row)
        if len(out) >= limit:
            break
    return out


def school_summary_action(row: dict) -> str:
    category = row.get("school_category") or "其他学校事务"
    mapping = {
        "奖学金助学金": "核验申请条件、材料要求和截止时间。",
        "比赛竞赛": "查看报名时间、参赛条件和提交材料。",
        "校园招聘": "查看岗位要求、宣讲/双选时间和投递入口。",
        "入团团员竞选": "核验报名条件、团支部流程和截止时间。",
        "团委通知": "查看活动对象、报名方式和时间安排。",
        "评优评先": "核验评选条件、公示时间和材料要求。",
        "教务通知": "核验考试、课程、选课或学籍事项的具体安排。",
        "学工通知": "查看学生事务要求和办理截止时间。",
        "实习实践": "核验实践安排、材料提交和安全要求。",
        "毕业相关": "查看毕业材料、档案、答辩或离校安排。",
    }
    return mapping.get(category, "打开官网原文核验时间、对象和具体要求。")


def append_school_section(lines: list[str], rows: list[dict], limit: int = 5) -> None:
    lines.append("【我的学校】")
    school_rows = [row for row in rows if intel_bucket(row) == "我的学校"]
    new_rows = [row for row in school_rows if row.get("is_new") == "yes"]
    display_rows = (new_rows or school_rows)[:limit]
    if not display_rows:
        lines.append("今日暂无新的学校观察源更新。")
        lines.append("")
        return
    if not new_rows:
        lines.append("今日暂无新的学校观察源更新；以下是当前学校观察源快照中最相关条目：")
    for idx, row in enumerate(display_rows, 1):
        category = row.get("school_category") or "其他学校事务"
        source = "官网观察源" if row.get("来源类型") == "watch_update" else (row.get("来源名称") or "学校信息")
        lines.append(f"{idx}. [{category}] {row['标题']}")
        lines.append(f"   来源：{source}")
        lines.append(f"   建议：{school_summary_action(row)}")
    lines.append("")


def write_daily_intel_wechat_summary(path: Path, rows: list[dict], stats: dict, xlsx_path: Path) -> None:
    lines = [
        "【InfoRadar 今日情报】",
        "",
        f"已生成：{xlsx_path.name}",
        f"保存位置：{xlsx_path.parent}",
        f"输入 {stats['input_count']} 条，输出 {stats['output_count']} 条，合并重复 {stats['duplicate_count']} 条，过滤 {stats.get('topic_filtered_count', 0)} 条，URL异常 {stats.get('url_anomaly_count', 0)} 条。",
        f"自动源：{stats.get('auto_input_count', 0)} 条；手动收集：{stats.get('manual_input_count', 0)} 条；官网观察：{stats.get('watch_input_count', 0)} 条；Folo回流：{stats.get('folo_link_input_count', 0)} 条；进入今日情报的手动条数：{stats.get('manual_enter_today_count', 0)} 条。",
        f"学校信息：手动 {stats.get('manual_school_count', 0)} 条，官网观察 {stats.get('school_watch_output_count', 0)} 条，其中新增 {stats.get('school_watch_new_count', 0)} 条；风险提醒：{stats.get('manual_risk_count', 0)} 条。",
        "",
    ]
    sections = [
        ("一、必须关注", ["我的学校", "专业成长"], 3),
        ("三、专业成长", ["专业成长"], 3),
        ("四、AI与科技", ["AI与科技"], 3),
        ("五、热点与时事", ["热点与时事"], 3),
        ("六、学习成长", ["学习成长"], 3),
        ("七、资源与购物", ["资源与购物"], 3),
        ("八、生活权益", ["生活权益"], 3),
        ("九、机会观察", ["机会观察"], 3),
        ("十、文化娱乐", ["文化娱乐"], 3),
        ("十一、风险提醒", ["风险提醒"], 3),
    ]
    for title, buckets, limit in sections:
        lines.append(title)
        section_rows = [row for row in rows if intel_bucket(row) in buckets][:limit]
        if not section_rows:
            lines.append("- 暂无足够高质量条目")
        for idx, row in enumerate(section_rows, 1):
            lines.append(f"{idx}. {row['标题']}")
            lines.append(f"   关联：{row['决策影响类型']} / {row['Folo文件夹路径']}")
            lines.append(f"   建议：{row['建议行动']}")
        lines.append("")
        if title == "一、必须关注":
            append_school_section(lines, rows, 5)

    action_rows = [row for row in rows if not blocked_from_top10(row)][:3]
    lines.append("今日建议：")
    if action_rows:
        for row in action_rows:
            lines.append(f"- {row['建议行动']}")
    else:
        lines.append("- 今天只做源池观察，不急于行动。")
    lines.extend(["", f"完整表格：{xlsx_path}", "", "可继续发送：深挖1 / 今日政策 / 今日招聘 / 今日技术 / 今日AI"])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar MVP runner")
    parser.add_argument("--input", default=str(ROOT / "data" / "samples" / "folo_items_sample.csv"))
    parser.add_argument("--topic", default="样例")
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()

    ensure_dirs()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    task_id = args.task_id or f"mvp_{now_stamp()}"
    started = dt.datetime.now()
    try:
        items = read_csv_items(input_path)
        manual_items = load_manual_items.load_manual_items(args.topic)
        watch_items = load_watch_updates.load_watch_updates(args.topic)
        folo_link_items = load_folo_link_items.load_folo_link_items(args.topic)
        items.extend(manual_items)
        items.extend(watch_items)
        items.extend(folo_link_items)
        rows, stats = process_items(items, args.topic)
        stamp = now_stamp()
        safe_topic = re.sub(r"[^\w\u4e00-\u9fff]+", "_", args.topic).strip("_") or "样例"
        base_name = f"FOLO_{safe_topic}_{stamp}"
        xlsx_path = RETURN_DIR / f"{base_name}.xlsx"
        md_path = RETURN_DIR / f"{base_name}.md"
        wechat_path = RETURN_DIR / f"{base_name}_微信摘要.txt"
        csv_path = ROOT / "data" / "deduped" / f"{base_name}.csv"

        write_csv(csv_path, rows)
        write_xlsx(xlsx_path, rows)
        write_markdown(md_path, rows, stats, xlsx_path)
        write_wechat_summary(wechat_path, rows, stats, xlsx_path, args.topic)

        result = {
            "task_id": task_id,
            "success": True,
            "started": started.isoformat(),
            "ended": dt.datetime.now().isoformat(),
            "input": str(input_path),
            "xlsx": str(xlsx_path),
            "markdown": str(md_path),
            "wechat_summary": str(wechat_path),
            **stats,
        }
        log_line(ROOT / "logs" / "run.log", result)
        log_line(ROOT / "memory" / "task_history" / f"{today_text().replace('-', '')}.jsonl", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        err = {
            "task_id": task_id,
            "success": False,
            "started": started.isoformat(),
            "ended": dt.datetime.now().isoformat(),
            "input": str(input_path),
            "error": repr(exc),
        }
        log_line(ROOT / "logs" / "error.log", err)
        print(json.dumps(err, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
