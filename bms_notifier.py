import os
import re
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BOOKMYSHOW_URL = "https://in.bookmyshow.com/movies/pune/project-hail-mary/buytickets/ET00481564/20260328"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "state.txt"

DAY_PATTERN = re.compile(r"\b(SAT|SUN|MON|TUE|WED|THU|FRI)\b\s*\d{1,2}\b", re.IGNORECASE)


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=20)


def load_state():
    path = Path(STATE_FILE)
    if not path.exists():
        return {}
    state = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        day_text, disabled = line.split("|", 1)
        state[day_text.strip()] = disabled.strip().lower() == "true"
    return state


def save_state(state):
    lines = [f"{day}|{str(disabled)}" for day, disabled in state.items()]
    Path(STATE_FILE).write_text("\n".join(lines) + "\n")


def get_day_candidates(page):
    # Nuclear option: scan ALL page text
    page_text = page.inner_text("body").lower()
    print("Page text preview:", page_text[:300] + "...")
    
    matches = DAY_PATTERN.findall(page_text)
    day_set = set()
    
    for match in matches:
        day = match.upper()
        if day not in day_set:
            day_set.add(day)
    
    candidates = [(day, None) for day in sorted(day_set)]
    print(f"TEXT SCAN found {len(candidates)} unique days: {[d for d, _ in candidates]}")
    return candidates


def main():
    previous_state = load_state()
    current_state = {}
    print("Previous state:", previous_state)

    print(f"Checking: {BOOKMYSHOW_URL}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        page.goto(BOOKMYSHOW_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(10000)

        print("Page title:", page.title()[:100])

        candidates = get_day_candidates(page)
        
        # Assume all found days are available (conservative)
        for text, _ in candidates:
            current_state[text] = False  # assume available if found

        browser.close()

    newly_available = []
    all_current_days = set(current_state.keys())
    
    # Alert for ANY days found that were previously marked unavailable
    for day_text in all_current_days:
        prev_state = previous_state.get(day_text, True)  # default unavailable
        if prev_state:  # was unavailable before
            newly_available.append(day_text)

    save_state(current_state)

    if newly_available:
        msg = "🚨 BookMyShow alert: Days now visible:\n" + "\n".join(newly_available) + f"\n\n{BOOKMYSHOW_URL}"
        send_telegram_message(msg)
        print("✅ Alert sent for:", newly_available)
    else:
        print("ℹ️ No new days detected.")


if __name__ == "__main__":
    main()
