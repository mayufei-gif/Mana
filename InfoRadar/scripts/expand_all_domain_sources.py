#!/usr/bin/env python3
import csv
import os
import datetime as dt
import os
import json
import os
from pathlib import Path

import all_domain_rules
import os
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
SOURCE_POOL = ROOT / "sources" / "source_pool_from_folo.csv"
PROFILE_CSV = ROOT / "sources" / "all_domain_source_profile.csv"
PROFILE_XLSX = ROOT / "sources" / "all_domain_source_profile.xlsx"
CANDIDATE_CSV = ROOT / "sources" / "all_domain_candidate_sources.csv"
CANDIDATE_XLSX = ROOT / "sources" / "all_domain_candidate_sources.xlsx"
LOG_DIR = ROOT / "logs"

PROFILE_HEADERS = [
    "源名称",
    "源状态",
    "RSS链接",
    "官网链接",
    "Folo文件夹路径",
    "source_layer",
    "platform",
    "acquisition_mode",
    "broad_category",
    "decision_scope",
    "push_frequency",
    "risk_policy",
    "paywall_policy",
    "建议动作",
    "备注",
]

CANDIDATE_HEADERS = [
    "源名称",
    "源状态",
    "候选URL",
    "RSS候选",
    "平台",
    "source_layer",
    "acquisition_mode",
    "broad_category",
    "decision_scope",
    "push_frequency",
    "risk_policy",
    "paywall_policy",
    "优先级",
    "是否一手源",
    "建议动作",
    "备注",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
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


def enrich_existing_sources() -> list[dict]:
    rows = []
    for source in read_csv(SOURCE_POOL):
        text = " ".join(
            str(source.get(key, ""))
            for key in ["源名称", "源类型", "RSS链接", "官网链接", "Folo文件夹路径", "主分类", "标签", "备注"]
        )
        domain = all_domain_rules.enrich_record(text, source.get("主分类", ""))
        rows.append(
            {
                "源名称": source.get("源名称", ""),
                "源状态": "已在Folo源池",
                "RSS链接": source.get("RSS链接", ""),
                "官网链接": source.get("官网链接", ""),
                "Folo文件夹路径": source.get("Folo文件夹路径", ""),
                "source_layer": domain["source_layer"],
                "platform": domain["platform"],
                "acquisition_mode": domain["acquisition_mode"],
                "broad_category": domain["broad_category"],
                "decision_scope": domain["decision_scope"],
                "push_frequency": domain["push_frequency"],
                "risk_policy": domain["risk_policy"],
                "paywall_policy": domain["paywall_policy"],
                "建议动作": "保留并按源池健康检查结果治理",
                "备注": "由现有 Folo 源池自动画像生成",
            }
        )
    return rows


def candidate(name: str, url: str, category: str, platform: str, acquisition: str, layer: str, priority: str, first_hand: str = "否", rss: str = "", paywall: str = "public_only", note: str = "") -> dict:
    decision = all_domain_rules.infer_decision_scope(category)
    risk_policy = all_domain_rules.infer_risk_policy(category, f"{name} {url} {note}")
    return {
        "源名称": name,
        "源状态": "候选待加入",
        "候选URL": url,
        "RSS候选": rss,
        "平台": platform,
        "source_layer": layer,
        "acquisition_mode": acquisition,
        "broad_category": category,
        "decision_scope": decision,
        "push_frequency": all_domain_rules.infer_push_frequency(layer, category),
        "risk_policy": risk_policy,
        "paywall_policy": paywall,
        "优先级": priority,
        "是否一手源": first_hand,
        "建议动作": "先人工核验质量，再加入 Folo/RSS/监控源池",
        "备注": note,
    }


def build_candidates() -> list[dict]:
    rows = [
        candidate("山西晋中理工学院官网", "https://www.sxjzit.edu.cn/", "我的学校", "学校官网", "official_page", "A_core", "最高", "是", note="学校通知、新闻、公告、赛事的一手入口"),
        candidate("山西晋中理工学院智慧就业系统", "https://jygl.sxjzit.edu.cn/", "校园招聘实习", "学校就业系统", "official_page", "A_core", "最高", "是", note="校园招聘、岗位、双选会、就业公告一手入口"),
        candidate("山西省教育厅公告通知", "https://jyt.shanxi.gov.cn/xwzx/ggtz/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("山西省人社厅", "https://rst.shanxi.gov.cn/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("山西省工信厅", "https://gxt.shanxi.gov.cn/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("中国政府网政策", "https://www.gov.cn/zhengce/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("教育部通知公告", "https://www.moe.gov.cn/jyb_xxgk/s5743/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("人社部", "https://www.mohrss.gov.cn/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("工信部", "https://www.miit.gov.cn/", "科技新闻", "政府官网", "official_page", "B_observe", "高", "是"),
        candidate("国家市场监督管理总局", "https://www.samr.gov.cn/", "法律权益", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("山西焦煤招聘入口", "https://www.sxcc.com.cn/", "就业招聘", "企业官网", "official_page", "A_core", "高", "是", note="需继续定位招聘/公告子栏目"),
        candidate("晋能控股集团", "https://www.jinnengholding.com/", "就业招聘", "企业官网", "official_page", "A_core", "高", "是", note="需继续定位招聘/公告子栏目"),
        candidate("太重集团", "https://www.tz.com.cn/", "就业招聘", "企业官网", "official_page", "A_core", "高", "是", note="需继续定位招聘/公告子栏目"),
        candidate("潞安化工集团", "https://www.chinaluan.com/", "就业招聘", "企业官网", "official_page", "A_core", "中", "是", note="需继续定位招聘/公告子栏目"),
        candidate("应急管理部特种作业", "https://www.mem.gov.cn/", "职业证书", "政府官网", "official_page", "A_core", "高", "是", note="电工证/特种作业政策需核验官方入口"),
        candidate("中国教育考试网", "https://www.neea.edu.cn/", "考试升学", "官方考试", "official_page", "A_core", "高", "是"),
        candidate("GitHub Trending", "https://github.com/trending", "开源仓库", "GitHub", "official_api", "B_observe", "高", "是"),
        candidate("GitHub Releases Atom模板", "https://github.com/{owner}/{repo}/releases.atom", "开源仓库", "GitHub", "rss", "B_observe", "高", "是", note="模板源，需替换 owner/repo"),
        candidate("OpenAI News RSS", "https://openai.com/news/rss.xml", "AI工具", "RSS", "rss", "B_observe", "高", "是", rss="https://openai.com/news/rss.xml"),
        candidate("RSSHub官方仓库", "https://github.com/DIYgod/RSSHub", "开源仓库", "GitHub", "official_api", "B_observe", "高", "是"),
        candidate("Folo官方仓库", "https://github.com/RSSNext/Folo", "开源仓库", "GitHub", "official_api", "B_observe", "高", "是"),
        candidate("Hacker News", "https://news.ycombinator.com/", "科技新闻", "RSS", "rss", "B_observe", "中", "是", rss="https://news.ycombinator.com/rss"),
        candidate("36氪", "https://36kr.com/", "科技新闻", "内容平台", "rsshub", "B_observe", "中"),
        candidate("少数派", "https://sspai.com/", "工具软件", "RSS", "rss", "C_opportunity", "中"),
        candidate("开源中国", "https://www.oschina.net/", "开源仓库", "RSSHub", "rsshub", "B_observe", "中"),
        candidate("知乎热点/收藏", "https://www.zhihu.com/", "知乎小红书微博", "知乎", "rsshub", "B_observe", "中", note="只用公开内容或手动收藏导入"),
        candidate("微博热搜", "https://s.weibo.com/top/summary", "热点新闻", "微博", "rsshub", "B_observe", "中"),
        candidate("B站技术UP主列表", "https://www.bilibili.com/", "B站YouTube", "B站", "rsshub", "B_observe", "中", note="需挑选高质量技术/学习UP主，不硬抓登录内容"),
        candidate("YouTube科技频道列表", "https://www.youtube.com/", "B站YouTube", "YouTube", "rss", "B_observe", "中", note="可用公开频道 RSS，需补频道ID"),
        candidate("微信公众号手动转发池", "manual://wechat-official-accounts", "微信公众号", "微信公众号", "manual_forward", "B_observe", "中", note="由用户转发文章链接/文本/截图，不自动硬抓"),
        candidate("视频号手动转发池", "manual://wechat-video", "视频号", "视频号", "manual_forward", "B_observe", "中", note="由用户转发链接/截图，不绕平台限制"),
        candidate("抖音热点手动线索池", "manual://douyin", "抖音快手", "抖音", "manual_forward", "B_observe", "中", note="只做公开线索/手动转发，不绕登录和反爬"),
        candidate("小红书手动线索池", "manual://xiaohongshu", "知乎小红书微博", "小红书", "manual_forward", "B_observe", "低", note="只做公开线索/手动转发"),
        candidate("淘宝购物线索池", "manual://taobao-price-watch", "消费购物", "淘宝", "price_watch", "C_opportunity", "中", paywall="metadata_only", note="只记录公开标题、价格、链接、评价线索"),
        candidate("拼多多购物线索池", "manual://pdd-price-watch", "消费购物", "拼多多", "price_watch", "C_opportunity", "中", paywall="metadata_only", note="只记录公开标题、价格、链接、评价线索"),
        candidate("京东数码装备线索池", "manual://jd-price-watch", "数码装备", "京东", "price_watch", "C_opportunity", "中", paywall="metadata_only", note="NAS硬盘、工具软件、电子设备价格观察"),
        candidate("闲鱼二手设备线索池", "manual://xianyu-watch", "数码装备", "闲鱼", "manual_import", "C_opportunity", "低", paywall="metadata_only", note="只记录公开线索，警惕诈骗"),
        candidate("付费知识公开元信息池", "manual://paid-knowledge", "付费知识", "付费知识", "paid_metadata_only", "C_opportunity", "中", paywall="metadata_only", note="只记录公开目录、价格、试看、评价，禁止破解和传播付费正文"),
        candidate("劳动权益风险池", "manual://labor-rights", "法律权益", "手动/公开搜索", "manual_import", "B_observe", "中", note="实习协议、工资、社保、劳动合同、仲裁线索"),
        candidate("虚假招聘风险池", "manual://fake-jobs", "虚假招聘", "手动/公开搜索", "manual_forward", "D_risk", "高", note="只进入风险提醒"),
        candidate("培训贷风险池", "manual://training-loan-risk", "培训贷", "手动/公开搜索", "manual_forward", "D_risk", "高", note="只进入风险提醒"),
        candidate("账号隐私风险池", "manual://privacy-risk", "账号隐私", "手动/公开搜索", "manual_forward", "D_risk", "高", note="账号封禁、隐私泄露、诈骗套路"),
        candidate("健康医学公开科普池", "manual://health-public", "健康医学", "公开网页", "manual_import", "B_observe", "低", note="只做科普线索，医疗问题需专业医生判断"),
        candidate("财经商业观察池", "manual://business-watch", "财经商业", "公开网页/RSS", "search_watch", "B_observe", "中", note="产业趋势、公司动态、消费趋势"),
        candidate("3D打印项目池", "manual://3d-printing-projects", "3D打印硬件", "公开网页/RSS", "search_watch", "C_opportunity", "中", note="项目机会、耗材、设备、作品集"),
        candidate("生活服务避坑池", "manual://life-service-risk", "生活服务", "手动/公开搜索", "manual_forward", "E_supplement", "低"),
        candidate("文化历史阅读池", "manual://culture-history", "文化历史", "RSS/手动", "manual_import", "E_supplement", "低"),
        candidate("游戏娱乐低频池", "manual://games-entertainment", "游戏娱乐", "RSS/手动", "manual_import", "E_supplement", "低"),
        candidate("山西省人民政府", "https://www.shanxi.gov.cn/", "本地山西", "政府官网", "official_page", "A_core", "高", "是", note="山西本地政策、民生、产业和政务入口"),
        candidate("太原市人民政府", "https://www.taiyuan.gov.cn/", "本地山西", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("晋中市人民政府", "https://www.sxjz.gov.cn/", "本地山西", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("长治市人民政府", "https://www.changzhi.gov.cn/", "本地山西", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("人民网时政频道RSS", "http://www.people.com.cn/rss/politics.xml", "时事政治", "RSS", "rss", "B_observe", "高", "是", rss="http://www.people.com.cn/rss/politics.xml"),
        candidate("人民网国际频道RSS", "http://www.people.com.cn/rss/world.xml", "国际观察", "RSS", "rss", "B_observe", "中", "是", rss="http://www.people.com.cn/rss/world.xml"),
        candidate("新华网", "https://www.news.cn/", "热点新闻", "公开网页/RSS", "search_watch", "B_observe", "高", "是"),
        candidate("央视新闻", "https://news.cctv.com/", "热点新闻", "公开网页/RSS", "search_watch", "B_observe", "高", "是"),
        candidate("联合国新闻", "https://news.un.org/zh/", "国际观察", "公开网页/RSS", "search_watch", "B_observe", "中", "是"),
        candidate("国家法律法规数据库", "https://flk.npc.gov.cn/", "法律权益", "政府官网", "official_page", "B_observe", "高", "是", note="法律条文和政策核验入口"),
        candidate("中国裁判文书网公开检索入口", "https://wenshu.court.gov.cn/", "法律权益", "公开网页", "official_page", "B_observe", "低", "是", note="仅作为公开入口记录，不自动批量抓取"),
        candidate("12315消费者权益入口", "https://www.12315.cn/", "法律权益", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("国家卫健委", "https://www.nhc.gov.cn/", "健康医学", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("中国疾控中心", "https://www.chinacdc.cn/", "健康医学", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("丁香园公开科普线索池", "manual://dxy-public-health", "健康医学", "公开网页/手动", "manual_import", "B_observe", "低", note="只做公开科普线索，不替代医生诊断"),
        candidate("国家统计局", "https://www.stats.gov.cn/", "财经商业", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("中国人民银行", "https://www.pbc.gov.cn/", "财经商业", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("证监会", "https://www.csrc.gov.cn/", "财经商业", "政府官网", "official_page", "B_observe", "中", "是"),
        candidate("国家发改委", "https://www.ndrc.gov.cn/", "政策风向", "政府官网", "official_page", "A_core", "高", "是"),
        candidate("国家能源局", "https://www.nea.gov.cn/", "工业技术", "政府官网", "official_page", "B_observe", "中", "是", note="能源、电力、煤炭和新型能源体系相关"),
        candidate("国家网络安全通报中心", "https://www.cert.org.cn/", "网络安全", "政府/行业官网", "official_page", "B_observe", "中", "是"),
        candidate("CVE公开漏洞库", "https://www.cve.org/", "网络安全", "公开网页/RSS", "search_watch", "B_observe", "中", "是"),
        candidate("Microsoft安全更新指南", "https://msrc.microsoft.com/update-guide", "网络安全", "公开网页", "official_page", "B_observe", "中", "是"),
        candidate("中国大学MOOC公开课程线索池", "manual://icourse-public", "学习资源", "公开网页/手动", "manual_import", "B_observe", "中", note="只记录公开课程目录和学习线索"),
        candidate("Coursera公开目录线索池", "manual://coursera-public-catalog", "课程资源", "公开网页/手动", "manual_import", "C_opportunity", "低", paywall="metadata_only", note="只记录公开目录、价格、试看，不抓付费课程正文"),
        candidate("B站学习UP主池", "manual://bilibili-study-creators", "B站YouTube", "B站", "manual_import", "B_observe", "中", note="人工挑选高质量学习/技术UP主，再用公开RSS或RSSHub"),
        candidate("YouTube公开课程频道池", "manual://youtube-learning-channels", "B站YouTube", "YouTube", "manual_import", "B_observe", "中", note="补充频道ID后可用公开视频RSS"),
        candidate("RSSHub路由候选池", "https://docs.rsshub.app/", "开源仓库", "RSSHub", "rsshub", "B_observe", "中", "是", note="用于后续为平台源寻找合规公开RSSHub路由"),
        candidate("GitHub Topic AI", "https://github.com/topics/artificial-intelligence", "开源仓库", "GitHub", "official_api", "B_observe", "中", "是"),
        candidate("GitHub Topic Automation", "https://github.com/topics/automation", "开源仓库", "GitHub", "official_api", "B_observe", "中", "是"),
        candidate("GitHub Topic PLC", "https://github.com/topics/plc", "工业技术", "GitHub", "official_api", "B_observe", "低", "是"),
        candidate("NAS与远程控制公开项目池", "manual://nas-remote-projects", "NAS自动化", "公开网页/RSS", "search_watch", "C_opportunity", "中", note="Tailscale、RustDesk、Docker、NAS自动化项目观察"),
        candidate("什么值得买公开线索池", "manual://smzdm-public", "消费购物", "公开网页/手动", "manual_import", "C_opportunity", "低", paywall="metadata_only", note="只记录公开价格和评价线索"),
        candidate("1688工业耗材线索池", "manual://1688-industrial-supplies", "消费购物", "公开网页/手动", "manual_import", "C_opportunity", "低", paywall="metadata_only", note="电气工具、耗材和3D打印耗材价格观察"),
        candidate("租房与生活服务线索池", "manual://rent-life-service", "住房租房", "公开网页/手动", "manual_import", "E_supplement", "低", paywall="metadata_only", note="只记录公开房源线索和避坑信息，不抓个人隐私"),
        candidate("铁路12306公告", "https://www.12306.cn/", "交通出行", "官方网页", "official_page", "E_supplement", "低", "是"),
        candidate("中国天气公开入口", "https://www.weather.com.cn/", "生活服务", "公开网页", "official_page", "E_supplement", "低", "是"),
        candidate("国家博物馆", "https://www.chnmuseum.cn/", "文化历史", "公开网页", "official_page", "E_supplement", "低", "是"),
        candidate("豆瓣读书影视手动线索池", "manual://douban-books-movies", "读书影视", "手动/公开搜索", "manual_import", "E_supplement", "低", note="只做公开条目线索，不抓账号内容"),
        candidate("Steam愿望单手动线索池", "manual://steam-watch", "游戏娱乐", "手动/公开搜索", "manual_import", "E_supplement", "低", paywall="metadata_only", note="只记录公开价格和评测线索"),
        candidate("体育赛事低频线索池", "manual://sports-events", "体育赛事", "公开网页/RSS", "search_watch", "E_supplement", "低"),
    ]
    return rows


def count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = row.get(key, "") or "未标记"
        out[value] = out.get(value, 0) + 1
    return out


def write_report(path: Path, profile_rows: list[dict], candidate_rows: list[dict]) -> None:
    combined = profile_rows + candidate_rows
    by_layer = count_by(combined, "source_layer")
    by_category = count_by(combined, "broad_category")
    by_acquisition = count_by(combined, "acquisition_mode")
    school_count = sum(1 for row in combined if row.get("broad_category") in {"我的学校", "学校通知", "校园招聘实习", "教务学业"})
    github_count = sum(1 for row in combined if row.get("platform") == "GitHub" or row.get("broad_category") == "开源仓库")
    platform_count = sum(1 for row in combined if row.get("broad_category") in {"微信公众号", "视频号", "抖音快手", "B站YouTube", "知乎小红书微博", "内容平台"})
    shopping_paid_count = sum(1 for row in combined if row.get("broad_category") in {"消费购物", "数码装备", "工具软件", "付费知识", "课程资源"})
    risk_count = sum(1 for row in combined if row.get("source_layer") == "D_risk" or "risk" in row.get("risk_policy", ""))
    forbidden_count = sum(1 for row in combined if row.get("paywall_policy") not in {"public_only", "metadata_only", "paid_owned_only", "forbidden_bypass"})
    lines = [
        "# InfoRadar MVP-2.5B 全域源池扩展报告",
        "",
        f"生成时间：{now_text()}",
        "",
        "## 总览",
        "",
        f"- 现有源画像数量：{len(profile_rows)}",
        f"- 新增候选源数量：{len(candidate_rows)}",
        f"- 全域源/候选总数：{len(combined)}",
        f"- 学校一手/学校相关源数量：{school_count}",
        f"- 开源仓库/GitHub源数量：{github_count}",
        f"- 平台内容源数量：{platform_count}",
        f"- 购物/付费资源源数量：{shopping_paid_count}",
        f"- 风险源数量：{risk_count}",
        f"- 异常付费边界数量：{forbidden_count}",
        "",
        "## source_layer 分布",
        "",
        "| source_layer | 数量 |",
        "|---|---:|",
    ]
    for key, value in sorted(by_layer.items(), key=lambda kv: kv[0]):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## broad_category 分布", "", "| broad_category | 数量 |", "|---|---:|"])
    for key, value in sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## acquisition_mode 分布", "", "| acquisition_mode | 数量 |", "|---|---:|"])
    for key, value in sorted(by_acquisition.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## 采集边界",
            "",
            "- 允许：公开 RSS/Atom、公开网页、官方公告、公开 API、RSSHub 合规公开路由、用户手动转发/导入内容。",
            "- 不允许：绕过登录、验证码、付费墙、访问控制、平台反爬、抓取会员课程正文、传播盗版破解资源。",
            "- 购物平台只记录公开标题、价格、链接、评价线索；付费知识只记录公开目录、价格、试看和评价。",
            "",
            "## 当前判断",
            "",
            "- 全域分类已覆盖学校、政策、新闻、科技、开源、内容平台、购物、付费资源、法律、健康、财经、生活、娱乐、风险等方向。",
            "- 当前仍是候选源扩展，不等于全部已加入 Folo；下一步应按优先级人工核验后逐步导入。",
            "- 今日情报已具备全域栏目结构，后续需要真实源池补齐每栏内容。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ROOT.joinpath("sources").mkdir(parents=True, exist_ok=True)
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    profile_rows = enrich_existing_sources()
    candidate_rows = build_candidates()
    write_csv(PROFILE_CSV, PROFILE_HEADERS, profile_rows)
    write_xlsx(PROFILE_XLSX, PROFILE_HEADERS, profile_rows, sheet_name="全域源池画像")
    write_csv(CANDIDATE_CSV, CANDIDATE_HEADERS, candidate_rows)
    write_xlsx(CANDIDATE_XLSX, CANDIDATE_HEADERS, candidate_rows, sheet_name="全域候选源")
    report = RETURN_DIR / f"InfoRadar_MVP2_5B_全域源池扩展报告_{today_stamp()}.md"
    write_report(report, profile_rows, candidate_rows)
    result = {
        "success": True,
        "profile_count": len(profile_rows),
        "candidate_count": len(candidate_rows),
        "report": str(report),
        "profile_csv": str(PROFILE_CSV),
        "profile_xlsx": str(PROFILE_XLSX),
        "candidate_csv": str(CANDIDATE_CSV),
        "candidate_xlsx": str(CANDIDATE_XLSX),
        "output_files": [str(report), str(PROFILE_CSV), str(PROFILE_XLSX), str(CANDIDATE_CSV), str(CANDIDATE_XLSX)],
    }
    append_jsonl(LOG_DIR / "run.log", {"task": "expand_all_domain_sources", **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
