from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


def _load_env_file() -> None:
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    backend_dir: Path = Path(__file__).resolve().parents[1]
    project_root: Path = Path(__file__).resolve().parents[2]

    def _first_env(self, *names: str, default: str | Path) -> str:
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        return str(default)

    @property
    def storage_dir(self) -> Path:
        raw = self._first_env("COURSEMIND_STORAGE_DIR", "PROCESSED_DIR", "STORAGE_DIR", default=self.project_root / "storage")
        return Path(raw).resolve()

    @property
    def data_dir(self) -> Path:
        raw = self._first_env("DATA_DIR", default=self.storage_dir)
        return Path(raw).resolve()

    @property
    def config_dir(self) -> Path:
        raw = self._first_env("CONFIG_DIR", default=self.project_root / "config")
        return Path(raw).resolve()

    @property
    def log_dir(self) -> Path:
        raw = self._first_env("LOG_DIR", "COURSEMIND_LOG_DIR", default=self.project_root / "storage" / "logs")
        return Path(raw).resolve()

    @property
    def database_path(self) -> Path:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            parsed = urlparse(database_url)
            if parsed.scheme != "sqlite":
                raise ValueError("Only sqlite DATABASE_URL is supported, for example sqlite:////data/coursemind.db")
            path_text = unquote(parsed.path)
            if parsed.netloc:
                path_text = f"//{parsed.netloc}{path_text}"
            return Path(path_text).resolve()
        raw = self._first_env("COURSEMIND_DB_PATH", "DB_PATH", default=self.data_dir / "coursemind.db")
        return Path(raw).resolve()

    @property
    def video_dir(self) -> Path:
        raw = self._first_env("COURSEMIND_VIDEO_DIR", "NAS_VIDEO_DIR", "VIDEO_ROOT", default=self.project_root / "sample_videos")
        return Path(raw).resolve()

    @property
    def video_dirs(self) -> list[Path]:
        raw = self._first_env("COURSEMIND_VIDEO_DIRS", "NAS_VIDEO_DIRS", "VIDEO_ROOTS", default="")
        if not raw:
            return [self.video_dir]
        # Use semicolon/newline as separators so Windows drive letters like G:/... stay intact.
        parts: list[str] = []
        for chunk in raw.replace("\n", ";").split(";"):
            value = chunk.strip()
            if value:
                parts.append(value)
        if not parts:
            return [self.video_dir]
        return [Path(part).resolve() for part in parts]

    @property
    def transcription_provider(self) -> str:
        raw = os.getenv("ASR_PROVIDER") or os.getenv("TRANSCRIPTION_PROVIDER", "mock")
        return raw.strip().lower()

    @property
    def transcription_api_key(self) -> str:
        return os.getenv("TRANSCRIPTION_API_KEY", "") or self.dashscope_api_key or self.openai_api_key

    @property
    def dashscope_api_key(self) -> str:
        return os.getenv("DASHSCOPE_API_KEY", "")

    @property
    def transcription_base_url(self) -> str:
        raw = os.getenv("TRANSCRIPTION_BASE_URL", "").strip()
        if raw:
            return raw.rstrip("/")
        return self.openai_base_url

    @property
    def openai_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def openai_base_url(self) -> str:
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    @property
    def transcription_model(self) -> str:
        configured = os.getenv("ASR_MODEL") or os.getenv("TRANSCRIPTION_MODEL")
        if configured:
            return configured
        provider = self.transcription_provider
        if provider == "aliyun_dashscope":
            return "fun-asr-realtime"
        if provider == "aliyun_paraformer":
            return "paraformer-realtime-v2"
        if provider in {"funasr", "local_funasr"}:
            return "funasr"
        return "gpt-4o-mini-transcribe"

    @property
    def asr_language(self) -> str:
        return os.getenv("ASR_LANGUAGE", os.getenv("TRANSCRIPTION_LANGUAGE", "zh")).strip() or "zh"

    @property
    def asr_sample_rate(self) -> int:
        return _int_env("ASR_SAMPLE_RATE", 16000)

    @property
    def asr_vocabulary_id(self) -> str:
        return os.getenv("ASR_VOCABULARY_ID", "").strip()

    @property
    def subtitle_correction_enabled(self) -> bool:
        return _bool_env("SUBTITLE_CORRECTION_ENABLED", _bool_env("ENABLE_SUBTITLE_CORRECTION", True))

    @property
    def asr_phrase_id(self) -> str:
        return os.getenv("ASR_PHRASE_ID", "").strip() or self.asr_vocabulary_id

    @property
    def dashscope_websocket_url(self) -> str:
        return os.getenv("DASHSCOPE_WEBSOCKET_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference").strip()

    @property
    def analysis_model(self) -> str:
        return os.getenv("ANALYSIS_MODEL", "gpt-4.1-mini")

    @property
    def summary_provider(self) -> str:
        return os.getenv("SUMMARY_PROVIDER", "mock").strip().lower()

    @property
    def summary_model(self) -> str:
        return os.getenv("SUMMARY_MODEL", self.analysis_model)

    @property
    def summary_api_key(self) -> str:
        return os.getenv("SUMMARY_API_KEY", "")

    @property
    def summary_base_url(self) -> str:
        return os.getenv("SUMMARY_BASE_URL", "").rstrip("/")

    @property
    def chunk_seconds(self) -> int:
        return _int_env("AUDIO_CHUNK_SECONDS", 600)

    @property
    def max_retry(self) -> int:
        return _int_env("MAX_RETRY", 2)

    @property
    def auto_process_new_videos(self) -> bool:
        return _bool_env("AUTO_PROCESS_NEW_VIDEO", _bool_env("AUTO_PROCESS_NEW_VIDEOS", False))

    @property
    def auto_scan(self) -> bool:
        return _bool_env("AUTO_SCAN", False)

    @property
    def scan_interval_seconds(self) -> int:
        return max(30, _int_env("SCAN_INTERVAL_SECONDS", 300))

    @property
    def auto_process_max_per_round(self) -> int:
        return max(1, _int_env("AUTO_PROCESS_MAX_PER_ROUND", 1))

    @property
    def process_concurrency(self) -> int:
        return max(1, _int_env("PROCESS_CONCURRENCY", 1))

    @property
    def retry_delay_seconds(self) -> int:
        return max(1, _int_env("RETRY_DELAY_SECONDS", 30))

    @property
    def scan_recursive(self) -> bool:
        return _bool_env("SCAN_RECURSIVE", True)

    @property
    def video_extensions(self) -> tuple[str, ...]:
        raw = os.getenv("VIDEO_EXTENSIONS", ".mp4,.m4v,.mov,.webm,.mkv,.avi,.flv,.ts,.mts,.m2ts,.wmv,.mpg,.mpeg,.3gp")
        values = []
        for item in raw.split(","):
            value = item.strip().lower()
            if not value:
                continue
            values.append(value if value.startswith(".") else f".{value}")
        return tuple(dict.fromkeys(values)) or (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".flv", ".ts", ".mts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".3gp")

    @property
    def video_exclude_dirs(self) -> tuple[str, ...]:
        raw = os.getenv(
            "VIDEO_EXCLUDE_DIRS",
            ".git,__pycache__,node_modules,coursemind-nas,CourseMind,processed,storage,"
            "CourseMind/processed,CourseMind/logs,CourseMind/backups,#SyncVersion,NAS回传归档,回传附件",
        )
        values: list[str] = []
        for item in raw.split(","):
            value = item.strip().replace("\\", "/").strip("/")
            if value:
                values.append(value.lower())
        return tuple(dict.fromkeys(values))

    @property
    def max_auto_process_minutes_per_day(self) -> int:
        return max(1, _int_env("MAX_AUTO_PROCESS_MINUTES_PER_DAY", 120))

    @property
    def max_single_video_minutes(self) -> int:
        return max(1, _int_env("MAX_SINGLE_VIDEO_MINUTES", 180))

    @property
    def cors_origins(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173")
        return [item.strip() for item in raw.split(",") if item.strip()]


settings = Settings()
