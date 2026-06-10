#!/usr/bin/env python3
import argparse
import os
import datetime as dt
import os
import json
import os
import socket
import os
import time
import os
import urllib.error
import os
import urllib.request
import os
from pathlib import Path

import rsshub_tools
import os
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
LOG_DIR = ROOT / "logs"

HEADERS = ["实例", "类型", "测试URL", "是否可连接", "HTTP状态", "耗时秒", "说明"]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def probe(base: str, timeout: int, route: str) -> dict:
    url = f"{base.rstrip('/')}/{route.strip('/')}" if route else base.rstrip("/")
    started = time.time()
    row = {
        "实例": base.rstrip("/"),
        "类型": "",
        "测试URL": url,
        "是否可连接": "否",
        "HTTP状态": "",
        "耗时秒": "",
        "说明": "",
    }
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "InfoRadarRSSHubCheck/0.1",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 0) or resp.getcode()
            row["HTTP状态"] = str(status)
            row["是否可连接"] = "是" if int(status) < 500 else "否"
            row["说明"] = "实例有响应；若具体路由失败，继续看源池健康检查。"
    except urllib.error.HTTPError as exc:
        row["HTTP状态"] = str(exc.code)
        row["是否可连接"] = "是" if exc.code < 500 else "否"
        row["说明"] = f"实例有 HTTP 响应：{exc.reason or exc}。403 不代表可绕过，只表示访问受限。"
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        row["HTTP状态"] = "ERR"
        row["说明"] = repr(exc)[:220]
    except Exception as exc:
        row["HTTP状态"] = "ERR"
        row["说明"] = repr(exc)[:220]
    row["耗时秒"] = round(time.time() - started, 2)
    return row


def write_markdown(path: Path, rows: list[dict], xlsx_path: Path) -> None:
    ok_count = sum(1 for row in rows if row.get("是否可连接") == "是")
    lines = [
        "# RSSHub 实例检查",
        "",
        f"生成时间：{now_text()}",
        f"Excel：{xlsx_path}",
        "",
        f"- 配置实例数：{len(rows)}",
        f"- 可连接实例数：{ok_count}",
        "",
        "## 检查结果",
        "",
        "| 实例 | 类型 | HTTP状态 | 可连接 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('实例')} | {row.get('类型')} | {row.get('HTTP状态')} | {row.get('是否可连接')} | {row.get('说明')} |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本脚本只检查公开实例连通性，不读取 Folo token、Cookie 或账号凭证。",
            "- 403/登录限制不做绕过，只进入替换、自建 RSSHub 或人工核验流程。",
            "- `config/rsshub_instances.yaml` 中的 `backup_examples` 是示例，不会当作真实实例测试。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check configured RSSHub instances")
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--route", default="", help="可选：指定一个 RSSHub route 进行测试，例如 hellogithub/home")
    args = parser.parse_args()

    config = rsshub_tools.load_rsshub_config()
    bases = rsshub_tools.rsshub_base_urls(config)
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = today_stamp()
    xlsx_path = RETURN_DIR / f"RSSHub实例检查_{stamp}.xlsx"
    md_path = RETURN_DIR / f"RSSHub实例检查_{stamp}.md"

    rows = []
    primary = bases[0] if bases else ""
    for base in bases:
        row = probe(base, args.timeout, args.route)
        row["类型"] = "primary" if base == primary else "backup"
        rows.append(row)

    write_xlsx(xlsx_path, HEADERS, rows, sheet_name="RSSHub实例检查")
    write_markdown(md_path, rows, xlsx_path)
    result = {
        "success": True,
        "instance_count": len(rows),
        "available_count": sum(1 for row in rows if row.get("是否可连接") == "是"),
        "xlsx": str(xlsx_path),
        "markdown": str(md_path),
        "output_files": [str(xlsx_path), str(md_path)],
    }
    append_jsonl(LOG_DIR / "run.log", {"task": "check_rsshub_instances", **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
