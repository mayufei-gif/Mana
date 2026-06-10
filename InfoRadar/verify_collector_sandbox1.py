from __future__ import annotations

import shutil
from pathlib import Path

from web.backend import app


def main() -> None:
    item = app.upsert_collector_adapter(
        {
            "platform": "采集器沙箱测试",
            "name": "deepset-ai/haystack",
            "repo_url": "https://github.com/deepset-ai/haystack",
            "source": "verify_collector_sandbox1",
            "status": "候选",
            "notes": "temporary sandbox execution gate test",
        }
    )
    fingerprint = item.get("fingerprint")
    manual_fingerprint = ""
    run_root = app.FOLO_COLLECTOR_RUNS_DIR / str(fingerprint)
    assert fingerprint, item
    try:
        reviewed = app.review_collector_adapter(str(fingerprint)).get("item") or {}
        assert str(reviewed.get("status") or "").startswith("reviewed-"), reviewed
        allowed = app.allow_collector_adapter_execution(str(fingerprint)).get("allowed") or {}
        assert allowed.get("allow_execute") is True, allowed
        assert allowed.get("runner") == "github-repo-metadata-snapshot", allowed
        assert allowed.get("execution_scope") == "builtin-runner-only", allowed
        data = app.run_collector_adapter_execution(str(fingerprint))
        run = data.get("run") or {}
        assert run.get("ok") is True, run
        assert run.get("collected_count") == 1, run
        assert run.get("execution_scope") == "builtin-runner-only", run
        sandbox_dir = Path(str(run.get("sandbox_dir") or ""))
        assert sandbox_dir.exists(), run
        assert (sandbox_dir / "result.json").exists(), run
        manual_entry = run.get("manual_entry") or {}
        manual_fingerprint = str(manual_entry.get("fingerprint") or "")
        assert manual_fingerprint, manual_entry
        print("COLLECTOR_SANDBOX_EXECUTION_OK")
        print(f"runner={run.get('runner')}")
        print(f"sandbox_dir={run.get('sandbox_dir')}")
        print(f"manual_entry={manual_entry.get('name')}")
    finally:
        adapter_rows = [row for row in app.read_collector_adapters() if row.get("fingerprint") != fingerprint]
        app.write_collector_adapters(adapter_rows)
        whitelist_rows = [row for row in app.read_collector_whitelist() if row.get("fingerprint") != fingerprint]
        app.write_collector_whitelist(whitelist_rows)
        if manual_fingerprint:
            manual_rows = [row for row in app.read_manual_hive_entries() if row.get("fingerprint") != manual_fingerprint]
            app.write_manual_hive_entries(manual_rows)
        if run_root.exists() and run_root.resolve().is_relative_to(app.FOLO_COLLECTOR_RUNS_DIR.resolve()):
            shutil.rmtree(run_root)
        print("COLLECTOR_SANDBOX_TEST_CLEANED")


if __name__ == "__main__":
    main()
