import hashlib
import json
import time
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

    prompt = "AI Sidekick 链路测试：请只回复 SIDEKICK_ROUTE_OK，不要回复其它内容。"
    sent = request_json(
        "/api/codex-terminal/send",
        headers=json_headers,
        payload={"session": "codex-qa", "message": prompt},
        method="POST",
        timeout=30,
    )
    print("SEND ok=%s session=%s job=%s status=%s" % (sent.get("ok"), sent.get("session"), bool(sent.get("job_id")), sent.get("job_status")))

    job_id = sent.get("job_id")
    if not job_id:
        return 2

    for _ in range(45):
        time.sleep(1)
        status = request_json(f"/api/codex-terminal/job/{job_id}?session=codex-qa", headers=cookie_headers, timeout=8)
        if status.get("job_status") in {"done", "error", "timeout"}:
            output = status.get("output") or ""
            print("JOB status=%s ok_text=%s" % (status.get("job_status"), "SIDEKICK_ROUTE_OK" in output))
            return 0 if "SIDEKICK_ROUTE_OK" in output else 3

    print("JOB status=still-running ok_text=False")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
