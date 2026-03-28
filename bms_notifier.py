import os
import re
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
    js_script = """
        () => {
            const results = {};
            const allElements = document.querySelectorAll("*");
            for (const el of allElements) {
                const text = (el.innerText || el.textContent || "").trim().toUpperCase();
                const dayMatch = text.match(/^(SAT|SUN|MON|TUE|WED|THU|FRI)[\\s\\n]*(\\d{1,2})$/);
                if (dayMatch) {
                    const key = dayMatch[1] + " " + dayMatch[2];
                    const style = window.getComputedStyle(el);
                    const isVisible = style.display !== "none" && style.visibility !== "hidden";
                    const isDisabled = (
                        el.disabled === true ||
                        el.getAttribute("disabled") !== null ||
                        el.getAttribute("aria-disabled") === "true" ||
                        style.pointerEvents === "none" ||
                        parseFloat(style.opacity) < 0.6 ||
                        (el.className && typeof el.className === "string" && el.className.toLowerCase().includes("disabled"))
                    );
                    if (isVisible) {
                        results[key] = !isDisabled;
                    }
                }
            }
            return results;
        }
    """
    return page.evaluate(js_script)


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
        page.wait_for_timeout(8000)

        print("Page title:", page.title())

        day_data = check_days(page)
        print(f"Raw day data from DOM: {day_data}")
        browser.close()

    for day, is_bookable in day_data.items():
        current_state[day] = is_bookable

    newly_available = []
    for day_text, is_bookable in current_state.items():
        was_bookable = previous_state.get(day_text, False)
        if is_bookable and not was_bookable:
            newly_available.append(day_text)

    save_state(current_state)

    if newly_available:
        msg = "Booking is now open for:\n" + "\n".join(newly_available) + f"\n\n{BOOKMYSHOW_URL}"
        send_telegram_message(msg)
        print("Alert sent for:", newly_available)
    else:
        print("No new days became available.")
        print("Current state:", current_state)


if __name__ == "__main__":
    main()
