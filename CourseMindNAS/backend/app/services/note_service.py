from __future__ import annotations

from ..utils.time_utils import format_clock


def generate_note(title: str, chapters: list[dict], highlights: list[dict], segments: list[dict]) -> str:
    lines: list[str] = [
        f"# {title}",
        "",
        "## 一、本节概览",
        "",
        "本笔记由 CourseMind NAS 根据字幕、章节和重点时间轴自动生成。未配置 AI 分析模型时，这里会使用规则占位摘要。",
        "",
        "## 二、章节目录",
        "",
        "| 时间 | 章节 | 重要程度 |",
        "|---|---|---|",
    ]
    for chapter in chapters:
        lines.append(f"| {format_clock(chapter['start_time'])} | {chapter['title']} | {chapter['importance']} |")

    lines.extend(["", "## 三、核心知识点", ""])
    if highlights:
        for idx, item in enumerate(highlights, start=1):
            lines.append(f"### {idx}. {item['title']}")
            lines.append("")
            lines.append(item["content"])
            lines.append("")
    else:
        lines.append("暂无自动识别出的核心知识点。")
        lines.append("")

    lines.extend([
        "## 四、重点时间轴",
        "",
        "| 时间 | 类型 | 内容 | 重要程度 |",
        "|---|---|---|---|",
    ])
    for item in highlights:
        content = item["content"].replace("|", "\\|")
        lines.append(f"| {format_clock(item['start_time'])} | {item['type']} | {content} | {item['importance']} |")

    lines.extend(["", "## 五、易错点", ""])
    mistakes = [item for item in highlights if item["type"] == "mistake"]
    lines.extend([f"- {item['content']}" for item in mistakes] or ["暂无自动识别出的易错点。"])

    lines.extend(["", "## 六、典型例题", ""])
    examples = [item for item in highlights if item["type"] == "example"]
    lines.extend([f"- {format_clock(item['start_time'])} {item['content']}" for item in examples] or ["暂无自动识别出的典型例题。"])

    lines.extend(["", "## 七、复习问题", "", "1. 这节课的核心主题是什么？", "2. 哪些时间点需要重点复习？", "3. 字幕中是否出现了老师强调的定义、公式或易错点？"])

    lines.extend(["", "## 八、完整字幕索引", ""])
    for segment in segments:
        text = segment.get("cleaned_text") or segment.get("text") or ""
        lines.append(f"- `{format_clock(segment['start_time'])}` {text}")
    return "\n".join(lines) + "\n"
