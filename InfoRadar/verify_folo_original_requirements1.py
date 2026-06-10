from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8", errors="replace")
JS = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8", errors="replace")
CSS = (ROOT / "web" / "frontend" / "style.css").read_text(encoding="utf-8", errors="replace")
BACKEND = (ROOT / "web" / "backend" / "app.py").read_text(encoding="utf-8", errors="replace")
FILE_INDEX = (ROOT / "web" / "backend" / "file_index.py").read_text(encoding="utf-8", errors="replace")


def require(item: str, title: str, red: str, green: str, passed: bool) -> None:
    print(f"{item} {title}")
    print(f"  RED: {red}")
    print(f"  GREEN: {green}")
    if not passed:
        raise AssertionError(f"{item} 未通过：{title}")
    print(f"  RESULT: GREEN\n")


def contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def main() -> None:
    require(
        "1.1",
        "个人雷达检索改为 Folo 巢式检索",
        "页面仍出现“个人雷达检索”，或检索入口消失。",
        "页面标题为“Folo 巢式检索”，且保留 radarSearchInput/radarSearchBtn。",
        "Folo 巢式检索" in HTML and "个人雷达检索" not in HTML and contains_all(HTML, ["radarSearchInput", "radarSearchBtn"]),
    )
    require(
        "1.2",
        "今日雷达改为带巡检区间的信息寻缘情况",
        "页面仍显示“今日雷达”，或没有巡检区间字段。",
        "页面显示“信息寻缘情况”，并由 inspection_interval_label / inspectionIntervalLabel 驱动区间。",
        "今日雷达" not in HTML and "信息寻缘情况" in HTML and "inspectionIntervalLabel" in HTML and "inspection_interval_label" in FILE_INDEX and "inspectionIntervalLabel" in JS,
    )
    require(
        "1.3",
        "情报卡片改为区间搜集卡片且数量不虚标",
        "页面仍显示“情报卡片”，或 intelCount 统计全部卡片。",
        "页面显示“区间搜集卡片”，intelCount 使用 jumpReadyCount，jumpReadyCount 由 isFoloJumpReady 过滤。",
        "情报卡片" not in HTML and "区间搜集卡片" in HTML and "jumpReadyCount = rows.filter(isFoloJumpReady).length" in JS and "intelCount.textContent = String(state.currentHiveMetrics.jumpReadyCount)" in JS,
    )
    require(
        "1.4",
        "回传文件改为新增信息且表示本区间新鲜信息总量",
        "页面仍显示“回传文件”，或 fileCount 仍统计文件数量。",
        "页面显示“新增信息”，fileCount 使用 currentHiveMetrics.totalNew，totalNew 来自当前信息池 rows.length。",
        "回传文件" not in HTML and "新增信息" in HTML and "totalNew: rows.length" in JS and "fileCount.textContent = String(state.currentHiveMetrics.totalNew)" in JS,
    )
    require(
        "1.5",
        "Folo 寻源时间线、三次星标晋升和颜色阶梯",
        "没有时间线/星标列表，点击 Folo 源列表不记录，或三次点击不晋升。",
        "页面有 foloSourceTimeline/starCardList；JS 记录点击并 count>=3 晋升；CSS 有紫青靛蓝绿黄橙红 tone。",
        contains_all(HTML, ["Folo 寻源时间线 / 星标列表", "foloSourceTimeline", "starCardList"])
        and contains_all(JS, ["recordFoloSourceClick", "syncFoloSourceClick", "count >= 3", "foloToneClass"])
        and contains_all(CSS, ["tone-violet", "tone-cyan", "tone-indigo", "tone-blue", "tone-green", "tone-yellow", "tone-orange", "tone-red"]),
    )
    require(
        "1.6",
        "收集线索改为热点候选算法入口",
        "页面仍显示“收集线索”，或没有热点算法。",
        "页面显示“热点候选”，inboxCount 使用 hotCount，hotCount 来自 hotspotSignal/isHotPotential。",
        "收集线索" not in HTML and "热点候选" in HTML and "hotspotSignal" in JS and "isHotPotential" in JS and "inboxCount.textContent = String(state.currentHiveMetrics.hotCount)" in JS,
    )
    require(
        "1.7",
        "全网资源鉴赏",
        "没有全网资源鉴赏 UI，或没有发现/入池/导出/NAS 归档接口。",
        "页面有全网资源鉴赏和 resourceHive 控件，后端有 discover/export/archive/download 接口。",
        contains_all(HTML, ["全网资源鉴赏", "resourceHiveQuery", "resourceHiveDiscoverBtn", "resourceHiveBatchAutoAddBtn", "导出 MD", "导出 JSONL"])
        and contains_all(BACKEND, ["/api/resource-hive/discover", "/api/resource-hive/export", "/api/resource-hive/archive-plan", "/api/resource-hive/download-approved"]),
    )
    require(
        "1.8",
        "Folo 巢式检索运行状态 UI 重设计",
        "仍出现上次运行/每日自动化/RSS源/映射库/构建时间等旧状态口径。",
        "运行状态使用今日全网检索、Folo 直查源成功、Folo源条ID、库存总条目、完成时间、总体积和每日四次自动更新口径。",
        contains_all(JS, ["今日全网检索", "Folo 直查源成功", "Folo源条ID", "现库存总条目", "完成时间", "总体积", "用户级 crontab 每天自动更新四遍 InfoRadar"])
        and not any(old in HTML for old in ["上次运行", "每日自动化", "RSS源", "映射库", "构建时间"]),
    )
    require(
        "2.1",
        "常用动作改为手动信息获取站",
        "页面仍显示“常用动作”，或没有平台下拉、名称搜索、URL 搜索、加入信息寻缘。",
        "页面显示“手动信息获取站”，支持公众号/快手/抖音/B站/Twitch/YouTube/TED，具备名称检索、URL 检索和加入信息寻缘。",
        "常用动作" not in HTML
        and contains_all(HTML, ["手动信息获取站", "manualHivePlatform", "公众号", "快手", "抖音", "B站", "Twitch", "YouTube", "TED", "manualHiveName", "manualHiveUrl", "manualHiveSearchNameBtn", "manualHiveSearchUrlBtn", "manualHiveAddBtn"])
        and contains_all(JS, ["openManualHiveSearch", "platformSearchUrl", "syncManualHiveEntry"]),
    )
    print("FOLO_ORIGINAL_REQUIREMENTS_ALL_GREEN")


if __name__ == "__main__":
    main()
