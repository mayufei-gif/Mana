#!/usr/bin/env python3
from __future__ import annotations

import re


BROAD_CATEGORIES = [
    "我的学校",
    "学校通知",
    "教务学业",
    "学工团委",
    "奖助评优",
    "入团竞选",
    "创新创业竞赛",
    "校园招聘实习",
    "毕业档案",
    "时事政治",
    "热点新闻",
    "政策风向",
    "本地山西",
    "国际观察",
    "法律权益",
    "就业招聘",
    "职业证书",
    "工业技术",
    "电气自动化",
    "PLC变频器",
    "工业机器人",
    "CAD_EPLAN",
    "AI工具",
    "科技新闻",
    "开源仓库",
    "编程开发",
    "网络安全",
    "NAS自动化",
    "3D打印硬件",
    "学习资源",
    "考试升学",
    "语言学习",
    "论文文档",
    "财经商业",
    "投资理财",
    "消费购物",
    "数码装备",
    "工具软件",
    "付费知识",
    "课程资源",
    "内容平台",
    "微信公众号",
    "视频号",
    "抖音快手",
    "B站YouTube",
    "知乎小红书微博",
    "个人项目",
    "机会观察",
    "副业观察",
    "创业扶持",
    "健康医学",
    "心理成长",
    "生活服务",
    "交通出行",
    "住房租房",
    "文化历史",
    "读书影视",
    "游戏娱乐",
    "体育赛事",
    "风险避坑",
    "诈骗灰产",
    "虚假招聘",
    "培训贷",
    "账号隐私",
    "盗版破解风险",
]

TOPIC_KEYWORDS = {
    "我的学校": ["山西晋中理工", "晋中理工", "sxjzit", "jygl.sxjzit"],
    "学校通知": ["山西晋中理工", "晋中理工", "教务", "学工", "团委", "奖助", "评优", "毕业", "实习实践"],
    "本地山西": ["山西", "太原", "晋中", "长治", "忻州", "大同", "临汾", "运城", "吕梁", "阳泉", "朔州", "晋城"],
    "时事热点": ["时事", "新闻", "热点", "新华网", "人民网", "央视", "环球网", "中新网", "BBC", "Wikipedia", "热搜"],
    "国际观察": ["国际", "外交", "全球", "美国", "欧盟", "日本", "韩国", "俄罗斯", "东盟", "联合国", "BBC", "Reuters"],
    "科技前沿": ["科技", "AI", "大模型", "芯片", "机器人", "自动驾驶", "量子", "航天", "OpenAI", "Claude", "模型", "Agent"],
    "开源动态": ["GitHub", "开源", "release", "releases", "仓库", "版本", "项目", "工具", "developer", "dev"],
    "网络安全": ["网络安全", "漏洞", "CVE", "补丁", "安全公告", "隐私", "数据泄露", "钓鱼", "恶意软件"],
    "购物情报": ["淘宝", "拼多多", "京东", "闲鱼", "1688", "价格", "优惠", "数码", "装备", "耗材", "工具", "硬盘", "万用表", "示波器", "电烙铁"],
    "数码装备": ["数码", "电脑", "手机", "硬盘", "NAS硬盘", "路由器", "平板", "显示器", "万用表", "示波器", "电烙铁"],
    "工具软件": ["软件", "工具", "效率", "自动化", "Windows", "macOS", "Android", "插件", "扩展"],
    "付费资源": ["付费", "课程", "专栏", "知识星球", "网课", "训练营", "会员", "试看", "目录", "价格", "评价"],
    "风险提醒": ["诈骗", "灰产", "培训贷", "虚假招聘", "破解版", "学习版", "注册机", "免激活", "盗版", "隐私泄露", "封号", "合同陷阱", "刷单"],
    "风险避坑": ["避坑", "诈骗", "套路", "黑产", "灰产", "封号", "隐私泄露", "虚假招聘", "培训贷"],
    "虚假招聘": ["虚假招聘", "招聘骗局", "收费内推", "培训贷", "押金", "入职收费"],
    "培训贷": ["培训贷", "贷款培训", "先学后付", "分期培训", "就业保障班"],
    "账号隐私": ["隐私", "账号", "封号", "泄露", "钓鱼", "验证码", "数据安全"],
    "法律权益": ["劳动法", "合同", "仲裁", "社保", "工资", "实习协议", "权益", "隐私", "消费者权益"],
    "健康医学": ["健康", "医学", "疾病", "睡眠", "心理", "运动", "营养", "医院", "医保"],
    "财经商业": ["财经", "商业", "产业", "公司", "市场", "消费", "金融", "投资", "创业", "价格"],
    "学习资源": ["学习", "教程", "资料", "考试", "升学", "英语", "数学", "论文", "文档", "课程"],
    "3D打印硬件": ["3D打印", "建模", "耗材", "树脂", "切片", "创客", "硬件"],
    "生活服务": ["租房", "交通", "医保", "社保", "公积金", "天气", "12306", "本地服务", "办事"],
    "文化历史": ["历史", "文化", "读书", "出版", "博物馆", "人文", "考古"],
    "读书影视": ["读书", "电影", "影视", "剧集", "纪录片", "影评", "书评"],
    "游戏娱乐": ["游戏", "娱乐", "音乐", "演出", "Steam", "主机", "手游"],
    "体育赛事": ["体育", "赛事", "足球", "篮球", "NBA", "CBA", "中超", "世界杯", "奥运"],
    "全域情报": [],
}

