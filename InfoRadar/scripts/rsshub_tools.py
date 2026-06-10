#!/usr/bin/env python3
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "rsshub_instances.yaml"

DEFAULT_CONFIG = {
    "primary": "https://rsshub.app",
    "backups": [],
    "timeout_seconds": 10,
    "max_retry_per_source": 2,
    "enable_public_instance": True,
    "enable_self_hosted_instance": False,
}


def _parse_scalar(value: str):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if re.fullmatch(r"\d+", value):
        return int(value)
    return value


def load_rsshub_config(path: Path = CONFIG_FILE) -> dict:
    config = dict(DEFAULT_CONFIG)
    if not path.exists():
        return config

    current_key = ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^\s{2}[A-Za-z_][\w-]*:\s*$", line):
            current_key = line.strip()[:-1]
            if current_key in ("backups", "backup_examples"):
                config.setdefault(current_key, [])
            continue
        list_match = re.match(r"^\s{4}-\s*(.+?)\s*$", line)
        if list_match and current_key:
            config.setdefault(current_key, [])
            if isinstance(config[current_key], list):
                config[current_key].append(_parse_scalar(list_match.group(1)))
            continue
        scalar_match = re.match(r"^\s{2}([A-Za-z_][\w-]*):\s*(.+?)\s*$", line)
        if scalar_match:
            key, value = scalar_match.groups()
            config[key] = _parse_scalar(value)
            current_key = ""

    config["primary"] = normalize_base_url(str(config.get("primary") or DEFAULT_CONFIG["primary"]))
    config["backups"] = [
        normalize_base_url(str(base))
        for base in config.get("backups", [])
        if is_http_url(str(base)) and not str(base).endswith(".invalid")
    ]
    return config


def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit((value or "").strip())
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def rsshub_base_urls(config: dict | None = None) -> list[str]:
    config = config or load_rsshub_config()
    raw_env = os.environ.get("RSSHUB_BASE_URLS") or os.environ.get("RSSHUB_BASE_URL") or ""
    bases: list[str] = []
    if raw_env.strip():
        bases.extend(part.strip() for part in re.split(r"[;,]", raw_env) if part.strip())
    else:
        bases.append(str(config.get("primary") or DEFAULT_CONFIG["primary"]))
    bases.extend(str(base) for base in config.get("backups", []))

    out: list[str] = []
    for base in bases:
        normalized = normalize_base_url(base)
        if is_http_url(normalized) and normalized not in out:
            out.append(normalized)
    return out


def rsshub_route(url: str) -> str:
    raw = (url or "").strip()
    if raw.startswith("rsshub://"):
        return raw[len("rsshub://") :].strip("/")
    if not is_http_url(raw):
        return ""
    parsed = urlsplit(raw)
    host = (parsed.netloc or "").lower()
    if "rsshub" not in host:
        return ""
    return (parsed.path or "").strip("/")


def resolve_rsshub_url(url: str, base_url: str | None = None) -> str:
    raw = (url or "").strip()
    if raw.startswith(("http://", "https://")):
        return raw
    route = rsshub_route(raw)
    if not route:
        return raw
    bases = [normalize_base_url(base_url)] if base_url else rsshub_base_urls()
    base = next((item for item in bases if is_http_url(item)), DEFAULT_CONFIG["primary"])
    return f"{base}/{route}"


def _source_value(source: dict, key: str) -> str:
    return str(source.get(key) or "").strip()


def original_rss_url(source: dict) -> str:
    return _source_value(source, "RSS链接") or _source_value(source, "可抓取RSS链接")


def configured_fetch_url(source: dict) -> str:
    return _source_value(source, "_fetch_url") or _source_value(source, "可抓取RSS链接") or _source_value(source, "RSS链接")


def rsshub_candidates(source: dict) -> list[dict]:
    original = original_rss_url(source)
    configured = configured_fetch_url(source)
    route = rsshub_route(original) or rsshub_route(configured)
    candidates: list[dict] = []

    if not route:
        if is_http_url(configured):
            candidates.append(
                {
                    "原始RSS链接": original or configured,
                    "实际抓取URL": configured,
                    "使用RSSHub实例": "",
                    "抓取策略": "direct_rss",
                }
            )
        return candidates

    for idx, base in enumerate(rsshub_base_urls()):
        url = f"{base}/{route}"
        strategy = "rsshub_primary" if idx == 0 else "rsshub_backup"
        candidates.append(
            {
                "原始RSS链接": original or configured,
                "实际抓取URL": url,
                "使用RSSHub实例": base,
                "抓取策略": strategy,
            }
        )
    return candidates


def source_fetch_strategy(source: dict) -> str:
    candidates = rsshub_candidates(source)
    if candidates:
        return candidates[0].get("抓取策略", "")
    original = original_rss_url(source) or configured_fetch_url(source)
    if not original:
        return "replace_needed"
    if not is_http_url(original) and not original.startswith("rsshub://"):
        return "replace_needed"
    return "direct_rss"
