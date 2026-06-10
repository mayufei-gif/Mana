#!/usr/bin/env bash
set -euo pipefail

PROJECT="${COURSEMIND_PROJECT:-$HOME/coursemind-nas}"
API_BASE="${COURSEMIND_API_BASE:-http://127.0.0.1:8766}"
LIMIT="${COURSEMIND_ASR_LIMIT:-1}"
IDS="${COURSEMIND_ASR_IDS:-}"
FOLDER="${COURSEMIND_ASR_FOLDER:-}"
MODE="${COURSEMIND_ASR_MODE:-needed}"
SCAN=1
SCAN_DIR=""
REPROCESS=0
DRY_RUN=0
ALLOW_MOCK=0
VERIFY_STREAM=0
POLL_SECONDS="${COURSEMIND_ASR_POLL_SECONDS:-30}"
TIMEOUT_MINUTES="${COURSEMIND_ASR_TIMEOUT_MINUTES:-360}"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run_real_asr_queue_once.sh [options]

Options:
  --limit N             Process at most N selected videos. Default: 1
  --ids 5,6,10          Process only these video IDs.
  --folder NAME         Process videos in this folder/path fragment.
  --mode needed|failed|all
                        needed: missing subtitle/analysis/note or mock transcript.
                        failed: failed videos only.
                        all: every matched non-missing video.
  --scan-dir PATH       Scan one container-visible video directory before selecting.
  --no-scan             Do not scan before selecting.
  --reprocess           Force /reprocess instead of /process.
  --dry-run             Print selected videos without enqueueing.
  --verify-stream       Verify /stream byte range after completion.
  --allow-mock          Do not abort when provider is mock. Useful only for UI tests.
  --poll-seconds N      Status polling interval. Default: 30
  --timeout-minutes N   Per-video timeout. Default: 360
  --api-base URL        Backend API base. Default: http://127.0.0.1:8766
  --help                Show this help.

Examples:
  bash scripts/run_real_asr_queue_once.sh --limit 1
  bash scripts/run_real_asr_queue_once.sh --ids 12 --reprocess
  bash scripts/run_real_asr_queue_once.sh --folder "初级会计" --limit 2
  bash scripts/run_real_asr_queue_once.sh --dry-run --mode needed
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --limit)
      LIMIT="${2:?missing value for --limit}"
      shift 2
      ;;
    --ids)
      IDS="${2:?missing value for --ids}"
      shift 2
      ;;
    --folder)
      FOLDER="${2:?missing value for --folder}"
      shift 2
      ;;
    --mode)
      MODE="${2:?missing value for --mode}"
      shift 2
      ;;
    --scan-dir)
      SCAN_DIR="${2:?missing value for --scan-dir}"
      SCAN=1
      shift 2
      ;;
    --no-scan)
      SCAN=0
      shift
      ;;
    --reprocess)
      REPROCESS=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --verify-stream)
      VERIFY_STREAM=1
      shift
      ;;
    --allow-mock)
      ALLOW_MOCK=1
      shift
      ;;
    --poll-seconds)
      POLL_SECONDS="${2:?missing value for --poll-seconds}"
      shift 2
      ;;
    --timeout-minutes)
      TIMEOUT_MINUTES="${2:?missing value for --timeout-minutes}"
      shift 2
      ;;
    --api-base)
      API_BASE="${2:?missing value for --api-base}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  needed|failed|all) ;;
  *)
    echo "[ERROR] --mode must be needed, failed, or all." >&2
    exit 2
    ;;
esac

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [ "$LIMIT" -lt 1 ]; then
  echo "[ERROR] --limit must be a positive integer." >&2
  exit 2
fi

if ! [[ "$POLL_SECONDS" =~ ^[0-9]+$ ]] || [ "$POLL_SECONDS" -lt 5 ]; then
  echo "[ERROR] --poll-seconds must be an integer >= 5." >&2
  exit 2
fi

if ! [[ "$TIMEOUT_MINUTES" =~ ^[0-9]+$ ]] || [ "$TIMEOUT_MINUTES" -lt 1 ]; then
  echo "[ERROR] --timeout-minutes must be a positive integer." >&2
  exit 2
fi

