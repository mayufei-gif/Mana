#!/usr/bin/env python3
"""Ubuntu Codex CLI worker for AgentHub command queue.

This worker is the Ubuntu-side counterpart to the Windows Codex App bridge.
It claims tasks from COMMAND_QUEUE.sqlite and executes them with `codex exec`.
No browser session token, cookie, API key, or desktop app login state is needed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
AGENTHUB_ROOT = SCRIPT_DIR.parents[1]
QUEUE_SCRIPT = SCRIPT_DIR / "agent_command_queue.py"
DEFAULT_RUNNER_ID = "ubuntu-codex-cli-runner"
DEFAULT_WORKDIR = Path(os.environ.get("CODEX_WEB_WORKDIR", str(Path.home() / "projects")))
DEFAULT_CODEX_BIN = Path.home() / ".local" / "npm-global" / "bin" / "codex"
LOG_DIR = AGENTHUB_ROOT / "logs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_log(line: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "ubuntu_codex_cli_runner.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} {line}\n")


def run_queue(args: list[str], timeout: int = 60) -> object:
    proc = subprocess.run(
        [sys.executable, str(QUEUE_SCRIPT), *args],
        cwd=str(AGENTHUB_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = proc.stdout or ""
    if proc.returncode != 0:
        raise RuntimeError(f"queue command failed rc={proc.returncode}: {output[:1200]}")
    return json.loads(output or "null")


def codex_exec_command(codex_bin: Path, workdir: Path, output_path: Path, sandbox: str) -> list[str]:
    return [
        str(codex_bin),
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(workdir if workdir.exists() else Path.home()),
        "-s",
        sandbox,
        "--output-last-message",
        str(output_path),
        "-",
    ]


def codex_exec_env() -> dict[str, str]:
    env = os.environ.copy()
    extra_path = [
        str(Path.home() / ".local" / "node" / "bin"),
        str(Path.home() / ".local" / "npm-global" / "bin"),
        str(Path.home() / "bin"),
    ]
    env["PATH"] = ":".join(extra_path + [env.get("PATH", "")])
    return env


def build_prompt(item: dict) -> str:
    raw = str(item.get("raw_text") or "").strip()
    command_id = str(item.get("command_id") or "")
    source = str(item.get("source") or "")
    policy = str(item.get("policy") or "")
    return "\n".join(
        [
            "你是 Ubuntu 上的 Codex CLI runner，正在执行 AgentHub 队列任务。",
            f"command_id: {command_id}",
            f"source: {source}",
            f"policy: {policy}",
            "",
            "请完成用户指令。除非用户明确要求，不要泄露 token、Cookie、API Key 或账号凭证。",
            "",
            raw,
        ]
    ).strip()


def execute_item(item: dict, args: argparse.Namespace) -> str:
    command_id = str(item.get("command_id") or "")
    codex_bin = Path(args.codex_bin).expanduser()
    if not codex_bin.exists():
        raise FileNotFoundError(f"codex binary not found: {codex_bin}")
    workdir = Path(args.workdir).expanduser()
    output_file = Path(tempfile.gettempdir()) / f"agenthub-{command_id or 'job'}-last.txt"
    prompt = build_prompt(item)
    proc = subprocess.run(
        codex_exec_command(codex_bin, workdir, output_file, args.sandbox),
        input=prompt,
        cwd=str(workdir if workdir.exists() else Path.home()),
        env=codex_exec_env(),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=args.exec_timeout,
    )
    stdout = (proc.stdout or "").strip()
    final = ""
    if output_file.exists():
        final = output_file.read_text(encoding="utf-8", errors="replace").strip()
    try:
        output_file.unlink(missing_ok=True)
    except Exception:
        pass
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed rc={proc.returncode}: {(final or stdout)[:1800]}")
    return final or stdout or "Codex CLI finished without text output."


def run_once(args: argparse.Namespace) -> int:
    items = run_queue(
        [
            "claim",
            "--runner-id",
            args.runner_id,
            "--runner-kind",
            "ubuntu",
            "--limit",
            str(args.limit),
            "--lease-seconds",
            str(args.lease_seconds),
        ],
        timeout=60,
    )
    if not isinstance(items, list) or not items:
        return 0

    for item in items:
        command_id = str(item.get("command_id") or "")
        write_log(f"claimed command_id={command_id} source={item.get('source')} policy={item.get('policy')}")
        try:
            result = execute_item(item, args)
            summary = result[: args.summary_chars]
            run_queue(
                [
                    "complete",
                    "--command-id",
                    command_id,
                    "--runner-id",
                    args.runner_id,
                    "--result-summary",
                    summary,
                ],
                timeout=60,
            )
            write_log(f"done command_id={command_id} result_chars={len(result)}")
        except Exception as exc:
            message = str(exc)[:1800]
            run_queue(
                [
                    "fail",
                    "--command-id",
                    command_id,
                    "--runner-id",
                    args.runner_id,
                    "--error",
                    message,
                    "--result-summary",
                    "Ubuntu Codex CLI runner failed.",
                ],
                timeout=60,
            )
            write_log(f"failed command_id={command_id} error={message}")
    return len(items)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ubuntu Codex CLI queue runner")
    parser.add_argument("--runner-id", default=os.environ.get("AGENTHUB_RUNNER_ID", DEFAULT_RUNNER_ID))
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", str(DEFAULT_CODEX_BIN)))
    parser.add_argument("--workdir", default=os.environ.get("CODEX_WEB_WORKDIR", str(DEFAULT_WORKDIR)))
    parser.add_argument("--sandbox", default=os.environ.get("CODEX_SANDBOX", "workspace-write"))
    parser.add_argument("--exec-timeout", type=int, default=int(os.environ.get("CODEX_WEB_EXEC_TIMEOUT", "900")))
    parser.add_argument("--lease-seconds", type=int, default=1800)
    parser.add_argument("--summary-chars", type=int, default=4000)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("AGENTHUB_RUNNER_POLL_SECONDS", "5")))
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.once:
        claimed = run_once(args)
        print(json.dumps({"ok": True, "claimed": claimed}, ensure_ascii=False))
        return 0
    write_log(f"started runner_id={args.runner_id} workdir={args.workdir}")
    while True:
        try:
            run_once(args)
        except Exception as exc:
            write_log(f"loop_error={str(exc)[:1800]}")
        time.sleep(max(1.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
