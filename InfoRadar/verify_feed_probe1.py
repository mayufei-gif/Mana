from __future__ import annotations

from fastapi import HTTPException
from web.backend import app


RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Codex RSS Test</title>
    <item>
      <title>First RSS Item</title>
      <link>https://example.com/rss/1</link>
      <pubDate>Tue, 09 Jun 2026 08:30:00 GMT</pubDate>
      <description>rss summary</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Codex Atom Test</title>
  <entry>
    <title>First Atom Item</title>
    <link href="https://example.com/atom/1" />
    <updated>2026-06-09T08:30:00Z</updated>
    <summary>atom summary</summary>
  </entry>
</feed>
"""


def main() -> None:
    rss = app.parse_feed_xml(RSS, "https://example.com/rss.xml")
    atom = app.parse_feed_xml(ATOM, "https://example.com/feed.xml")
    assert rss["title"] == "Codex RSS Test", rss
    assert rss["items"][0]["title"] == "First RSS Item", rss
    assert atom["title"] == "Codex Atom Test", atom
    assert atom["items"][0]["link"] == "https://example.com/atom/1", atom
    try:
        app.validate_public_http_url("http://127.0.0.1/feed.xml")
    except HTTPException as exc:
        assert exc.status_code == 400, exc
    else:
        raise AssertionError("localhost URL should be rejected")
    print("FEED_PARSE_RSS_OK")
    print("FEED_PARSE_ATOM_OK")
    print("FEED_URL_GUARD_OK")


if __name__ == "__main__":
    main()