cd "$PROJECT"
LOG_DIR="$PROJECT/CourseMind/logs"
mkdir -p "$LOG_DIR"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/real_asr_queue_once_$RUN_ID.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== CourseMind real ASR queue once =="
echo "time=$(date '+%Y-%m-%d %H:%M:%S')"
echo "project=$PROJECT"
echo "api_base=$API_BASE"
echo "log_file=$LOG_FILE"
echo "limit=$LIMIT ids=${IDS:-<auto>} folder=${FOLDER:-<any>} mode=$MODE scan=$SCAN scan_dir=${SCAN_DIR:-<default>} reprocess=$REPROCESS dry_run=$DRY_RUN"

ASR_API_BASE="$API_BASE" \
ASR_LIMIT="$LIMIT" \
ASR_IDS="$IDS" \
ASR_FOLDER="$FOLDER" \
ASR_MODE="$MODE" \
ASR_SCAN="$SCAN" \
ASR_SCAN_DIR="$SCAN_DIR" \
ASR_REPROCESS="$REPROCESS" \
ASR_DRY_RUN="$DRY_RUN" \
ASR_ALLOW_MOCK="$ALLOW_MOCK" \
ASR_VERIFY_STREAM="$VERIFY_STREAM" \
ASR_POLL_SECONDS="$POLL_SECONDS" \
ASR_TIMEOUT_MINUTES="$TIMEOUT_MINUTES" \
python3 - <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE = os.environ["ASR_API_BASE"].rstrip("/")
LIMIT = int(os.environ["ASR_LIMIT"])
IDS_RAW = os.environ.get("ASR_IDS", "").strip()
FOLDER = os.environ.get("ASR_FOLDER", "").strip().replace("\\", "/")
MODE = os.environ["ASR_MODE"]
SCAN = os.environ["ASR_SCAN"] == "1"
SCAN_DIR = os.environ.get("ASR_SCAN_DIR", "").strip()
REPROCESS = os.environ["ASR_REPROCESS"] == "1"
DRY_RUN = os.environ["ASR_DRY_RUN"] == "1"
ALLOW_MOCK = os.environ["ASR_ALLOW_MOCK"] == "1"
VERIFY_STREAM = os.environ["ASR_VERIFY_STREAM"] == "1"
POLL_SECONDS = int(os.environ["ASR_POLL_SECONDS"])
TIMEOUT_MINUTES = int(os.environ["ASR_TIMEOUT_MINUTES"])


def request_json(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: http={exc.code} body={detail}") from exc
    if not raw:
        return {}
    return json.loads(raw)


def request_bytes(path: str, timeout: int = 60, headers: dict[str, str] | None = None) -> tuple[int, int, str]:
    req = urllib.request.Request(f"{BASE}{path}", headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        content_type = resp.headers.get("content-type", "")
        return resp.status, len(body), content_type


def parse_ids(raw: str) -> set[int]:
    if not raw:
        return set()
    values: set[int] = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        values.add(int(item))
    return values


def norm(value: object) -> str:
    return str(value or "").strip().replace("\\", "/").lower()


def is_failed(video: dict) -> bool:
    values = [
        video.get("status"),
        video.get("subtitle_status"),
        video.get("analysis_status"),
        video.get("note_status"),
    ]
    return any(value == "failed" for value in values)


def is_ready(video: dict) -> bool:
    return (
        video.get("subtitle_status") == "ready"
        and video.get("analysis_status") == "ready"
        and video.get("note_status") == "ready"
        and not int(video.get("has_mock_transcript") or 0)
    )


def needs_processing(video: dict) -> bool:
    if int(video.get("missing") or 0):
        return False
    if MODE == "all":
        return True
    if MODE == "failed":
        return is_failed(video)
    return not is_ready(video)


def folder_matches(video: dict) -> bool:
    if not FOLDER:
        return True
    needle = norm(FOLDER).strip("/")
    folder = norm(video.get("folder")).strip("/")
    path = norm(video.get("file_path"))
    title = norm(video.get("title"))
    return (
        folder == needle
        or folder.startswith(f"{needle}/")
        or needle in path
        or needle in title
    )


def endpoint_for(video: dict) -> str:
    video_id = int(video["id"])
    if REPROCESS or is_failed(video) or int(video.get("has_mock_transcript") or 0):
        return f"/api/videos/{video_id}/reprocess"
    return f"/api/videos/{video_id}/process"


def wait_for_video(video_id: int) -> dict:
    deadline = time.time() + TIMEOUT_MINUTES * 60
    last = ""
    while time.time() < deadline:
        payload = request_json("GET", f"/api/videos/{video_id}/status", timeout=60)
        video = payload["data"]["video"]
        job = payload["data"].get("job") or {}
        line = (
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} id={video_id} "
            f"video={video.get('status')} subtitle={video.get('subtitle_status')} "
            f"analysis={video.get('analysis_status')} note={video.get('note_status')} "
            f"job={job.get('status')} step={job.get('current_step')} progress={job.get('progress')}"
        )
        if line != last:
            print(line, flush=True)
            last = line
        if is_ready(video):
            return video
        if video.get("status") == "missing" or job.get("status") == "failed":
            stage = job.get("error_stage") or video.get("error_stage")
            message = job.get("error_message") or video.get("error_message")
            raise RuntimeError(f"video {video_id} failed: stage={stage} message={message}")
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"video {video_id} timeout after {TIMEOUT_MINUTES} minutes")


