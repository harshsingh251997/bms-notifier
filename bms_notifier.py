import os
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BOOKMYSHOW_URL = "https://in.bookmyshow.com/movies/pune/project-hail-mary/buytickets/ET00481564/20260328"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "state.txt"


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
        day_text, status = line.split("|", 1)
        state[day_text.strip()] = status.strip().lower() == "true"
    return state


def save_state(state):
    lines = [f"{day}|{str(status)}" for day, status in state.items()]
    Path(STATE_FILE).write_text("\n".join(lines) + "\n")


def check_days(page):
    import re

    # Scroll to trigger lazy loading
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(3000)

    html = page.inner_html("body")
    print(f"Total HTML length: {len(html)}")

    # Find where SAT appears in HTML
    sat_idx = html.upper().find("SAT")
    if sat_idx >= 0:
        print("Found SAT at index:", sat_idx)
        print("Context around SAT:")
        print(html[max(0, sat_idx - 200):sat_idx + 500])
    else:
        print("SAT not found in HTML - page not fully loaded")
        print("HTML chunk 3000-6000:", html[3000:6000])

    return {}


def main():
    previous_state = load_state()

    print(f"Checking: {BOOKMYSHOW_URL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Cache-Control": "max-age=0"
            }
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, "webdriver", { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page.goto(BOOKMYSHOW_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(10000)
        print("Page title:", page.title())

        check_days(page)
        browser.close()

    print("Done - check HTML output above to understand structure")


if __name__ == "__main__":
    main()
