import requests
import time
import json
import os
from html.parser import HTMLParser

# ── CONFIG ──────────────────────────────────────────────
BOT_TOKEN   = "8850438218:AAHJruf1c-QaZAdbICcXv-W60F56RLEEDnM"
CHAT_ID     = "-1001425868315"   # e.g. -1001234567890
CHECK_URL   = "https://pitsport.xyz/live-now"
CHECK_EVERY = 60
STATE_FILE  = "seen_streams.json"
# ────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    # state format: { "stream_url": message_id, ... }
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_live_streams():
    try:
        r = requests.get(CHECK_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text

        # ── Only look at the LIVE section, stop before Upcoming ──
        live_marker     = html.lower().find("live now")
        upcoming_marker = html.lower().find("upcoming")

        if live_marker == -1:
            print("[INFO] No live section found on page")
            return []

        if upcoming_marker != -1 and upcoming_marker > live_marker:
            live_html = html[live_marker:upcoming_marker]
        else:
            live_html = html[live_marker:]

        # ── Parse stream links from live section only ──
        class LiveParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.streams = []
                self.capture_title = False
                self.current_title = ""
                self.current_link = ""

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "a" and "href" in attrs:
                    href = attrs["href"]
                    if "/watch/" in href or "/stream/" in href or "/live/" in href:
                        self.current_link = href
                        self.capture_title = True
                        self.current_title = ""

            def handle_data(self, data):
                if self.capture_title and data.strip():
                    self.current_title += data.strip() + " "

            def handle_endtag(self, tag):
                if tag == "a" and self.capture_title:
                    title = self.current_title.strip()
                    if title and self.current_link:
                        self.streams.append({
                            "title": title,
                            "link": self.current_link
                        })
                    self.capture_title = False
                    self.current_title = ""
                    self.current_link = ""

        parser = LiveParser()
        parser.feed(live_html)
        return parser.streams

    except Exception as e:
        print(f"[ERROR] Could not fetch page: {e}")
        return []

def clean_title(title):
    for noise in ["| PitSport", "| Pitsport", "PitSport", "Pitsport", "Watch", "Stream", "HD"]:
        title = title.replace(noise, "")
    return title.strip(" |-")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        message_id = data["result"]["message_id"]
        print(f"[SENT] Message ID {message_id} — {message[:60]}")
        return message_id
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return None

def delete_telegram(message_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    payload = {
        "chat_id": CHAT_ID,
        "message_id": message_id
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"[DELETED] Message ID {message_id} removed from group")
    except Exception as e:
        print(f"[ERROR] Could not delete message {message_id}: {e}")

def main():
    print("🏁 TorqueLive Bot started...")
    # state = { "stream_url": message_id }
    state = load_state()

    while True:
        print(f"[CHECK] Scanning for live streams...")
        streams = get_live_streams()
        live_urls = {s["link"] for s in streams}
        print(f"[INFO] Found {len(streams)} live stream(s)")

        # ── Post new streams ──
        for stream in streams:
            uid = stream["link"]
            if uid not in state:
                title = clean_title(stream["title"])
                msg = (
                    f"🔴 <b>Live Now in TorqueLive!</b>\n\n"
                    f"🏎️ {title}"
                )
                message_id = send_telegram(msg)
                if message_id:
                    state[uid] = message_id
                    save_state(state)

        # ── Delete messages for streams that have ended ──
        ended = [url for url in list(state.keys()) if url not in live_urls]
        for url in ended:
            message_id = state.pop(url)
            print(f"[INFO] Stream ended, deleting message ID {message_id}")
            delete_telegram(message_id)
            save_state(state)

        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
