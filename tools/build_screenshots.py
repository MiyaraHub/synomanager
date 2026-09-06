#!/usr/bin/env python3
"""Turn the raw device captures in .raw/ into the framed shots the site ships.

One manifest, one command, so the whole screenshot set is reproducible and the
privacy pass is written down rather than remembered:

    tools/build_screenshots.py

Each entry names the raw capture, the name it ships under, and the regions to
destroy before framing. A region is given in RAW capture coordinates
(1344x2992 on the Pixel 10 Pro XL), which is what measuring off the capture
gives you.

The BLUR list is the privacy pass. It exists because the app is pointed at a
real NAS, and several screens draw things that must not reach a public page:
a routable public IP, a DDNS hostname that resolves to somebody's front door,
real names, personal email addresses. Internal RFC1918 addresses are
deliberately NOT blurred - they identify nothing outside the LAN they live on,
and a manual that hides them teaches the reader less.

Rather than the raw captures, this file is the reviewable artifact: a reader
can see exactly what was removed from which shot and why.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".raw"
OUT = ROOT / "docs" / "screenshots"
BLUR = ROOT / "tools" / "blur_regions.py"
FRAME = ROOT / "tools" / "frame_shot.py"
STAGE = ROOT / ".raw" / "_staged"

# (raw name, shipped name, [regions to blur])
SHOTS = [
    # Home
    ("dashboard", "dashboard", [(175, 278, 445, 322)]),
    ("dashboard-edit", "dashboard-customize", []),
    ("dash1", "dashboard-cards", []),
    # System
    ("system-health", "system-health", []),
    ("system-health2", "system-cooling", []),
    ("system-resources", "system-resources", []),
    ("customize-views", "customize-views", []),
    # Storage
    ("storage-volumes", "storage-volumes", []),
    ("storage-disk-health", "storage-disk-health", []),
    ("storage-external", "storage-external", []),
    # Network - the public IP and the DDNS hostname are the two values on this
    # site that would let a stranger reach somebody's NAS. Both go.
    ("network", "network", [(375, 1025, 595, 1158), (200, 1352, 402, 1398)]),
    # The Connections landing view shows counts and the auto-block policy, not
    # who is signed in - the names live one level deeper and are not shipped.
    ("network-connections", "network-connections", []),
    ("network-services", "network-services", []),
    ("network-vpn", "network-vpn", []),
    ("network-ddns", "network-ddns", [(1000, 845, 1290, 910), (125, 915, 440, 975)]),
    # Files
    ("files-station", "files-station", [(170, 1548, 400, 1612)]),
    ("files-shared", "files-shared", [(170, 1990, 560, 2160)]),
    ("files-downloads", "downloads", []),
    ("files-download-settings", "download-settings", []),
    ("files-download-add", "download-add", []),
    # EVERY notebook title, not a chosen few. The first pass blurred three that
    # looked personal and left the rest, which shipped two notebooks of the
    # owner's work material from a former employer to a public page. Picking
    # which titles are sensitive is a judgement call made from outside somebody
    # else's life, and it was wrong. The note counts, the icons, the delete
    # control and the whole layout still read - the titles are not what this
    # screenshot documents.
    (
        "files-notes",
        "notes",
        [
            (195, 1118, 645, 1175),
            (195, 1320, 645, 1377),
            (195, 1521, 645, 1578),
            (195, 1723, 645, 1780),
            (195, 1924, 645, 1981),
            (195, 2126, 645, 2183),
            (195, 2327, 645, 2384),
            (195, 2529, 645, 2586),
            # the ninth row is cut off by the fold and still showed a title
            (195, 2725, 645, 2800),
        ],
    ),
    ("files-office", "office", []),
    ("files-contacts", "contacts", [(215, 1005, 680, 1070)]),
    # Apps
    ("apps-packages", "packages", []),
    ("apps-search-install", "packages-search", []),
    ("apps-install-confirm", "packages-install", []),
    ("apps-docker", "docker", []),
    ("apps-projects", "docker-projects", []),
    # Media
    ("media-photos", "photos", []),
    ("media-drive", "drive", []),
    ("media-cameras", "cameras", []),
    ("media-camera-live", "camera-live", []),
    # Backup
    ("backup-hyper", "backup-hyper", []),
    ("backup-active", "backup-active", [(200, 1440, 402, 1492), (200, 1815, 402, 1867),
     (200, 2190, 402, 2242), (200, 2565, 402, 2617)]),
    # Control Panel - real names and personal email addresses.
    (
        "control-users",
        "users",
        [(210, 985, 620, 1140), (210, 1540, 620, 1600), (210, 1700, 620, 1850)],
    ),
    ("control-tasks", "tasks", []),
    ("control-power", "ups", []),
    # Assistant
    ("assistant", "assistant", []),
    ("assistant-how", "assistant-how", []),
    # Setup and settings
    ("manage-nas", "manage-nas", [(470, 745, 670, 805), (230, 655, 515, 705), (245, 740, 462, 812)]),
    ("manage-nas-menu", "manage-nas-menu", [(470, 745, 670, 805), (230, 655, 515, 705), (245, 740, 462, 812), (128, 2228, 428, 2275)]),
    ("add-nas", "add-nas", []),
    ("wake-devices", "wake-devices", []),
    ("settings-main", "settings-main", []),
    ("settings-help", "settings-help", []),
    ("settings-theme", "settings-theme", []),
    ("settings-categories", "settings-categories", []),
    ("settings-nav", "settings-nav", []),
    ("settings-launch", "settings-launch", []),
    ("settings-cardview", "settings-cardview", []),
    ("settings-backup", "settings-backup", []),
    ("about", "about", []),
    # The accent showcase: the same dashboard in each named accent, so a reader
    # can see that the accent drives the whole app - card borders, icons, the
    # brand line and the bottom bar - rather than just a button tint.
    ("accent-cyan", "accent-cyan", [(175, 278, 445, 322)]),
    ("accent-purple", "accent-purple", [(175, 278, 445, 322)]),
    ("accent-green", "accent-green", [(175, 278, 445, 322)]),
    ("accent-amber", "accent-amber", [(175, 278, 445, 322)]),
    ("accent-pink", "accent-pink", [(175, 278, 445, 322)]),
    # The launcher's own widget picker, which is where the three widgets are
    # named and sized. Captured on the same device family as everything else.
    ("widget-picker", "widget-picker", []),
]


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"{' '.join(str(c) for c in cmd)}\n{result.stdout}{result.stderr}")
    return result.stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    missing = [s for s, _, _ in SHOTS if not (RAW / f"{s}.png").exists()]
    if missing:
        sys.exit("missing raw captures: " + ", ".join(missing))

    blurred = 0
    for raw, ship, regions in SHOTS:
        src = RAW / f"{raw}.png"
        if regions:
            staged = STAGE / f"{raw}.png"
            run(
                [sys.executable, str(BLUR), str(src), str(staged)]
                + [",".join(str(v) for v in r) for r in regions]
            )
            src = staged
            blurred += 1
        run([sys.executable, str(FRAME), str(src), str(OUT / f"{ship}.webp")])
        print(f"  {ship}")

    print(f"\n{len(SHOTS)} shots, {blurred} carrying a privacy pass -> {OUT}")


if __name__ == "__main__":
    main()
