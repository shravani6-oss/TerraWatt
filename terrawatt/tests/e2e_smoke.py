"""Browser end-to-end smoke test (Playwright). Start the server first, then:

    BASE=http://127.0.0.1:5000 ADMIN_EMAIL=... ADMIN_PASSWORD=... python tests/e2e_smoke.py [screenshot_dir]

Walks the main user journeys, fails on any console error / HTTP >= 400 (except expected ones) and saves screenshots.
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("BASE", "http://127.0.0.1:5000")
ADMIN = (os.getenv("ADMIN_EMAIL", "admin@terrawatt.test"), os.getenv("ADMIN_PASSWORD", "AdminPass123"))
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-shots")
SHOTS.mkdir(parents=True, exist_ok=True)
EXPECTED = ("/api/auth/me", "/api/auth/register")   # 401s from probing the session are fine


def main():
    email = f"e2e{int(time.time())}@example.com"
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1360, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: problems.append(("console", m.text)) if m.type == "error" and "401" not in m.text and "422" not in m.text else None)
        page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
        page.on("response", lambda r: problems.append(("http", f"{r.status} {r.url}")) if r.status >= 400 and not any(x in r.url for x in EXPECTED) and "favicon" not in r.url else None)

        def go(path, wait=1200):
            page.goto(f"{BASE}/#{path}")
            page.wait_for_timeout(wait)

        # ---- register
        go("/register")
        page.fill("#name", "E2E Tester"); page.fill("#email", email); page.fill("#password", "weak")
        page.click("button[type=submit]"); page.wait_for_timeout(600)
        expect(page.locator(".err:not(:empty)").first).to_be_visible()
        page.fill("#password", "Str0ngPass99"); page.click("button[type=submit]")
        page.wait_for_url("**/#/dashboard"); page.wait_for_timeout(1200)
        expect(page.get_by_text("Sign out")).to_be_visible()
        page.screenshot(path=str(SHOTS / "dashboard-auth.png"))

        # ---- country: watch, forecast with target, switch tabs
        go("/country/Germany", 1800)
        page.get_by_role("button", name="Watch").click(); page.wait_for_timeout(600)
        expect(page.get_by_role("button", name="Watching")).to_be_visible()
        page.fill("input[aria-label='Target value']", "50"); page.keyboard.press("Tab"); page.wait_for_timeout(1500)
        expect(page.get_by_text("Model card")).to_be_visible()
        page.screenshot(path=str(SHOTS / "country-forecast.png"), full_page=True)
        for tab in ("Electricity mix", "Access", "Emissions"):
            page.get_by_role("tab", name=tab).click(); page.wait_for_timeout(700)
        page.screenshot(path=str(SHOTS / "country-mix.png"))
        with page.expect_download() as d:
            page.get_by_role("button", name="PDF report").click()
        assert d.value.suggested_filename.endswith(".pdf")

        # ---- carbon: estimate live, save, delete
        go("/carbon", 1500)
        page.fill("input[aria-label='Electricity (kWh)']", "320"); page.fill("input[aria-label='Car travel (km)']", "400")
        page.wait_for_timeout(900)
        expect(page.get_by_text("kg CO₂e / month").first).to_be_visible()
        page.get_by_role("button", name="Save month").click(); page.wait_for_timeout(1200)
        expect(page.get_by_text("Monthly emissions")).to_be_visible()
        page.screenshot(path=str(SHOTS / "carbon-auth.png"), full_page=True)
        page.get_by_role("button", name="Delete" , exact=False).first.click(); page.wait_for_timeout(300)
        page.get_by_role("button", name="Delete", exact=True).click(); page.wait_for_timeout(900)
        expect(page.get_by_text("No saved months yet")).to_be_visible()

        # ---- alerts
        go("/alerts", 1500)
        page.fill("input[aria-label='Threshold']", "60")
        page.get_by_role("button", name="Add rule").click(); page.wait_for_timeout(1200)
        expect(page.get_by_text("is below 60").first).to_be_visible()
        page.screenshot(path=str(SHOTS / "alerts.png"), full_page=True)
        page.locator(".icon-btn[aria-label=Notifications]").click(); page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "notifications.png"))

        # ---- what-if lab
        go("/lab?country=Brazil", 1800)
        slider = page.locator("input[type=range]").first
        slider.evaluate("e => { e.value = e.max; e.dispatchEvent(new Event('input', {bubbles:true})); }")
        page.wait_for_timeout(900)
        expect(page.get_by_text("Effect of each change on its own")).to_be_visible()
        page.screenshot(path=str(SHOTS / "lab.png"), full_page=True)

        # ---- other pages
        for path, name in [("/atlas", "atlas"), ("/compare?c=India,China,Brazil,Germany", "compare"), ("/data", "data"), ("/models", "models")]:
            go(path, 1800); page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=(name != "atlas"))
        go("/data", 1200)
        page.fill("input[aria-label='Search country']", "Nor"); page.wait_for_timeout(800)
        expect(page.get_by_role("link", name="Norway").first).to_be_visible()
        for tab in ("Regression", "Classification", "Clustering"):
            go("/models", 1500); page.get_by_role("tab", name=tab).click(); page.wait_for_timeout(700)
            page.screenshot(path=str(SHOTS / f"models-{tab.lower()}.png"), full_page=True)

        # ---- non-admin must not reach admin
        go("/admin", 800)
        assert "/admin" not in page.url, "non-admin reached admin page"

        # ---- settings + logout
        go("/settings", 1000)
        page.fill("#name", "E2E Renamed"); page.get_by_role("button", name="Save profile").click(); page.wait_for_timeout(700)
        page.get_by_role("button", name="Sign out").click(); page.wait_for_timeout(800)

        # ---- admin
        go("/login", 800)
        page.fill("#email", ADMIN[0]); page.fill("#password", ADMIN[1]); page.click("button[type=submit]")
        page.wait_for_url("**/#/dashboard"); go("/admin", 1500)
        expect(page.get_by_role("heading", name="Administration")).to_be_visible()
        page.screenshot(path=str(SHOTS / "admin.png"), full_page=True)
        page.get_by_role("tab", name="System").click(); page.wait_for_timeout(500)
        page.get_by_role("tab", name="Audit log").click(); page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "admin-audit.png"))

        # ---- dark theme + mobile
        page.locator(".icon-btn[aria-label='Toggle dark mode']").click(); page.wait_for_timeout(300)
        go("/dashboard", 1600); page.screenshot(path=str(SHOTS / "dashboard-dark.png"))
        go("/country/India", 1800); page.screenshot(path=str(SHOTS / "country-dark.png"))
        m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = m.new_page()
        mp.on("pageerror", lambda e: problems.append(("pageerror-mobile", str(e))))
        for path, name in [("/", "m-landing"), ("/dashboard", "m-dashboard"), ("/country/India", "m-country"), ("/carbon", "m-carbon"), ("/atlas", "m-atlas")]:
            mp.goto(f"{BASE}/#{path}"); mp.wait_for_timeout(1800)
            mp.screenshot(path=str(SHOTS / f"{name}.png"))
            overflow = mp.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if overflow > 2:
                problems.append(("overflow", f"{name} scrolls horizontally by {overflow}px"))
        browser.close()
    if problems:
        print("PROBLEMS:"); [print(" ", p) for p in problems]; sys.exit(1)
    print("E2E OK: all journeys passed with no console errors.")


if __name__ == "__main__":
    main()