COMMAND_TOPIC_ALIASES = {
    "我的学校": "我的学校",
    "学校通知": "学校通知",
    "本地山西": "本地山西",
    "时事热点": "时事热点",
    "国际观察": "国际观察",
    "科技前沿": "科技前沿",
    "开源动态": "开源动态",
    "网络安全": "网络安全",
    "购物情报": "购物情报",
    "数码装备": "数码装备",
    "工具软件": "工具软件",
    "付费资源": "付费资源",
    "风险提醒": "风险提醒",
    "风险避坑": "风险避坑",
    "虚假招聘": "虚假招聘",
    "培训贷": "培训贷",
    "账号隐私": "账号隐私",
    "法律权益": "法律权益",
    "健康医学": "健康医学",
    "财经商业": "财经商业",
    "学习资源": "学习资源",
    "3D打印硬件": "3D打印硬件",
    "生活服务": "生活服务",
    "文化历史": "文化历史",
    "读书影视": "读书影视",
    "游戏娱乐": "游戏娱乐",
    "体育赛事": "体育赛事",
    "全域情报": "全域情报",
}

MY_SCHOOL_TERMS = ["山西晋中理工", "晋中理工", "sxjzit", "jygl.sxjzit"]
SCHOOL_NOTICE_TERMS = ["教务", "学工", "团委", "奖学金", "助学金", "入团", "评优", "竞赛", "校园招聘", "实习实践", "毕业"]
POLICY_TERMS = ["政策", "政府", "人社", "教育", "工信", "通知", "公告", "规划", "意见", "办法", "补贴", "国务院", "山西省"]
JOB_TERMS = ["招聘", "岗位", "校招", "实习", "就业", "投递", "简历", "面试", "山西焦煤", "霍州煤电", "晋能控股", "太重", "潞安"]
CERT_TERMS = ["证书", "电工证", "低压电工", "高压电工", "职业技能", "技能等级", "计算机等级", "CAD证书", "考试报名", "补贴"]
INDUSTRIAL_TERMS = [
    "PLC",
    "变频器",
    "ACS800",
    "ACS880",
    "电气",
    "自动化",
    "工业机器人",
    "AutoCAD",
    "EPLAN",
    "控制柜",
    "矿用设备",
    "电路板",
    "电路",
    "电流",
    "电压",
    "电阻",
    "电功率",
    "电路模型",
]
AI_TECH_TERMS = ["AI", "OpenAI", "ChatGPT", "Codex", "Folo", "RSSHub", "OpenClaw", "GitHub", "大模型", "Agent", "API", "开源", "科技"]
HOT_TERMS = ["时事", "新闻", "热点", "热搜", "央视", "新华网", "人民网", "中新网", "环球网", "BBC", "Wikipedia"]
LOCAL_TERMS = ["山西", "太原", "晋中", "长治", "忻州", "大同", "临汾", "运城", "吕梁", "阳泉", "朔州", "晋城"]
INTERNATIONAL_TERMS = ["国际", "外交", "全球", "美国", "欧盟", "日本", "韩国", "俄罗斯", "东盟", "联合国", "BBC", "Reuters"]
SHOPPING_TERMS = ["淘宝", "拼多多", "京东", "闲鱼", "1688", "价格", "优惠", "数码", "耗材", "硬盘", "万用表", "电烙铁", "示波器"]
PAID_TERMS = ["付费", "课程", "专栏", "知识星球", "网课", "训练营", "会员", "试看", "目录", "价格"]
OPPORTUNITY_TERMS = ["机会", "项目", "竞赛", "创业", "扶持", "补贴", "低成本", "3D打印", "小程序", "接单"]
RISK_TERMS = ["诈骗", "灰产", "培训贷", "虚假招聘", "破解版", "学习版", "注册机", "免激活", "盗版", "隐私泄露", "封号", "刷单", "合同陷阱"]
LEGAL_TERMS = ["法律", "劳动法", "劳动", "合同", "仲裁", "社保", "工资", "实习协议", "权益", "消费者权益", "12315"]
HEALTH_TERMS = ["健康", "医学", "疾病", "睡眠", "心理", "运动", "营养", "医院", "医保", "疾控"]
FINANCE_TERMS = ["财经", "金融", "投资", "商业", "市场", "产业", "公司", "消费", "统计局", "央行", "证监会"]
LEARNING_TERMS = ["学习", "教程", "考试", "升学", "英语", "数学", "论文", "文档", "课程", "资料"]
SECURITY_TERMS = ["网络安全", "漏洞", "CVE", "补丁", "安全公告", "钓鱼", "恶意软件", "数据泄露"]
TOOL_SOFTWARE_TERMS = ["Windows", "macOS", "Android", "软件", "插件", "扩展", "自动点击", "图片识别", "坐标点击", "效率工具", "客户端"]
LIFE_TERMS = ["租房", "出行", "医保", "社保", "公积金", "天气", "12306", "本地服务", "办事", "住房", "铁路"]
CULTURE_TERMS = ["历史", "文化", "读书", "出版", "博物馆", "人文", "考古", "电影", "影视", "纪录片"]
SPORTS_TERMS = ["体育", "赛事", "足球", "篮球", "NBA", "CBA", "中超", "世界杯", "奥运"]

