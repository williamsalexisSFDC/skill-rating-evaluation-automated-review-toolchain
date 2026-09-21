"""
Shared Playwright browser session for org62 scripts.

Usage:
    from playwright_session import org62_session

    with org62_session(slow_mo=200, viewport=(1400, 900)) as page:
        page.goto(URL)
        ...
"""

from contextlib import contextmanager

from playwright.sync_api import sync_playwright


@contextmanager
def org62_session(slow_mo: int = 100, viewport: tuple[int, int] = (1440, 900)):
    """
    Launch a headed Chromium browser sized for org62 and yield the page.
    Closes the browser on exit whether or not an exception was raised.

    Args:
        slow_mo:  Milliseconds to slow each Playwright action (useful for debugging).
        viewport: (width, height) in pixels.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]}
        )
        page = context.new_page()
        try:
            yield page
        finally:
            browser.close()
