from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.app import search_wechat_accounts  # noqa: E402


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "人民日报"
    data = search_wechat_accounts(query, 3)
    items = data.get("items") or []
    first = items[0] if items else {}
    print(f"ok={data.get('ok')} count={data.get('count')} first={first.get('nickname')}")
    if not data.get("ok"):
        raise AssertionError(data.get("error") or "wechat search failed")
    if not items:
        raise AssertionError("wechat search returned no items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