PLATFORM_RULES = [
    ("GitHub", ["github.com", "GitHub"], "official_api", "public_only"),
    ("YouTube", ["youtube.com", "youtu.be", "YouTube"], "rss", "public_only"),
    ("B站", ["bilibili.com", "bilibili", "b站", "哔哩"], "rsshub", "public_only"),
    ("微信公众号", ["公众号", "mp.weixin.qq.com"], "manual_forward", "public_only"),
    ("视频号", ["视频号"], "manual_forward", "public_only"),
    ("抖音", ["douyin.com", "抖音"], "manual_forward", "public_only"),
    ("快手", ["kuaishou.com", "快手"], "manual_forward", "public_only"),
    ("知乎", ["zhihu.com", "知乎"], "rsshub", "public_only"),
    ("小红书", ["xiaohongshu.com", "小红书"], "manual_forward", "public_only"),
    ("微博", ["weibo.com", "微博"], "rsshub", "public_only"),
    ("淘宝", ["taobao.com", "淘宝"], "price_watch", "metadata_only"),
    ("拼多多", ["pinduoduo.com", "拼多多"], "price_watch", "metadata_only"),
    ("京东", ["jd.com", "京东"], "price_watch", "metadata_only"),
    ("闲鱼", ["goofish.com", "闲鱼"], "manual_import", "metadata_only"),
    ("付费知识", PAID_TERMS, "paid_metadata_only", "metadata_only"),
    ("RSSHub", ["rsshub://", "rsshub.app", "rsshub"], "rsshub", "public_only"),
    ("Folo/RSS", ["rss", "atom", "feed"], "rss", "public_only"),
]


def contains_any(text: str, words: list[str]) -> bool:
    lower = (text or "").lower()
    for word in words:
        if not word:
            continue
        if re.fullmatch(r"[A-Za-z0-9+#.]{1,4}", word):
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text or "", re.I):
                return True
        elif word.lower() in lower:
            return True
    return False


