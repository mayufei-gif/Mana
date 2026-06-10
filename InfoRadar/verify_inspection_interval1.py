from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from web.backend import file_index


def main() -> None:
    original = file_index.INSPECTION_INTERVAL_STATE_JSON
    temp_path = Path(f"/tmp/inforadar-inspection-interval-{uuid4().hex}.json")
    try:
        file_index.INSPECTION_INTERVAL_STATE_JSON = temp_path
        first = file_index.inspection_interval_status("2026-06-09T08:30:00")
        second = file_index.inspection_interval_status("2026-06-09T11:30:00")
        assert first["current"] == "2026-06-09T08:30:00", first
        assert second["previous"] == "2026-06-09T08:30:00", second
        assert second["current"] == "2026-06-09T11:30:00", second
        data = file_index.latest_status()
        health = data.get("health") or {}
        assert "inspection_interval_label" in health, health
        print("INSPECTION_INTERVAL_STATE_OK")
        print(f"label={health.get('inspection_interval_label')}")
    finally:
        file_index.INSPECTION_INTERVAL_STATE_JSON = original
        temp_path.unlink(missing_ok=True)
        print("INSPECTION_INTERVAL_TEST_CLEANED")


if __name__ == "__main__":
    main()
