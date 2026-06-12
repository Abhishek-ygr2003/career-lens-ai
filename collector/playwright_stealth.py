"""
CareerLens AI - collector/playwright_stealth.py
================================================
Automatically refreshes Naukri API session headers (nkparam + Cookie)
by running a stealth Playwright browser that mimics a real human visit.

Anti-detection techniques used:
  - Hides 'webdriver' flag via CDP / init script
  - Randomises viewport, window size, and language headers
  - Sets realistic navigator properties (platform, vendor, plugins)
  - Uses non-headless mode first; falls back to headless if display unavailable
  - Adds human-like random delays before interactions

Usage (standalone):
    python -m collector.playwright_stealth
"""

import os
import random
import time
from dotenv import load_dotenv, set_key
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NAUKRI_SEARCH_URL = "https://www.naukri.com/ai-ml-engineer-jobs"
_API_PATH          = "jobapi/v3/search"
_ENV_PATH          = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1366, "height": 768},
]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# JS injected into every page to mask automation signals
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
window.chrome = { runtime: {} };
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _human_delay(lo: float = 0.8, hi: float = 2.2):
    """Sleep for a random duration to mimic human think-time."""
    time.sleep(random.uniform(lo, hi))


def _write_env(nkparam: str, cookie: str):
    """Persist nkparam and cookie into the project .env file."""
    os.makedirs(os.path.dirname(_ENV_PATH), exist_ok=True)

    # Ensure the file exists so set_key works even on first run
    if not os.path.exists(_ENV_PATH):
        open(_ENV_PATH, "a").close()

    set_key(_ENV_PATH, "NAUKRI_NKPARAM", nkparam)
    set_key(_ENV_PATH, "NAUKRI_COOKIE", cookie)

    # Reload into the current process environment
    os.environ["NAUKRI_NKPARAM"] = nkparam
    os.environ["NAUKRI_COOKIE"]  = cookie


def _try_browser(p, headless: bool) -> dict | None:
    """
    Launch a single browser attempt (headless or not).
    Returns intercepted headers dict on success, None on failure.
    """
    viewport   = random.choice(_VIEWPORTS)
    user_agent = random.choice(_USER_AGENTS)
    intercepted: dict = {}

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        f"--window-size={viewport['width']},{viewport['height']}",
    ]

    browser = p.chromium.launch(
        headless=headless,
        args=launch_args,
    )

    context = browser.new_context(
        user_agent=user_agent,
        viewport=viewport,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    # Inject stealth script into every page/frame before any JS runs
    context.add_init_script(_STEALTH_INIT_SCRIPT)

    page = context.new_page()

    def _on_request(request):
        if _API_PATH in request.url:
            hdrs = request.headers
            if "nkparam" in hdrs:
                intercepted["nkparam"] = hdrs["nkparam"]
                intercepted["cookie"]  = hdrs.get("cookie", "")
                print(f"  [OK] Intercepted nkparam from: {request.url[:80]}...")

    page.on("request", _on_request)

    try:
        print(f"  -> Navigating to Naukri ({'headless' if headless else 'headed'})...")
        page.goto(_NAUKRI_SEARCH_URL, wait_until="domcontentloaded", timeout=30_000)
        _human_delay(1.5, 3.0)

        # Scroll down slightly - triggers lazy-loaded job cards & API calls
        page.evaluate("window.scrollBy(0, Math.floor(Math.random() * 300 + 200))")
        _human_delay(0.5, 1.5)

        # Wait for the network to settle (API should fire automatically with page load)
        page.wait_for_load_state("networkidle", timeout=15_000)
        _human_delay(1.0, 2.0)

        # If the API hasn't fired yet, click next page to force it
        if "nkparam" not in intercepted:
            print("  -> API not intercepted on load. Clicking page 2 to trigger it...")
            try:
                # Try the 'next page' button or a page-2 link
                next_btn = page.locator("a[title='Next']").first
                if next_btn.is_visible(timeout=3_000):
                    next_btn.click()
                else:
                    page.locator("a", has_text="2").first.click(timeout=5_000)
                _human_delay(2.0, 4.0)
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PWTimeout:
                pass

    except Exception as nav_err:
        print(f"  [!] Navigation warning: {nav_err}")
    finally:
        browser.close()

    return intercepted if "nkparam" in intercepted else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refresh_naukri_headers(keyword: str = "ai ml engineer") -> dict | None:
    """
    Launch a stealth browser, intercept valid Naukri API session headers,
    persist them to .env and return them.

    Tries non-headless first (harder to detect), then headless.
    Returns dict with keys 'nkparam' and 'cookie', or None on failure.
    """
    print("\n[Playwright] Auto-refreshing Naukri session headers...")

    with sync_playwright() as p:
        for headless in (False, True):
            try:
                result = _try_browser(p, headless=headless)
                if result:
                    print("  [OK] Successfully captured fresh session headers.")
                    _write_env(result["nkparam"], result["cookie"])
                    return result
            except Exception as err:
                mode = "headless" if headless else "headed"
                print(f"  [FAIL] Browser attempt ({mode}) failed: {err}")

    print("  [FAIL] Could not intercept Naukri headers. Will proceed without refresh.")
    return None


if __name__ == "__main__":
    result = refresh_naukri_headers()
    if result:
        print(f"\nnkparam (first 40 chars): {result['nkparam'][:40]}...")
        print(f"cookie  (first 40 chars): {result['cookie'][:40]}...")
    else:
        print("\nFailed to refresh headers.")
