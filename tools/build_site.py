#!/usr/bin/env python3
"""Build docs/ from the page bodies in content/.

The manual is two dozen pages that must agree on their navigation, their
footer, their canonical URLs, their breadcrumbs and their structured data. Hand
-writing that boilerplate twenty-four times is how a site ends up with one page
missing a canonical tag and another still linking to a section that was
renamed - and nothing tells you which.

So each file under content/ carries a small JSON header and a body, and this
script wraps the body in the shared chrome:

    tools/build_site.py            # write docs/
    tools/build_site.py --check    # exit 1 if docs/ is out of date

The output is plain static HTML committed to docs/, which is what GitHub Pages
serves. Edit content/, never docs/.
"""
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
DOCS = ROOT / "docs"

SITE = "https://synomanager.com"
NAME = "Syno Manager"
ORG = "MiyaraHub Technologies LLC"
PLAY = "https://play.google.com/store/apps/details?id=com.synomanager"
APPLE = "https://apps.apple.com/us/app/syno-manager/id6763011668"
MSSTORE = "https://apps.microsoft.com/detail/9P19N2B54N1R"
ISSUES = "https://github.com/MiyaraHub/synomanager/issues"
THEME = "#3b82f6"

NAV = [
    ("Home", "/", "home"),
    ("User Guide", "/guide/", "guide"),
    ("Screenshots", "/#screenshots", None),
    ("Compatibility", "/compatible-nas/", "compat"),
    ("Why switch", "/best-synology-nas-app/", "why"),
    ("Help", "/help/", "help"),
]

FOOTER_LINKS = [
    ("Home", "/"),
    ("User Guide", "/guide/"),
    ("Getting started", "/guide/getting-started/"),
    ("Compatibility", "/compatible-nas/"),
    ("Help", "/help/"),
    ("Privacy", "/privacy/"),
    ("Google Play", PLAY),
    ("App Store", APPLE),
    ("Report a bug", ISSUES),
    ("MiyaraHub", "https://miyarahub.com"),
]

LEGAL = (
    f"&copy; {ORG}. Syno Manager is an independent app and is not affiliated with, "
    "endorsed by, or sponsored by Synology Inc. Synology, DSM, DiskStation, "
    "RackStation, Hyper Backup, Active Backup, Surveillance Station and QuickConnect "
    "are trademarks of Synology Inc."
)

META_RE = re.compile(r"^<!--meta\s*(\{.*?\})\s*-->\s*", re.S)


def store_badges(social=False):
    """All four stores. The app ships on Google Play, the App Store, the Mac
    App Store and the Microsoft Store - the Apple id covers iOS and macOS as a
    universal purchase, which is what the app's own store_links.dart does."""
    out = [
        f'<a href="{PLAY}"><img alt="Get it on Google Play" '
        'src="https://img.shields.io/badge/Google%20Play-Download-414141'
        '?logo=google-play&logoColor=white&style=for-the-badge" /></a>',
        f'<a href="{APPLE}"><img alt="Download on the App Store" '
        'src="https://img.shields.io/badge/App%20Store-Download-0D96F6'
        '?logo=app-store&logoColor=white&style=for-the-badge" /></a>',
        f'<a href="{APPLE}"><img alt="Download on the Mac App Store" '
        'src="https://img.shields.io/badge/Mac%20App%20Store-Download-1D1D1F'
        '?logo=apple&logoColor=white&style=for-the-badge" /></a>',
        f'<a href="{MSSTORE}"><img alt="Get it on the Microsoft Store" '
        'src="https://img.shields.io/badge/Microsoft%20Store-Download-0078D4'
        '?logo=windows&logoColor=white&style=for-the-badge" /></a>',
    ]
    return '<div class="badges">' + "".join(out) + "</div>"


