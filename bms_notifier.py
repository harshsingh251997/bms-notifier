import os
import requests
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

BOOKMYSHOW_URL = "https://in.bookmyshow.com/movies/pune/project-hail-mary/buytickets/ET00481564/20260328"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "state.txt"

DISABLED_CLASS = "hzcALk"


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


def date_id_to_label(date_id):
    try:
        dt = datetime.strptime(date_id, "%Y%m%d")
        return dt.strftime("%a").upper() + " " + str(dt.day)
    except:
        return date_id


def check_days(page):
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(2000)

    js_script = """
        () => {
            const results = {};
            const dateTabs = document.querySelectorAll('div[id^="2026"]');
            for (const tab of dateTabs) {
                const id = tab.getAttribute("id");
                if (!/^\d{8}$/.test(id)) continue;
                const classes = tab.getAttribute("class") || "";
                const isDisabled = classes.includes("hzcALk");
                results[id] = {
                    classes: classes,
                    bookable: !isDisabled
                };
            }
            return results;
        }
    """
    raw = page.evaluate(js_script)
    print("Raw DOM results:", raw)

    results = {}
    for date_id, info in raw.items():
        label = date_id_to_label(date_id)
        results[label] = info["bookable"]
        print(f"  {label} (id={date_id}): bookable={info['bookable']} | class={info['classes']}")

    return results


def main():
    previous_state = load_state()
    current_state = {}

    print(f"Checking: {BOOKMYSHOW_URL}")
    print(f"Previous state: {previous_state}")

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

        current_state = check_days(page)
        browser.close()

    print(f"Current state: {current_state}")

    newly_available = []
    for day_text, is_bookable in current_state.items():
        was_bookable = previous_state.get(day_text, False)
        if is_bookable and not was_bookable:
            newly_available.append(day_text)

    save_state(current_state)

    if newly_available:
        msg = "🚨 BookMyShow: Booking now open!\n" + "\n".join(newly_available) + f"\n\n{BOOKMYSHOW_URL}"
        send_telegram_message(msg)
        print("Alert sent for:", newly_available)
    else:
        print("No new days became available.")


if __name__ == "__main__":
    main()