def infer_platform(text: str) -> tuple[str, str, str]:
    for platform, words, acquisition, paywall in PLATFORM_RULES:
        if contains_any(text, words):
            return platform, acquisition, paywall
    return "公开网页/RSS", "rss", "public_only"


def infer_broad_category(text: str, main_category: str = "") -> str:
    raw = text or ""
    hay = f"{main_category} {raw}"
    if contains_any(raw, MY_SCHOOL_TERMS):
        if contains_any(raw, ["招聘", "就业", "岗位", "宣讲会", "双选会"]):
            return "校园招聘实习"
        return "我的学校"
    if contains_any(raw, RISK_TERMS):
        if contains_any(raw, ["破解版", "学习版", "注册机", "免激活", "盗版"]):
            return "盗版破解风险"
        if contains_any(raw, ["虚假招聘", "招聘"]):
            return "虚假招聘"
        if contains_any(raw, ["培训贷"]):
            return "培训贷"
        return "风险避坑"
    if contains_any(raw, JOB_TERMS):
        return "就业招聘"
    if contains_any(raw, CERT_TERMS):
        return "职业证书"
    if contains_any(raw, AI_TECH_TERMS) or main_category in {"AI工具", "NAS与远程控制"}:
        if contains_any(raw, ["GitHub", "开源", "release", "仓库"]):
            return "开源仓库"
        return "AI工具"
    if contains_any(raw, INDUSTRIAL_TERMS):
        if contains_any(raw, ["PLC", "变频器", "ACS800", "ACS880"]):
            return "PLC变频器"
        if contains_any(raw, ["机器人"]):
            return "工业机器人"
        return "工业技术"
    if main_category in {"国家政策", "地方政策", "技能补贴"} or contains_any(raw, POLICY_TERMS):
        return "政策风向"
    if contains_any(raw, SECURITY_TERMS):
        return "网络安全"
    if contains_any(raw, LOCAL_TERMS):
        return "本地山西"
    if contains_any(raw, INTERNATIONAL_TERMS):
        return "国际观察"
    if contains_any(raw, LEGAL_TERMS):
        return "法律权益"
    if contains_any(raw, HEALTH_TERMS):
        return "健康医学"
    if contains_any(raw, FINANCE_TERMS):
        return "财经商业"
    if contains_any(raw, LEARNING_TERMS):
        return "学习资源"
    if contains_any(raw, HOT_TERMS) or main_category == "新闻时政":
        return "热点新闻"
    if contains_any(raw, SHOPPING_TERMS):
        return "消费购物"
    if contains_any(raw, TOOL_SOFTWARE_TERMS):
        return "工具软件"
    if contains_any(raw, PAID_TERMS):
        return "付费知识"
    if contains_any(raw, OPPORTUNITY_TERMS):
        return "机会观察"
    if contains_any(raw, LIFE_TERMS):
        return "生活服务"
    if contains_any(raw, CULTURE_TERMS):
        if contains_any(raw, ["电影", "影视", "纪录片"]):
            return "读书影视"
        return "文化历史"
    if contains_any(raw, SPORTS_TERMS):
        return "体育赛事"
    if contains_any(raw, ["游戏", "影视", "娱乐", "音乐", "体育"]):
        return "游戏娱乐"
    return "内容平台"


def infer_source_layer(broad_category: str, text: str = "") -> str:
    if broad_category in {"我的学校", "学校通知", "教务学业", "校园招聘实习", "毕业档案", "就业招聘", "职业证书", "工业技术", "电气自动化", "PLC变频器", "政策风向", "本地山西"}:
        return "A_core"
    if broad_category in {"时事政治", "热点新闻", "科技新闻", "AI工具", "开源仓库", "法律权益", "健康医学", "财经商业", "学习资源", "国际观察", "网络安全"}:
        return "B_observe"
    if broad_category in {"消费购物", "数码装备", "工具软件", "付费知识", "个人项目", "机会观察", "副业观察", "创业扶持", "3D打印硬件"}:
        return "C_opportunity"
    if broad_category in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}:
        return "D_risk"
    return "E_supplement"


