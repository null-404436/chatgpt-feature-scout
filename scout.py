#!/usr/bin/env python3
"""ChatGPT Feature Scout: collect recent AI announcements and DM a Discord user."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEEN_FILE = ROOT / "seen.json"

FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Anthropic", "https://www.anthropic.com/news/rss.xml"),
    ("Google AI Blog", "https://blog.research.google/feeds/posts/default?alt=rss"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
]

INTEREST_WORDS = re.compile(
    r"\b(new|launch|introduc|release|available|rollout|update|model|chatgpt|"
    r"agent|image|video|voice|audio|reason|coding|developer|tool|assistant|"
    r"open.?source|ai|artificial intelligence|api|robot|research|benchmark|"
    r"generat|vision|multimodal|automation|feature|capabilit)\w*\b",
    re.IGNORECASE,
)
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "8"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "72"))


def http_get(url, headers=None):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ChatGPT-Feature-Scout/1.0 (+personal hobby project)", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element, names):
    for child in list(element):
        if local_name(child.tag) in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def item_link(item):
    for child in list(item):
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
        if local_name(child.tag) == "guid" and child.text:
            value = child.text.strip()
            if value.startswith("http"):
                return value
    return ""


def parse_feed(source, url):
    try:
        data = http_get(url)
        root = ET.fromstring(data)
    except Exception as exc:
        print(f"[WARN] Could not read {source} feed: {exc}")
        return []

    found = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        title = child_text(item, {"title"}) or "Untitled announcement"
        link = item_link(item)
        summary = child_text(item, {"description", "summary", "content", "encoded"})
        date_text = child_text(item, {"pubdate", "published", "updated", "date", "issued"})
        published = parse_date(date_text)
        # If an item has no date, skip it rather than guessing.
        if not link or not published:
            continue
        plain_summary = re.sub(r"<[^>]+>", " ", summary)
        plain_summary = re.sub(r"\s+", " ", plain_summary).strip()
        found.append({
            "source": source,
            "title": re.sub(r"\s+", " ", title).strip(),
            "link": link,
            "summary": plain_summary[:500],
            "published": published.isoformat(),
        })
    # A feed can sometimes expose duplicate entries; de-duplicate by URL.
    unique = {}
    for item in found:
        unique[item["link"]] = item
    return list(unique.values())


def load_seen():
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"links": []}


def save_seen(links):
    SEEN_FILE.write_text(
        json.dumps({"links": sorted(set(links))}, indent=2),
        encoding="utf-8",
    )


def discord_dm(message):
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    user_id = os.getenv("DISCORD_USER_ID", "").strip()
    if not token or not user_id:
        raise RuntimeError("Set DISCORD_BOT_TOKEN and DISCORD_USER_ID before sending.")
    api = "https://discord.com/api/v10"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps({"recipient_id": user_id}).encode("utf-8")
    request = urllib.request.Request(
        f"{api}/users/@me/channels", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            channel = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            "Could not open a DM. Check the bot token, user ID, and that you and the bot "
            f"share a Discord server. Discord said: {detail}"
        ) from exc

    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)] or ["No new items."]
    for chunk in chunks:
        payload = json.dumps({"content": chunk, "allowed_mentions": {"parse": []}}).encode("utf-8")
        req = urllib.request.Request(
            f"{api}/channels/{channel['id']}/messages",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            response.read()


def main():
    dry_run = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"}
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)
    seen = set(load_seen().get("links", []))
    all_items = []
    for source, url in FEEDS:
        all_items.extend(parse_feed(source, url))

    candidates = []
    for item in all_items:
        published = parse_date(item["published"])
        if not published or published < cutoff or item["link"] in seen:
            continue
        searchable = f"{item['title']} {item['summary']}"
        if INTEREST_WORDS.search(searchable):
            candidates.append(item)

    candidates.sort(key=lambda item: item["published"], reverse=True)
    candidates = candidates[:MAX_ITEMS]

    if not candidates:
        print("No new recent announcements matched the filters.")
        # Mark older entries as seen too, so old items do not resurface later.
        save_seen(seen | {item["link"] for item in all_items})
        return

    lines = ["🤖 **FEATURE SCOUT — AI discoveries**", "Fresh announcements worth a look:\n"]
    for item in candidates:
        lines.append(f"**{item['source']}** · {item['title']}\n{item['link']}")
        if item["summary"]:
            lines.append(item["summary"][:220] + ("…" if len(item["summary"]) > 220 else ""))
        lines.append("")
    lines.append("Tip: announcements can roll out gradually, so a feature may not be available to every account yet.")

    message = "\n".join(lines)
    print(message)
    if not dry_run:
        discord_dm(message)
        print("Discord DM sent.")

    # Store everything seen in the feeds so old entries do not repeat.
    save_seen(seen | {item["link"] for item in all_items})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
