
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
USER_ID = os.environ.get("DISCORD_USER_ID", "").strip()
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "8"))
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "72"))

SEEN_FILE = "seen.json"

FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; FeatureScout/1.0; "
    "+https://github.com/null-404436/chatgpt-feature-scout)"
)

DISCORD_AGENT = (
    "DiscordBot "
    "(https://github.com/null-404436/chatgpt-feature-scout, 1.0)"
)


def fetch_url(url, headers=None):
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, headers=request_headers)

    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return set(data) if isinstance(data, list) else set()
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(seen), file, indent=2)


def child_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_date(value):
    if not value:
        return None

    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_feed(source, content):
    root = ET.fromstring(content)
    entries = []

    # Supports RSS and Atom feeds.
    for entry in root.iter():
        tag = entry.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue

        title = child_text(entry, ["title", "{*}title"])
        link = child_text(entry, ["link", "{*}link"])

        if not link:
            for item in entry:
                if item.tag.split("}")[-1].lower() == "link":
                    link = item.attrib.get("href", "")
                    if link:
                        break

        published = (
            child_text(entry, [
                "pubDate", "published", "updated",
                "{*}pubDate", "{*}published", "{*}updated"
            ])
        )

        if not title or not link:
            continue

        entries.append({
            "source": source,
            "title": title,
            "link": link,
            "published": parse_date(published),
        })

    return entries


def get_announcements():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    announcements = []

    for source, url in FEEDS:
        try:
            content = fetch_url(url)
            items = parse_feed(source, content)

            for item in items:
                # If the feed has no date, retain the item as a candidate.
                if item["published"] is None or item["published"] >= cutoff:
                    announcements.append(item)

        except Exception as error:
            print(f"[WARN] Could not read {source} feed: {error}")

    # Newest dated announcements first.
    announcements.sort(
        key=lambda item: item["published"] or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True,
    )

    return announcements


def discord_request(endpoint, method="GET", payload=None):
    url = "https://discord.com/api/v10" + endpoint
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "User-Agent": DISCORD_AGENT,
        "Content-Type": "application/json",
    }

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url, data=body, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        print(f"[ERROR] Discord HTTP {error.code}: {details}")
        raise


def send_dm(message):
    # Open or retrieve a DM channel, then send the message.
    channel = discord_request(
        "/users/@me/channels",
        method="POST",
        payload={"recipient_id": USER_ID},
    )

    channel_id = channel.get("id")
    if not channel_id:
        raise RuntimeError("Discord did not return a DM channel ID.")

    discord_request(
        f"/channels/{channel_id}/messages",
        method="POST",
        payload={"content": message[:2000]},
    )


def main():
    if not BOT_TOKEN or not USER_ID:
        print("[ERROR] DISCORD_BOT_TOKEN or DISCORD_USER_ID is missing.")
        sys.exit(1)

    if not USER_ID.isdigit():
        print("[ERROR] DISCORD_USER_ID must be your numeric Discord user ID.")
        sys.exit(1)

    seen = load_seen()
    announcements = get_announcements()

    fresh = [
        item for item in announcements
        if item["link"] not in seen
    ][:MAX_ITEMS]

    lines = [
        "🤖 **ALEX — FEATURE SCOUT**",
        "",
        "Fresh AI announcements worth a look:",
        "",
    ]

    if not fresh:
        lines.append(
            "No new announcements found in the monitored feeds today."
        )
    else:
        for item in fresh:
            lines.extend([
                f"**{item['source']}** · {item['title']}",
                item["link"],
                "",
            ])

    lines.extend([
        "Tip: announcements can roll out gradually, so a feature may not "
        "be available to every account yet."
    ])

    # Report the actual Discord error if the DM cannot be opened or sent.
    try:
        send_dm("\n".join(lines))
        print(f"[OK] Sent a DM to Discord user ID {USER_ID}.")
    except Exception as error:
        print(f"[ERROR] Could not send Discord DM: {error}")
        sys.exit(1)

    for item in fresh:
        seen.add(item["link"])

    save_seen(seen)
    print(f"[OK] Checked feeds; sent {len(fresh)} new announcement(s).")


if __name__ == "__main__":
    main()
