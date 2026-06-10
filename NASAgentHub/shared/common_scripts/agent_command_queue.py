#!/usr/bin/env python3
"""SQLite command queue for Win11/Ubuntu dual Codex runners.

The queue is intentionally small and dependency-free. It gives both sides a
single source of truth and uses SQLite transactions to prevent duplicate
execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "coordination" / "COMMAND_QUEUE.sqlite"


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def make_dedupe_key(source: str, external_id: str | None, text: str) -> str:
    seed = f"{source}|{external_id or ''}|{normalize_text(text)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def make_command_id(dedupe_key: str) -> str:
    return "cmd_" + hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:24]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
  command_id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  external_msg_id TEXT,
  raw_text TEXT NOT NULL,
  policy TEXT NOT NULL DEFAULT 'queue',
  target_runner TEXT NOT NULL DEFAULT 'any',
  priority INTEGER NOT NULL DEFAULT 50,
  status TEXT NOT NULL DEFAULT 'queued',
  created_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  claimed_by TEXT,
  claimed_at TEXT,
  lease_expires_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  result_summary TEXT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_commands_status_priority
ON commands(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_commands_target
ON commands(target_runner, status);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def enqueue(args: argparse.Namespace) -> dict:
    db = Path(args.db or default_db_path())
    conn = connect(db)
    init_db(conn)
    dedupe_key = args.dedupe_key or make_dedupe_key(args.source, args.external_id, args.text)
    command_id = args.command_id or make_command_id(dedupe_key)
    policy = args.policy
    status = "held" if policy == "hold" else "queued"
    priority = args.priority if args.priority is not None else (100 if policy == "now" else 50)
    now = utc_now()
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO commands (
              command_id, dedupe_key, source, external_msg_id, raw_text, policy,
              target_runner, priority, status, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command_id,
                dedupe_key,
                args.source,
                args.external_id,
                args.text,
                policy,
                args.target_runner,
                priority,
                status,
                args.created_by,
                now,
                now,
            ),
        )
    row = conn.execute("SELECT * FROM commands WHERE dedupe_key=?", (dedupe_key,)).fetchone()
    data = row_to_dict(row)
    data["inserted"] = data["created_at"] == now
    return data


def release_expired_leases(conn: sqlite3.Connection) -> None:
    now = utc_now()
    conn.execute(
        """
        UPDATE commands
        SET status='queued', claimed_by=NULL, claimed_at=NULL, lease_expires_at=NULL,
            updated_at=?
        WHERE status='claimed'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= ?
          AND attempt_count < max_attempts
        """,
        (now, now),
    )


def claim(args: argparse.Namespace) -> list[dict]:
    db = Path(args.db or default_db_path())
    conn = connect(db)
    init_db(conn)
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    now = now_dt.isoformat()
    lease_until = (now_dt + timedelta(seconds=args.lease_seconds)).isoformat()
    target_choices = ("any", args.runner_kind, args.runner_id)
    claimed: list[dict] = []

    conn.execute("BEGIN IMMEDIATE")
    try:
        release_expired_leases(conn)
        if args.command_id:
            rows = conn.execute(
                """
                SELECT command_id FROM commands
                WHERE command_id=?
                  AND status='queued'
                  AND target_runner IN (?, ?, ?)
                  AND attempt_count < max_attempts
                LIMIT 1
                """,
                (args.command_id, *target_choices),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT command_id FROM commands
                WHERE status='queued'
                  AND target_runner IN (?, ?, ?)
                  AND attempt_count < max_attempts
                ORDER BY priority DESC, created_at ASC
                LIMIT ?
                """,
                (*target_choices, args.limit),
            ).fetchall()
        for row in rows:
            cur = conn.execute(
                """
                UPDATE commands
                SET status='claimed', claimed_by=?, claimed_at=?, lease_expires_at=?,
                    attempt_count=attempt_count+1, updated_at=?
                WHERE command_id=? AND status='queued'
                """,
                (args.runner_id, now, lease_until, now, row["command_id"]),
            )
            if cur.rowcount == 1:
                claimed_row = conn.execute(
                    "SELECT * FROM commands WHERE command_id=?",
                    (row["command_id"],),
                ).fetchone()
                claimed.append(row_to_dict(claimed_row))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return claimed


def approve(args: argparse.Namespace) -> dict | None:
    db = Path(args.db or default_db_path())
    conn = connect(db)
    init_db(conn)
    now = utc_now()
    with conn:
        conn.execute(
            """
            UPDATE commands
            SET status='queued', updated_at=?
            WHERE command_id=? AND status='held'
            """,
            (now, args.command_id),
        )
    return row_to_dict(conn.execute("SELECT * FROM commands WHERE command_id=?", (args.command_id,)).fetchone())


def complete(args: argparse.Namespace, status: str) -> dict | None:
    db = Path(args.db or default_db_path())
    conn = connect(db)
    init_db(conn)
    now = utc_now()
    with conn:
        conn.execute(
            """
            UPDATE commands
            SET status=?, result_summary=?, error=?, updated_at=?, lease_expires_at=NULL
            WHERE command_id=? AND claimed_by=?
            """,
            (status, args.result_summary, args.error, now, args.command_id, args.runner_id),
        )
    return row_to_dict(conn.execute("SELECT * FROM commands WHERE command_id=?", (args.command_id,)).fetchone())


def list_commands(args: argparse.Namespace) -> list[dict]:
    db = Path(args.db or default_db_path())
    conn = connect(db)
    init_db(conn)
    params: list[str] = []
    where = ""
    if args.status:
        where = "WHERE status=?"
        params.append(args.status)
    rows = conn.execute(
        f"SELECT * FROM commands {where} ORDER BY created_at DESC LIMIT ?",
        (*params, args.limit),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentHub command queue")
    parser.add_argument("--db", help="SQLite queue path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p = sub.add_parser("enqueue")
    p.add_argument("--text", required=True)
    p.add_argument("--source", default="wechat")
    p.add_argument("--external-id")
    p.add_argument("--dedupe-key")
    p.add_argument("--command-id")
    p.add_argument("--policy", choices=["now", "queue", "hold"], default="queue")
    p.add_argument("--target-runner", default="any")
    p.add_argument("--priority", type=int)
    p.add_argument("--created-by", default="openclaw")

    p = sub.add_parser("claim")
    p.add_argument("--runner-id", required=True)
    p.add_argument("--runner-kind", choices=["win11", "ubuntu"], required=True)
    p.add_argument("--command-id")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--lease-seconds", type=int, default=900)

    p = sub.add_parser("approve")
    p.add_argument("--command-id", required=True)

    for name, status in [("complete", "done"), ("fail", "failed")]:
        p = sub.add_parser(name)
        p.set_defaults(final_status=status)
        p.add_argument("--command-id", required=True)
        p.add_argument("--runner-id", required=True)
        p.add_argument("--result-summary", default="")
        p.add_argument("--error", default="")

    p = sub.add_parser("list")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        db = Path(args.db or default_db_path())
        conn = connect(db)
        init_db(conn)
        print_json({"ok": True, "db": str(db)})
    elif args.cmd == "enqueue":
        print_json(enqueue(args))
    elif args.cmd == "claim":
        print_json(claim(args))
    elif args.cmd == "approve":
        print_json(approve(args))
    elif args.cmd in {"complete", "fail"}:
        print_json(complete(args, args.final_status))
    elif args.cmd == "list":
        print_json(list_commands(args))
    else:
        raise SystemExit(f"unknown command: {args.cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
