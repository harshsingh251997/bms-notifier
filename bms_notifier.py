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
    # PC UI + BookMyShow specific selectors
    selectors = [
        '[role="tab"]',
        'button, div[role="button"]:has-text("SAT"), button:has-text("SUN"), button:has-text("MON")',
        '[data-testid*="date"], .date-tab, .datepicker-tab, .show-date-tab',
        '[class*="date-tab"], [class*="date-picker"] button',
        '.sc-bkPkYk, .sc-gCFkuy'  # common BookMyShow CSS patterns
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
    
    # Fallback: broad text search
    if len(candidates) < 3:
        matches = page.get_by_text(DAY_PATTERN, exact=False)
        count = matches.count()
        seen_texts = {text for text, _ in candidates}
        
        for i in range(min(count, 20)):  # limit to avoid too many
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
        # Stealth mode for GitHub Actions + BookMyShow
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0"
            }
        )
        
        # Anti-detection scripts
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            window.chrome = {
                runtime: {},
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
        """)
        
        page.goto(BOOKMYSHOW_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(10000)  # Wait for dynamic content

        print("Page title:", page.title()[:100])
        print("Final URL:", page.url)

        candidates = get_day_candidates(page)
        print(f"Found {len(candidates)} days: {[text for text, _ in candidates]}")

        for text, loc in candidates:
            disabled = is_disabled(loc)
            current_state[text] = disabled
            print(f"  {text}: disabled={disabled}")

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
