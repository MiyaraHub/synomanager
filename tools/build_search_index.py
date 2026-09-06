#!/usr/bin/env python3
"""Rebuild docs/assets/search-index.json from the pages themselves.

The index was hand-maintained, which is why it drifted: four guide pages
shipped without entries and the site's own search could not find them. Every
field here already exists in each page's head, so generating it means a new
page is searchable the moment it has a title and a description - and a page
that loses one fails this script loudly instead of silently vanishing from
search.

    tools/build_search_index.py           # rewrite the index
    tools/build_search_index.py --check   # exit 1 if it is out of date

Shape, unchanged from the hand-written file:
    t  title            <title>, with the " | Syno Manager" suffix trimmed
    u  url              directory path with a trailing slash
    d  description      <meta name="description">, trimmed
    k  keyword haystack lowercased title + description + keywords
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
INDEX = DOCS / "assets" / "search-index.json"

SUFFIX = re.compile(r"\s*\|\s*Syno Manager\s*$")
DESC_CAP = 160


def meta(html: str, name: str) -> str:
    m = re.search(
        r'<meta\s+name=["\']%s["\']\s+content=["\'](.*?)["\']\s*/?>' % name,
        html,
        re.S | re.I,
    )
    return " ".join(m.group(1).split()) if m else ""


def title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not m:
        return ""
    return SUFFIX.sub("", " ".join(m.group(1).split()))


def url_of(path: Path) -> str:
    rel = path.relative_to(DOCS).parent.as_posix()
    return "/" if rel == "." else f"/{rel}/"


def build() -> list:
    entries = []
    for page in sorted(DOCS.rglob("index.html")):
        html = page.read_text(encoding="utf-8")
        if 'name="robots"' in html and "noindex" in html:
            continue
        title, desc = title_of(html), meta(html, "description")
        if not title or not desc:
            raise SystemExit(
                f"{page.relative_to(ROOT)} has no {'title' if not title else 'description'}. "
                "Both are required - a page without them is invisible to search "
                "and to every crawler."
            )
        entries.append(
            {
                "t": title,
                "u": url_of(page),
                "d": desc[:DESC_CAP],
                "k": " ".join(
                    f"{title} {desc} {meta(html, 'keywords')}".lower().split()
                ),
            }
        )
    entries.sort(key=lambda e: e["u"])
    return entries


def main() -> int:
    entries = build()
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))

    if "--check" in sys.argv:
        current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if current.strip() != payload:
            have = json.loads(current) if current.strip() else []
            missing = {e["u"] for e in entries} - {e["u"] for e in have}
            stale = {e["u"] for e in have} - {e["u"] for e in entries}
            print("search-index.json is out of date. Run tools/build_search_index.py")
            if missing:
                print("  missing:", ", ".join(sorted(missing)))
            if stale:
                print("  stale:  ", ", ".join(sorted(stale)))
            return 1
        print(f"search-index.json is current ({len(entries)} pages)")
        return 0

    INDEX.write_text(payload, encoding="utf-8")
    print(f"wrote {INDEX.relative_to(ROOT)} - {len(entries)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
