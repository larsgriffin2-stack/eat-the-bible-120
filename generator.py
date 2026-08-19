#!/usr/bin/env python3
"""Generate an Apple Podcasts-compatible RSS feed for Eat The Bible 120.

The script is intentionally dependency-light. It uses mutagen when available,
then falls back to ffprobe for MP3 duration metadata.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

TITLE = "Eat The Bible 120"
AUTHOR = "Lars Griffin"
DESCRIPTION = ("Eat The Bible 120 is a daily Bible reading podcast following the "
              "Eat The Bible 120 reading plan. Each episode presents selected readings "
              "from the Old Testament, New Testament, Psalms, and Proverbs, helping "
              "listeners engage with Scripture consistently throughout the year. "
              "This podcast uses the World English Bible (WEB), a public-domain modern "
              "English translation. Visit https://worldenglish.bible/ for more "
              "information and resources.")
CATEGORY = "Religion & Spirituality"
SUBCATEGORY = "Christianity"
DEFAULT_BASE_URL = "https://larsgriffin2-stack.github.io/eat-the-bible-120"
RSS_FILENAME = "rss.xml"


def duration_seconds(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3  # type: ignore
        return float(MP3(path).info.length)
    except Exception:
        probe = shutil.which("ffprobe")
        if not probe:
            return 0.0
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=False,
        )
        try:
            return float(result.stdout.strip())
        except (TypeError, ValueError):
            return 0.0


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def episode_number(path: Path) -> int:
    match = re.search(r"(?:day|episode)[-_ ]?(\d+)", path.stem, re.I)
    return int(match.group(1)) if match else 0


def pub_date(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def text(parent: ET.Element, tag: str, value: str, namespace: str | None = None) -> ET.Element:
    node = ET.SubElement(parent, f"{{{namespace}}}{tag}" if namespace else tag)
    node.text = value
    return node


def generate(root: Path, base_url: str) -> Path:
    audio_dir = root / "audio"
    files = sorted(audio_dir.glob("*.mp3"), key=lambda p: (episode_number(p), p.name.lower()))
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
    })
    channel = ET.SubElement(rss, "channel")
    text(channel, "title", TITLE)
    text(channel, "link", base_url)
    text(channel, "language", "en-us")
    text(channel, "copyright", f"© {datetime.now(timezone.utc).year} {AUTHOR}")
    text(channel, "description", DESCRIPTION)
    text(channel, "lastBuildDate", format_datetime(datetime.now(timezone.utc), usegmt=True))
    text(channel, "generator", "Eat The Bible 120 local RSS generator")
    text(channel, "docs", "https://www.rssboard.org/rss-specification")
    text(channel, "itunes:author", AUTHOR)
    text(channel, "itunes:summary", DESCRIPTION)
    text(channel, "itunes:type", "episodic")
    owner = ET.SubElement(channel, "itunes:owner")
    text(owner, "itunes:name", AUTHOR)
    text(owner, "itunes:email", "larsgriffin2@users.noreply.github.com")
    text(channel, "itunes:explicit", "false")
    category = ET.SubElement(channel, "itunes:category", {"text": CATEGORY})
    ET.SubElement(category, "itunes:category", {"text": SUBCATEGORY})
    # Artwork is intentionally omitted until a cover image is supplied.

    for path in reversed(files):
        episode = ET.SubElement(channel, "item")
        number = episode_number(path)
        title = f"Day {number:03d}" if number else path.stem.replace("-", " ").title()
        pub = pub_date(path)
        audio_url = f"{base_url}/audio/{path.name}"
        text(episode, "title", f"{TITLE} — {title}")
        text(episode, "itunes:title", f"{TITLE} — {title}")
        text(episode, "description", f"Daily reading {title}.")
        text(episode, "itunes:summary", f"Daily reading {title}.")
        text(episode, "pubDate", format_datetime(pub, usegmt=True))
        text(episode, "guid", audio_url)
        text(episode, "link", audio_url)
        text(episode, "itunes:author", AUTHOR)
        text(episode, "itunes:episodeType", "full")
        if number:
            text(episode, "itunes:episode", str(number))
        text(episode, "itunes:explicit", "false")
        ET.SubElement(episode, "enclosure", {
            "url": audio_url,
            "length": str(path.stat().st_size),
            "type": "audio/mpeg",
        })
        text(episode, "itunes:duration", format_duration(duration_seconds(path)))

    output = root / RSS_FILENAME
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    output = generate(args.root.resolve(), args.base_url.rstrip("/"))
    count = len(list((args.root / "audio").glob("*.mp3")))
    print(f"Generated {output} with {count} episode(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
