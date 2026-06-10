from __future__ import annotations

from web.backend import app


def main() -> None:
    data = app.resource_hive_summary(limit=5)
    markdown = app.resource_hive_markdown()
    assert data.get("ok") is True, data
    assert "InfoRadar 全网资源鉴赏池" in markdown, markdown[:120]
    assert "| 类型 | 名称 | 状态 | 次数 | 链接 | NAS路径 | 更新时间 |" in markdown, markdown[:300]
    print("RESOURCE_HIVE_EXPORT_OK")
    print(f"total={data.get('total')}")
    print(f"markdown_chars={len(markdown)}")


if __name__ == "__main__":
    main()
