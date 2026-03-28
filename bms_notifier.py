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


def is_disabled(locator):
    try:
        disabled_attr = locator.get_attribute("disabled")
        aria_disabled = locator.get_attribute("aria-disabled")
        class_attr = locator.get_attribute("class") or ""
        style_attr = locator.get_attribute("style") or ""

        if disabled_attr is not None:
            return True
        if aria_disabled and aria_disabled.lower() == "true":
            return True
        if "disabled" in class_attr.lower():
            return True
        if "pointer-events: none" in style_attr.lower():
            return True
        if "opacity: 0.5" in style_attr.lower():
            return True
        return False
    except:
        return False


def get_day_candidates(page):
    selectors = [
        '[role="tab"]',
        'button:has-text("SAT"), button:has-text("SUN"), button:has-text("MON")',
        '[data-testid*="date"], .date-tab, .datepicker-tab',
        '.show-date-tab, [class*="date-tab"]'
    ]
    
    candidates = []
    
    for selector in selectors:
        try:
            tabs = page.locator(selector)
            count = tabs.count()
            for i in range(count):
                loc = tabs.nth(i)
                text = loc.inner_text().strip().upper()
                if DAY_PATTERN.search(text):
                    candidates.append((text, loc))
                    break
        except:
            pass
    
    if len(candidates) < 3:
        matches = page.get_by_text(DAY_PATTERN)
        count = matches.count()
        seen_texts = {text for text, _ in candidates}
        
        for i in range(count):
            loc = matches.nth(i)
            try:
                text = loc.inner_text().strip().upper()
                if DAY_PATTERN.search(text) and text not in seen_texts:
                    candidates.append((text, loc))
            except:
                pass
    
    return candidates


def main():
    previous_state = load_state()
    current_state = {}

    print(f"Checking: {BOOKMYSHOW_URL}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1600})
        page.goto(BOOKMYSHOW_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        candidates = get_day_candidates(page)
        print(f"Found {len(candidates)} days: {[text for text, _ in candidates]}")

        for text, loc in candidates:
            current_state[text] = is_disabled(loc)

        browser.close()

    newly_available = []
    for day_text, curr_disabled in current_state.items():
        prev_disabled = previous_state.get(day_text)
        if prev_disabled is True and curr_disabled is False:
            newly_available.append(day_text)

    save_state(current_state)

    if newly_available:
        msg = "🚨 BookMyShow alert: booking is now open for:\n" + "\n".join(newly_available) + f"\n\n{BOOKMYSHOW_URL}"
        send_telegram_message(msg)
        print("✅ Alert sent for:", newly_available)
    else:
        print("ℹ️ No new days became available.")


if __name__ == "__main__":
    main()
