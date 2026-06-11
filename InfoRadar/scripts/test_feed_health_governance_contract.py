from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_feed_health import classify_error, finalize_strategy, strategy_row, write_governance_report, write_markdown


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def base_source(**updates) -> dict:
    source = {
        "源名称": "测试源",
        "可抓取RSS链接": "https://example.com/feed.xml",
        "Folo文件夹路径": "测试/源池",
        "长期价值评分": "50",
    }
    source.update(updates)
    return source


def failed_row(error_type: str, *, status: str = "ERR", strategy: str = "direct_rss", cache: str = "否") -> dict:
    return {
        "源名称": "测试源",
        "原始RSS链接": "https://example.com/feed.xml",
        "实际抓取URL": "https://example.com/feed.xml",
        "RSS链接": "https://example.com/feed.xml",
        "Folo文件夹路径": "测试/源池",
        "抓取策略": strategy,
        "是否抓取成功": "否",
        "HTTP状态": status,
        "错误类型": error_type,
        "错误详情": "simulated failure",
        "最近成功时间": "",
        "是否使用缓存": cache,
        "失败次数": 3,
        "RSSHub实例": "",
        "是否建议替换": "否",
        "是否建议废弃": "否",
        "建议处理方式": "",
    }


def test_error_classification() -> None:
    cases = [
        ("not-a-url", "", "", "", "URL异常"),
        ("https://example.com/feed.xml", "403", "Forbidden", "", "403访问限制"),
        ("https://example.com/feed.xml", "404", "Not Found", "", "404源失效"),
        ("https://example.com/feed.xml", "ERR", "timed out", "", "网络超时"),
        ("https://example.com/feed.xml", "200", "mismatched tag", "", "XML解析失败"),
        ("https://example.com/feed.xml", "200", "0 items", "", "空内容"),
        ("https://rsshub.example/routes", "ERR", "upstream failed", "rsshub_primary", "RSSHub主实例失败"),
        ("https://rsshub.example/routes", "ERR", "upstream failed", "rsshub_backup", "RSSHub备用实例失败"),
    ]
    for url, status, error, strategy, expected in cases:
        assert_equal(classify_error(url, status, error, strategy), expected, f"classify {expected}")


def test_strategy_recommendations_and_reports() -> None:
    rsshub_403 = failed_row("403访问限制", status="403", strategy="rsshub_primary")
    finalize_strategy(base_source(), rsshub_403)
    assert_equal(rsshub_403["是否建议替换"], "是", "RSSHub 403 should be replace-needed")
    if "不硬绕" not in rsshub_403["建议处理方式"] and "备用 RSSHub" not in rsshub_403["建议处理方式"]:
        raise AssertionError(f"RSSHub 403 suggestion is too vague: {rsshub_403}")

    official_403 = failed_row("403访问限制", status="403")
    finalize_strategy(base_source(官网链接="https://www.gov.cn/"), official_403)
    assert_equal(official_403["抓取策略"], "official_page", "official 403 should become official_page")
    if "人工核验" not in official_403["建议处理方式"]:
        raise AssertionError(f"official 403 should keep manual verification: {official_403}")

    xml_failed = failed_row("XML解析失败", status="200")
    finalize_strategy(base_source(), xml_failed)
    assert_equal(xml_failed["是否建议替换"], "是", "XML failure should need replacement")

    timeout_failed = failed_row("网络超时")
    finalize_strategy(base_source(), timeout_failed)
    if "降低并发" not in timeout_failed["建议处理方式"]:
        raise AssertionError(f"timeout suggestion should mention concurrency/retry: {timeout_failed}")

    empty_failed = failed_row("空内容")
    finalize_strategy(base_source(), empty_failed)
    if "连续空内容" not in empty_failed["建议处理方式"]:
        raise AssertionError(f"empty feed suggestion should mention repeated empty content: {empty_failed}")

    rows = [rsshub_403, official_403, xml_failed, timeout_failed, empty_failed]
    strategy_rows = [strategy_row(base_source(), row) for row in rows]
    with tempfile.TemporaryDirectory(prefix="feed-health-") as tmp:
        tmp_path = Path(tmp)
        md_path = tmp_path / "RSS源健康检查_测试.md"
        governance_path = tmp_path / "RSSHub备用与403源治理报告_测试.md"
        write_markdown(md_path, rows, tmp_path / "健康.xlsx", tmp_path / "策略.xlsx")
        write_governance_report(governance_path, rows, strategy_rows)
        md_text = md_path.read_text(encoding="utf-8")
        governance_text = governance_path.read_text(encoding="utf-8")
        for marker in ["403访问限制", "XML解析失败", "网络超时", "空内容", "建议优先处理的失败源"]:
            if marker not in md_text:
                raise AssertionError(f"health markdown missing marker {marker!r}")
        for marker in ["403数量", "建议替换数量", "不硬绕过", "下一步需要人工处理的源清单"]:
            if marker not in governance_text:
                raise AssertionError(f"governance markdown missing marker {marker!r}")


def main() -> int:
    test_error_classification()
    test_strategy_recommendations_and_reports()
    print({"ok": True, "contract": "feed_health_governance"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