def infer_decision_scope(broad_category: str) -> str:
    if broad_category in {"我的学校", "学校通知", "教务学业", "校园招聘实习", "毕业档案"}:
        return "学校行动"
    if broad_category in {"就业招聘", "职业证书", "工业技术", "电气自动化", "PLC变频器", "工业机器人", "CAD_EPLAN"}:
        return "职业成长"
    if broad_category in {"政策风向", "时事政治", "热点新闻", "本地山西", "国际观察"}:
        return "环境判断"
    if broad_category in {"AI工具", "科技新闻", "开源仓库", "编程开发", "NAS自动化"}:
        return "工具/技术选择"
    if broad_category in {"消费购物", "数码装备", "工具软件", "付费知识", "课程资源"}:
        return "购买/学习决策"
    if broad_category in {"学习资源", "考试升学", "语言学习", "论文文档"}:
        return "学习成长"
    if broad_category in {"法律权益", "健康医学", "心理成长", "生活服务", "交通出行", "住房租房", "投资理财"}:
        return "生活权益"
    if broad_category in {"文化历史", "读书影视", "游戏娱乐", "体育赛事"}:
        return "文化娱乐"
    if broad_category in {"个人项目", "机会观察", "副业观察", "创业扶持"}:
        return "机会探索"
    if broad_category in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}:
        return "风险规避"
    return "长期观察"


def infer_push_frequency(source_layer: str, broad_category: str) -> str:
    if source_layer == "A_core":
        return "daily"
    if source_layer == "B_observe":
        return "daily_or_weekly"
    if source_layer == "C_opportunity":
        return "weekly"
    if source_layer == "D_risk":
        return "on_trigger"
    return "low_frequency"


def infer_risk_policy(broad_category: str, text: str = "") -> str:
    if broad_category in {"盗版破解风险", "诈骗灰产", "培训贷", "账号隐私", "虚假招聘"} or contains_any(text, RISK_TERMS):
        return "risk_only_no_opportunity"
    if broad_category in {"付费知识", "消费购物"}:
        return "metadata_public_only"
    return "normal"


def daily_intel_section(broad_category: str) -> str:
    if broad_category in {"我的学校", "学校通知", "教务学业", "学工团委", "奖助评优", "入团竞选", "创新创业竞赛", "校园招聘实习", "毕业档案"}:
        return "我的学校"
    if broad_category in {"就业招聘", "职业证书", "工业技术", "电气自动化", "PLC变频器", "工业机器人", "CAD_EPLAN"}:
        return "专业成长"
    if broad_category in {"AI工具", "科技新闻", "开源仓库", "编程开发", "网络安全", "NAS自动化", "3D打印硬件"}:
        return "AI与科技"
    if broad_category in {"时事政治", "热点新闻", "政策风向", "本地山西", "国际观察", "法律权益", "财经商业"}:
        return "热点与时事"
    if broad_category in {"消费购物", "数码装备", "工具软件", "付费知识", "课程资源"}:
        return "资源与购物"
    if broad_category in {"学习资源", "考试升学", "语言学习", "论文文档"}:
        return "学习成长"
    if broad_category in {"法律权益", "健康医学", "心理成长", "生活服务", "交通出行", "住房租房", "投资理财"}:
        return "生活权益"
    if broad_category in {"文化历史", "读书影视", "游戏娱乐", "体育赛事"}:
        return "文化娱乐"
    if broad_category in {"个人项目", "机会观察", "副业观察", "创业扶持"}:
        return "机会观察"
    if broad_category in {"风险避坑", "诈骗灰产", "虚假招聘", "培训贷", "账号隐私", "盗版破解风险"}:
        return "风险提醒"
    return "热点与时事"


def enrich_record(text: str, main_category: str = "") -> dict:
    platform, acquisition_mode, paywall_policy = infer_platform(text)
    broad_category = infer_broad_category(text, main_category)
    source_layer = infer_source_layer(broad_category, text)
    return {
        "source_layer": source_layer,
        "platform": platform,
        "acquisition_mode": acquisition_mode,
        "broad_category": broad_category,
        "decision_scope": infer_decision_scope(broad_category),
        "push_frequency": infer_push_frequency(source_layer, broad_category),
        "risk_policy": infer_risk_policy(broad_category, text),
        "paywall_policy": paywall_policy,
        "daily_section": daily_intel_section(broad_category),
    }