def depth_prefix(meta):
    """Path back to the site root, so assets resolve without a base tag.

    Relative for a normal page. ABSOLUTE for a standalone one, because 404.html
    is served by GitHub Pages in response to a request for any path at any
    depth - so a relative asset path in it resolves against whatever the visitor
    typed and breaks. It is the one page whose own location tells you nothing
    about where the browser thinks it is.
    """
    if meta.get("standalone"):
        return "/"
    parts = [p for p in meta["url"].strip("/").split("/") if p]
    return "../" * len(parts) if parts else ""


def head(meta):
    url = meta["url"]
    pre = depth_prefix(meta)
    canonical = SITE + url
    title = meta["title"]
    desc = meta["description"]
    image = SITE + "/" + meta.get("og_image", "screenshots/dashboard.png")
    kw = meta.get("keywords", "")
    page_type = meta.get("og_type", "website")

    blocks = [
        '<meta charset="UTF-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f"<title>{title}</title>",
        f'<meta name="description" content="{desc}" />',
    ]
    if kw:
        blocks.append(f'<meta name="keywords" content="{kw}" />')
    blocks += [
        f'<meta name="author" content="{ORG}" />',
        (
            '<meta name="robots" content="noindex, follow" />'
            if meta.get("noindex")
            else '<meta name="robots" content="index, follow, max-image-preview:large" />'
        ),
        f'<meta name="theme-color" content="{THEME}" />',
        f'<link rel="canonical" href="{canonical}" />',
        # Search Console verification. The DNS TXT record verifies a Domain
        # property; this meta tag verifies a URL-prefix property. Both carry
        # the same token, and having both means whichever property type was
        # created in the console will verify.
        *(
            [f'<meta name="google-site-verification" content="{meta["google_verification"]}" />']
            if meta.get("google_verification")
            else []
        ),
        f'<meta property="og:title" content="{meta.get("og_title", title)}" />',
        f'<meta property="og:description" content="{meta.get("og_description", desc)}" />',
        f'<meta property="og:type" content="{page_type}" />',
        f'<meta property="og:url" content="{canonical}" />',
        f'<meta property="og:site_name" content="{NAME}" />',
        f'<meta property="og:image" content="{image}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{meta.get("og_title", title)}" />',
        f'<meta name="twitter:description" content="{meta.get("og_description", desc)}" />',
        f'<meta name="twitter:image" content="{image}" />',
        f'<link rel="icon" href="{pre}assets/favicon.ico" sizes="any" />',
        f'<link rel="icon" type="image/png" sizes="32x32" href="{pre}assets/favicon-32.png" />',
        f'<link rel="icon" type="image/png" sizes="48x48" href="{pre}assets/favicon-48.png" />',
        f'<link rel="apple-touch-icon" href="{pre}assets/apple-touch-icon.png" />',
        # Fonts as a head link with preconnect, NOT a CSS @import. An @import
        # inside site.css serialises the whole chain - HTML, then site.css, then
        # the font CSS, then the font files - and blocks rendering the entire
        # time. This starts the font fetch in parallel with the stylesheet.
        '<link rel="preconnect" href="https://fonts.googleapis.com" />',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
        # The store badges are the page's only other origin, and they sit in the
        # hero next to the primary call to action.
        '<link rel="preconnect" href="https://img.shields.io" />',
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        "family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700"
        "&family=JetBrains+Mono:wght@400;500;600&display=swap\" />",
        f'<link rel="stylesheet" href="{pre}assets/site.css" />',
    ]

    # Organization and WebSite go on every page, not just the homepage. Google
    # consolidates them across the site, and having them everywhere means a
    # deep guide page that earns the link still carries the brand entity.
    site_schema = [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": ORG,
            "url": "https://miyarahub.com",
            "logo": f"{SITE}/assets/icon-192.png",
        },
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": NAME,
            "url": SITE + "/",
            "publisher": {"@type": "Organization", "name": ORG},
        },
    ]
    for block in site_schema + meta.get("jsonld", []):
        blocks.append(
            '<script type="application/ld+json">\n'
            + json.dumps(block, indent=2)
            + "\n</script>"
        )

    crumb = meta.get("crumb")
    if crumb:
        items = []
        for i, (label, href) in enumerate(crumb, start=1):
            entry = {"@type": "ListItem", "position": i, "name": label}
            if href:
                entry["item"] = SITE + href
            items.append(entry)
        blocks.append(
            '<script type="application/ld+json">\n'
            + json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": items,
                },
                indent=2,
            )
            + "\n</script>"
        )

    # A guide page is a technical article. Declaring it as one makes it eligible
    # for article rich results and tells Google what the page IS, rather than
    # leaving it to infer from the markup.
    if url.startswith("/guide/") and url != "/guide/":
        blocks.append(
            '<script type="application/ld+json">\n'
            + json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": meta.get("og_title", title),
                    "description": desc,
                    "image": image,
                    "url": canonical,
                    "inLanguage": "en",
                    "isPartOf": {
                        "@type": "WebSite",
                        "name": NAME,
                        "url": SITE + "/",
                    },
                    "author": {"@type": "Organization", "name": ORG},
                    "publisher": {
                        "@type": "Organization",
                        "name": ORG,
                        "logo": {
                            "@type": "ImageObject",
                            "url": f"{SITE}/assets/icon-192.png",
                        },
                    },
                    "about": {
                        "@type": "SoftwareApplication",
                        "name": NAME,
                        "operatingSystem": "Android, iOS, macOS, Windows",
                        "applicationCategory": "UtilitiesApplication",
                    },
                },
                indent=2,
            )
            + "\n</script>"
        )

    faq = meta.get("faq")
    if faq:
        blocks.append(
            '<script type="application/ld+json">\n'
            + json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a},
                        }
                        for q, a in faq
                    ],
                },
                indent=2,
            )
            + "\n</script>"
        )

    return "\n".join(blocks)


