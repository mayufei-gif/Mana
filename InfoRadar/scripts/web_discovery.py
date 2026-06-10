#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import source_intake


ROOT = Path(__file__).resolve().parents[1]


def parse_json_output(stdout: str) -> dict:
    stdout = (stdout or "").strip()
    if not stdout:
        return {}
    start = stdout.find("{")
    if start < 0:
        return {"stdout": stdout}
    try:
        return json.loads(stdout[start:])
    except Exception:
        return {"stdout": stdout}


def run_public_discovery(query: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "discover_sources.py"), "--keyword", query],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    discovery = parse_json_output(proc.stdout)
    discovery["returncode"] = proc.returncode
    if proc.stderr.strip():
        discovery["stderr"] = proc.stderr.strip()
    if proc.returncode != 0:
        return {
            "success": False,
            "query": query,
            "public_search_count": 0,
            "candidate_source_count": 0,
            "error": discovery.get("stderr") or discovery.get("stdout") or "candidate discovery failed",
            "discovery": discovery,
        }
    intake = source_intake.summarize_source_intake(
        query,
        discovery.get("csv", ""),
        discovery.get("watchlist_csv", ""),
    )
    output_files = []
    for value in discovery.get("output_files", []) if isinstance(discovery.get("output_files"), list) else []:
        output_files.append(value)
    for key in ["return_xlsx", "return_summary", "return_watchlist_xlsx", "return_watchlist_summary"]:
        if discovery.get(key):
            output_files.append(discovery[key])
    output_files.extend(intake.get("output_files", []))
    return {
        "success": True,
        "query": query,
        "public_search_count": int(discovery.get("new_candidates", 0) or 0),
        "candidate_source_count": int(intake.get("candidate_source_count", 0) or 0),
        "import_ready_count": int(intake.get("import_ready_count", 0) or 0),
        "watch_only_count": int(intake.get("watch_only_count", 0) or 0),
        "discovery": discovery,
        "source_intake": intake,
        "output_files": output_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled public discovery wrapper")
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    result = run_public_discovery(args.query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
