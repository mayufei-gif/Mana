import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = "http://127.0.0.1:8769"
ENV_PATH = "/home/mana/inforadar-runtime/inforadar-web.env"


def read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def request_json(path: str, *, headers: dict[str, str], payload: dict | None = None, method: str | None = None, timeout: int = 30) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    env = read_env(ENV_PATH)
    token = env.get("WEB_ACCESS_TOKEN", "").strip()
    secret = env.get("WEB_TOTP_SECRET", "").replace(" ", "").strip().upper() or "no-totp"
    session_value = hashlib.sha256(f"inforadar-session:v2-totp:{token}:{secret}".encode("utf-8")).hexdigest()
    cookie_headers = {"Cookie": "inforadar_session=" + session_value}
    json_headers = {**cookie_headers, "Content-Type": "application/json"}

    session = request_json("/api/session", headers=cookie_headers, timeout=8)
    print(
        "SESSION authenticated=%s protected=%s totp_required=%s"
        % (session.get("authenticated"), session.get("protected"), session.get("totp_required"))
    )
    if not session.get("authenticated"):
        print("AUTH_FAILED")
        return 2

    summary = request_json(
        "/api/codex-terminal/summary",
        headers=json_headers,
        payload={"session": "codex"},
        method="POST",
        timeout=60,
    )
    handoff = summary.get("handoff") or {}
    print(
        "SUMMARY ok=%s id=%s size=%s count=%s"
        % (summary.get("ok"), handoff.get("id"), handoff.get("size"), len(summary.get("handoffs") or []))
    )

    handoffs = request_json("/api/codex-terminal/handoffs", headers=cookie_headers, timeout=8)
    print("HANDOFFS ok=%s count=%s" % (handoffs.get("ok"), len(handoffs.get("handoffs") or [])))

    handoff_id = handoff.get("id") or ""
    if not handoff_id:
        print("NO_HANDOFF_ID")
        return 3

    deliver = request_json(
        "/api/codex-terminal/handoff",
        headers=json_headers,
        payload={"handoff_id": handoff_id, "target_session": "codex-qa"},
        method="POST",
        timeout=60,
    )
    print(
        "DELIVER job=%s session=%s status=%s"
        % (bool(deliver.get("job_id")), deliver.get("session"), deliver.get("job_status"))
    )
    return 0 if deliver.get("job_id") else 4


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP_ERROR status={exc.code} body={body[:500]}")
        raise SystemExit(10)
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}")
        raise SystemExit(11)