def image_size(path: Path):
    """Width and height of a PNG, JPEG, GIF or WebP, without pulling in Pillow.

    Every <img> needs width and height in the markup or the browser cannot
    reserve space for it, the page reflows as each screenshot arrives, and that
    reflow is Cumulative Layout Shift - a Core Web Vitals metric Google ranks
    on. There are 50-odd screenshots on this site and not one of them carried
    dimensions, so this reads them from the file itself. Nobody has to remember.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
        if chunk == b"VP8 ":
            return struct.unpack("<HH", data[26:30])[0] & 0x3FFF, struct.unpack(
                "<HH", data[26:30]
            )[1] & 0x3FFF
        if chunk == b"VP8L":
            b0, b1, b2, b3 = data[21:25]
            bits = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


IMG_TAG = re.compile(r"<img\s+([^>]*?)/?>", re.I)
SRC_ATTR = re.compile(r'src="([^"]+)"', re.I)


def stamp_images(html: str, page_dir: Path) -> str:
    """Give every <img> real dimensions, async decoding and a loading hint.

    The first image on a page is the LCP candidate, so it loads eagerly at high
    priority; everything below it is lazy. Doing this in the builder rather than
    by hand means a new page cannot ship without it.
    """
    # The LCP candidate is the first SCREENSHOT, not the first <img>. The first
    # <img> on every page is the 30px nav logo, and giving that the eager hint
    # while lazy-loading the hero is exactly backwards - it delays the element
    # the metric is actually measuring. The logo is above the fold too, so it
    # is never lazy either; only images below the hero are.
    hero = {"claimed": False}

    def fix(match):
        attrs = match.group(1).strip()
        src = SRC_ATTR.search(attrs)
        if not src:
            return match.group(0)
        target = src.group(1)
        is_shot = "screenshots/" in target
        if not target.startswith(("http://", "https://", "data:", "//")):
            if "width=" not in attrs and "height=" not in attrs:
                # A root-absolute src resolves against the site root, not the
                # directory the page happens to sit in. 404.html uses those.
                base = DOCS if target.startswith("/") else page_dir
                size = image_size((base / target.lstrip("/")).resolve())
                if size:
                    attrs += f' width="{size[0]}" height="{size[1]}"'
        if "decoding=" not in attrs:
            attrs += ' decoding="async"'
        if "loading=" not in attrs and "fetchpriority=" not in attrs:
            if is_shot and not hero["claimed"]:
                hero["claimed"] = True
                attrs += ' fetchpriority="high"'
            elif is_shot:
                attrs += ' loading="lazy"'
        return f"<img {attrs} />"

    return IMG_TAG.sub(fix, html)


def nav_html(meta):
    pre = depth_prefix(meta)
    active = meta.get("nav")
    links = []
    for label, href, key in NAV:
        cls = ' class="active"' if key and key == active else ""
        links.append(f'<a href="{href}"{cls}>{label}</a>')
    links.append('<a href="/#top" class="cta">Download</a>')
    rendered = "\n      ".join(links)
    return f"""<header class="nav">
  <div class="wrap">
    <a class="brand" href="/"><img src="{pre}assets/syno-manager-icon.png" alt="Syno Manager icon" /> {NAME}</a>
    <button class="nav-toggle" aria-label="Menu" onclick="document.getElementById('m').classList.toggle('open')">&#9776;</button>
    <nav id="m">
      {rendered}
    </nav>
  </div>
