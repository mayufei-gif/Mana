from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "web" / "frontend" / "app.js"


def require(text: str, needle: str, message: str) -> None:
    if needle not in text:
        raise AssertionError(message)


def main() -> int:
    text = APP_JS.read_text(encoding="utf-8", errors="replace")
    require(text, 'platform === "公众号" && kind === "name"', "公众号名称检索必须走站内微信桥接分支")
    require(text, '"/api/manual-hive/wechat/search"', "前端缺少公众号搜索接口调用")
    require(text, '"/api/manual-hive/wechat/subscribe"', "前端缺少公众号订阅接口调用")
    require(text, "rss_url", "前端公众号卡片必须使用后端返回的 RSS 代理链接")
    require(text, "rss_view_url", "前端公众号卡片必须优先打开可读文章列表")
    require(text, "查看文章", "公众号卡片需要提供人类可读入口")
    require(text, "RSS源", "公众号卡片需要保留原始 RSS 源入口")
    require(text, "data-wechat-subscribe", "前端缺少公众号订阅按钮绑定")
    require(text, "data-wechat-search-radar", "前端缺少订阅后回到个人雷达检索入口")
    require(text, "manualHiveName", "公众号名称输入框未绑定")
    print({"ok": True, "file": str(APP_JS)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
