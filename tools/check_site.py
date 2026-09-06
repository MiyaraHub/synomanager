#!/usr/bin/env python3
"""Refuse to ship a broken or leaky site.

Four checks, all deterministic, all cheap enough to run before every push:

  links       every internal href resolves to something that was actually built
  images      every referenced screenshot exists on disk
  dashes      no em dash or en dash anywhere - hyphens only, brand voice rule
  leaks       no routable address, hostname or personal detail from the rig

The leak check is the one with teeth. Screenshots are blurred by a manifest in
build_screenshots.py, but the same values can reach a page through prose, an
alt attribute or a meta description, where no blur applies. This greps the
built HTML for the specific strings the capture device really had, so a value
that escaped the image pass is caught before it is public rather than after.

    tools/check_site.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Values that were genuinely on screen while the screenshots were taken. Adding
# one here is how a new rig detail becomes permanently un-shippable.
FORBIDDEN = [
    "38.190.117.245",
    "up.miyarahub.com",
    "meir.miyara@gmail.com",
    "donna.miyara@gmail.com",
    "Donna Miyara",
    "Meir Miyara",
    "DonnaShare",
]

# Both the literal character and every way of spelling it as an entity. The
# entity form was the gap: it renders as an em dash on the page but does not
# match a search for the character, so a guard that only looks for "—" passes a
# document that shows one.
DASHES = {
    "\u2014": "em dash",
    "\u2013": "en dash",
    "&mdash;": "em dash (entity)",
    "&ndash;": "en dash (entity)",
    "&#8212;": "em dash (numeric entity)",
    "&#8211;": "en dash (numeric entity)",
    "&#x2014;": "em dash (hex entity)",
    "&#x2013;": "en dash (hex entity)",
}

# Google truncates a title past roughly 60 characters and a description past
# roughly 160 in the result snippet, and a truncated snippet is a worse reason
# to click. Every one of the 26 pages was over both limits when this was first
# measured, so the limits live here now rather than in anyone's memory.
TITLE_MAX = 60
DESC_MAX = 160

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
DESC_RE = re.compile(r'<meta name="description" content="(.*?)"', re.S | re.I)
CANON_RE = re.compile(r'<link rel="canonical"', re.I)
# Every image needs intrinsic dimensions or the page reflows as it loads, which
# is Cumulative Layout Shift - a ranking signal. Remote images cannot be
# measured at build time, so only local ones are required to carry them.
LOCAL_IMG_RE = re.compile(r'<img\s+(?![^>]*src="(?:https?:)?//)[^>]*?>', re.I)

HREF = re.compile(r'href="(/[^"#?]*)', re.I)
IMG = re.compile(r'src="([^"]+\.(?:png|jpg|jpeg|webp|svg|ico))"', re.I)
SRC_ATTR = re.compile(r'src="([^"]+)"', re.I)


def built_paths():
    out = set()
    for p in DOCS.rglob("*"):
        if p.is_file():
            rel = "/" + p.relative_to(DOCS).as_posix()
            out.add(rel)
            if p.name == "index.html":
                out.add(rel[: -len("index.html")])
    return out


def main():
    if not DOCS.is_dir():
        sys.exit("no docs/ - run tools/build_site.py first")

    known = built_paths()
    pages = sorted(DOCS.rglob("*.html"))
    problems = []

    for page in pages:
        rel = page.relative_to(ROOT)
        html = page.read_text(encoding="utf-8")

        for href in HREF.findall(html):
            target = href if href.endswith("/") or "." in Path(href).name else href + "/"
            if target not in known and href not in known:
                problems.append(f"{rel}: dead internal link -> {href}")

        for src in IMG.findall(html):
            if src.startswith(("http", "//")):
                continue
            # Root-absolute paths resolve against docs/, not against the page's
            # own directory - 404.html has to use those, because it is served
            # for a request to any path at any depth.
            base = DOCS if src.startswith("/") else page.parent
            resolved = (base / src.lstrip("/")).resolve()
            if not resolved.is_file():
                problems.append(f"{rel}: missing image -> {src}")

        for ch, name in DASHES.items():
            if ch in html:
                line = html[: html.index(ch)].count("\n") + 1
                problems.append(f"{rel}:{line}: {name} - hyphens only")

        for secret in FORBIDDEN:
            if secret in html:
                problems.append(f"{rel}: LEAK - contains {secret!r}")

        title = TITLE_RE.search(html)
        if not title:
            problems.append(f"{rel}: no <title>")
        elif len(title.group(1)) > TITLE_MAX:
            problems.append(
                f"{rel}: title is {len(title.group(1))} chars, over {TITLE_MAX} "
                "- Google will truncate it"
            )

        desc = DESC_RE.search(html)
        if not desc:
            problems.append(f"{rel}: no meta description")
        elif len(desc.group(1)) > DESC_MAX:
            problems.append(
                f"{rel}: description is {len(desc.group(1))} chars, over "
                f"{DESC_MAX} - Google will truncate it"
            )

        if not CANON_RE.search(html):
            problems.append(f"{rel}: no canonical link")

        for tag in LOCAL_IMG_RE.findall(html):
            if 'src=""' in tag:
                continue  # the lightbox placeholder, filled in by script
            if "width=" not in tag or "height=" not in tag:
                src = SRC_ATTR.search(tag)
                problems.append(
                    f"{rel}: <img> without width/height -> "
                    f"{src.group(1) if src else tag[:60]} (layout shift)"
                )

    for other in list(DOCS.rglob("*.xml")) + list(DOCS.rglob("*.json")) + list(
        DOCS.rglob("*.txt")
    ):
        text = other.read_text(encoding="utf-8", errors="replace")
        rel = other.relative_to(ROOT)
        for ch, name in DASHES.items():
            if ch in text:
                problems.append(f"{rel}: {name} - hyphens only")
        for secret in FORBIDDEN:
            if secret in text:
                problems.append(f"{rel}: LEAK - contains {secret!r}")

    # A screenshot that is built but never placed on a page is invisible. Seven
    # of them shipped that way - Launch Behavior, Default Card View, the main
    # Settings screen, VPN, the package search, live camera view and the card
    # grid were all captured, framed, committed and then documented in prose
    # with no picture. The manifest said the work was done; nothing said the
    # picture never reached a reader.
    shots_dir = DOCS / "screenshots"
    if shots_dir.is_dir():
        referenced = set()
        for page in pages:
            referenced |= set(
                re.findall(r"screenshots/([a-z0-9-]+\.webp)", page.read_text(encoding="utf-8"))
            )
        for shot in sorted(f.name for f in shots_dir.iterdir() if f.is_file()):
            if shot not in referenced:
                problems.append(
                    f"docs/screenshots/{shot}: built but shown on no page"
                )

    # The stamped width/height attributes and this CSS rule are one mechanism,
    # not two. Stamping dimensions without `height:auto` renders every
    # screenshot at its full intrinsic height inside whatever box the layout
    # gives it - a 1324x2644 shot in a 300px column becomes 300 by 2644. That
    # shipped, and the lightbox hid it, because .lb img sets height:auto of its
    # own accord. Checked here so the pair cannot be separated again.
    css = DOCS / "assets" / "site.css"
    if css.is_file():
        base = re.search(r"^img\{([^}]*)\}", css.read_text(), re.M)
        if not base:
            problems.append("assets/site.css: no base img{} rule")
        elif "height:auto" not in base.group(1).replace(" ", ""):
            problems.append(
                "assets/site.css: base img{} rule has no height:auto - every "
                "stamped width/height attribute will stretch its image"
            )

    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  " + p)
        return 1

    print(f"ok: {len(pages)} pages, links resolve, no stray dashes, no leaks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