</header>"""


def crumb_html(meta):
    crumb = meta.get("crumb")
    if not crumb:
        return ""
    parts = []
    for label, href in crumb:
        parts.append(f'<a href="{href}">{label}</a>' if href else label)
    return '<div class="crumb">' + " &rsaquo; ".join(parts) + "</div>"


def footer_html():
    links = "".join(f'<a href="{href}">{label}</a>' for label, href in FOOTER_LINKS)
    return f"""<footer>
  <div class="wrap">
    <div class="flinks">{links}</div>
    <p class="legal">{LEGAL}</p>
  </div>
</footer>"""


def render(path):
    raw = path.read_text(encoding="utf-8")
    m = META_RE.match(raw)
    if not m:
        raise SystemExit(f"{path.relative_to(ROOT)}: missing <!--meta {{...}} --> header")
    meta = json.loads(m.group(1))
    body = raw[m.end() :]

    for field in ("url", "title", "description"):
        if not meta.get(field):
            raise SystemExit(f"{path.relative_to(ROOT)}: meta.{field} is required")
    if not meta["url"].startswith("/") or not meta["url"].endswith("/"):
        raise SystemExit(f"{path.relative_to(ROOT)}: meta.url must start and end with /")

    pre = depth_prefix(meta)
    body = body.replace("{{PRE}}", pre)
    body = body.replace("{{CRUMB}}", crumb_html(meta))
    body = body.replace("{{BADGES}}", store_badges())
    body = body.replace("{{PLAY}}", PLAY)
    body = body.replace("{{APPLE}}", APPLE)
    body = body.replace("{{ISSUES}}", ISSUES)

    page = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        + head(meta)
        + "\n</head>\n<body>\n\n"
        + nav_html(meta)
        + "\n\n"
        + body.strip()
        + "\n\n"
        + footer_html()
        + '\n\n<script defer src="/assets/search.js"></script>\n'
        '<script defer src="/assets/lightbox.js"></script>\n'
        "</body>\n</html>\n"
    )

    # Stamp the WHOLE document, not just the body. The nav is injected after the
    # body is built, so stamping the body alone left the one <img> that appears
    # on every single page - the brand logo - without dimensions.
    dst_dir = DOCS if meta["url"] == "/" else DOCS / meta["url"].strip("/")
    return stamp_images(page, dst_dir), meta


def last_modified(source: Path) -> str:
    """When this page's source last changed, from git.

    NOT date.today(). The sitemap is a build output that `--check` compares
    against the committed copy, so anything derived from the wall clock makes
    that comparison fail the day after it is written - and immediately, if the
    committer and the CI runner are on opposite sides of midnight UTC. That is
    exactly how this check went red: generated on the 5th locally, verified at
    00:05 UTC on the 6th.

    The commit date of the file is both stable and more honest: it is when the
    page actually last changed, which is what lastmod is supposed to mean.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(source)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        stamp = out.stdout.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            return stamp
    except (OSError, subprocess.SubprocessError):
        pass
    # A file git has never seen (a brand-new page, or a checkout without
    # history) has no honest date, so it gets no lastmod rather than a made-up
    # one. Sitemaps treat the element as optional.
    return ""


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def sitemap(pages):
    """A sitemap that also declares every screenshot.

    The image extension is the part most sitemaps leave out. This site is 50-odd
    original screenshots of a real app, which is exactly the material Google
    Images can send traffic for, and an image Google has not been told about is
    an image it has to find by crawling. Each <url> carries the images that page
    actually references, with their alt text as the caption.
    """
    rows = []
    for meta in sorted(pages, key=lambda m: m["url"]):
        priority = meta.get("priority", "0.7")
        stamp = meta.get("lastmod", "")
        lastmod = f"    <lastmod>{stamp}</lastmod>\n" if stamp else ""
        images = ""
        for loc, alt in meta.get("images", []):
            images += (
                "    <image:image>\n"
                f"      <image:loc>{SITE}/{loc}</image:loc>\n"
                f"      <image:title>{xml_escape(alt)}</image:title>\n"
                "    </image:image>\n"
            )
        rows.append(
            "  <url>\n"
            f"    <loc>{SITE}{meta['url']}</loc>\n"
            f"{lastmod}"
            f"    <changefreq>{meta.get('changefreq', 'monthly')}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"{images}"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )


def main():
    check = "--check" in sys.argv
    if not CONTENT.is_dir():
        raise SystemExit("no content/ directory")

    pages, written, stale = [], 0, []
    for src in sorted(CONTENT.rglob("*.html")):
        out, meta = render(src)
        meta["lastmod"] = last_modified(src)
        meta["images"] = sorted(
            {
                (m.group(1), m.group(2))
                for m in re.finditer(
                    r'<img[^>]*?src="[^"]*?(screenshots/[^"]+)"[^>]*?alt="([^"]*)"',
                    out,
                )
            }
            | {
                (m.group(2), m.group(1))
                for m in re.finditer(
                    r'<img[^>]*?alt="([^"]*)"[^>]*?src="[^"]*?(screenshots/[^"]+)"',
                    out,
                )
            }
        )
        pages.append(meta)
        dst = DOCS / meta["url"].strip("/") / "index.html"
        if meta["url"] == "/":
            dst = DOCS / "index.html"
        # A standalone page lands at an exact filename rather than a directory.
        # GitHub Pages serves /404.html for any path it cannot find, and that
        # file has to sit at the root under that name.
        if meta.get("standalone"):
            dst = DOCS / meta["standalone"]
        if check:
            if not dst.exists() or dst.read_text(encoding="utf-8") != out:
                stale.append(meta["url"])
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding="utf-8")
        written += 1

    indexed = [m for m in pages if not m.get('noindex')]
    sm = sitemap(indexed)
    if check:
        current = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
        if current != sm:
            stale.append("/sitemap.xml")
        if stale:
            print("docs/ is out of date. Run tools/build_site.py")
            for s in stale:
                print("  ", s)
            return 1
        print(f"docs/ is current ({len(pages)} pages)")
        return 0

    (DOCS / "sitemap.xml").write_text(sm, encoding="utf-8")
    print(f"wrote {written} pages + sitemap.xml ({len(indexed)} indexed URLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