def verify_video(video_id: int) -> None:
    paths = [
        f"/api/videos/{video_id}/transcript",
        f"/api/videos/{video_id}/chapters",
        f"/api/videos/{video_id}/highlights",
        f"/api/videos/{video_id}/note",
        f"/api/videos/{video_id}/smart-subtitle/vtt",
    ]
    if VERIFY_STREAM:
        paths.append(f"/api/videos/{video_id}/stream")
    for path in paths:
        headers = {"Range": "bytes=0-1023"} if path.endswith("/stream") else None
        status, size, content_type = request_bytes(path, timeout=120, headers=headers)
        print(f"verify {path} http={status} bytes={size} type={content_type}", flush=True)


health = request_json("GET", "/healthz", timeout=30)
if not health.get("ok"):
    raise RuntimeError(f"backend health failed: {health}")

settings_payload = request_json("GET", "/api/settings", timeout=60)
settings = settings_payload.get("data") or {}
provider = str(settings.get("transcription_provider") or "").lower()
model = settings.get("transcription_model")
has_key = bool(settings.get("has_transcription_api_key"))
print(f"settings provider={provider} model={model} has_key={has_key} chunk_seconds={settings.get('chunk_seconds')}")
if provider == "mock" and not ALLOW_MOCK:
    raise RuntimeError("current transcription provider is mock; switch backend to aliyun_dashscope before real ASR")
if provider in {"aliyun_dashscope", "aliyun_paraformer"} and not has_key:
    raise RuntimeError("missing DashScope/transcription API key")

request_json("POST", "/api/settings", {"auto_process_new_videos": False}, timeout=60)
print("auto_process_new_videos=false")

if SCAN:
    payload = {"video_dir": SCAN_DIR} if SCAN_DIR else None
    result = request_json("POST", "/api/videos/scan", payload, timeout=300)
    data = result.get("data") or {}
    print(
        "scan "
        f"found={data.get('found')} inserted={data.get('inserted')} updated={data.get('updated')} "
        f"skipped={data.get('skipped')} missing={data.get('missing')} recursive={data.get('recursive')}"
    )

videos = request_json("GET", "/api/videos", timeout=120).get("data") or []
ids = parse_ids(IDS_RAW)
selected = []
for video in videos:
    video_id = int(video["id"])
    if ids and video_id not in ids:
        continue
    if not folder_matches(video):
        continue
    if not needs_processing(video):
        continue
    selected.append(video)
    if len(selected) >= LIMIT:
        break

if not selected:
    print("NO_MATCHED_VIDEO_TO_PROCESS")
    sys.exit(0)

print("selected:")
for video in selected:
    print(
        f"  id={video['id']} title={video.get('title')} folder={video.get('folder')} "
        f"status={video.get('status')} subtitle={video.get('subtitle_status')} "
        f"analysis={video.get('analysis_status')} note={video.get('note_status')} "
        f"mock={video.get('has_mock_transcript')}"
    )

if DRY_RUN:
    print("DRY_RUN_DONE")
    sys.exit(0)

completed: list[int] = []
for video in selected:
    video_id = int(video["id"])
    endpoint = endpoint_for(video)
    print(f"enqueue id={video_id} endpoint={endpoint}")
    body = request_json("POST", endpoint, timeout=60)
    print(f"enqueue_result {json.dumps(body.get('data') or body, ensure_ascii=False)}")
    wait_for_video(video_id)
    verify_video(video_id)
    completed.append(video_id)
    print(f"VIDEO_DONE id={video_id}")

print(f"ASR_QUEUE_DONE completed={completed}")
PY

echo "== done =="
