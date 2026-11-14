"""Browser end-to-end test for TerraWatt v2 (Playwright). Start the server first, then:

    BASE=http://127.0.0.1:5055 python tests/e2e_v2.py [screenshot_dir]

Covers every page on desktop and mobile, the carbon -> goal -> badge journey, What-if presets/report, all Model Lab tabs.
Fails on any console error, uncaught exception, HTTP >= 400 (except expected ones), "Something went wrong"-style error
states, or horizontal overflow on mobile.
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("BASE", "http://127.0.0.1:5055")
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-shots")
SHOTS.mkdir(parents=True, exist_ok=True)
EXPECTED = ("/api/auth/me", "/api/auth/register", "favicon")
results, problems = [], []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as exc:                           # noqa: BLE001 - report every failure, keep going
        results.append((name, False, (((str(exc).splitlines() or [""])[0] or type(exc).__name__) + " @line " + str(exc.__traceback__.tb_next.tb_lineno if exc.__traceback__ and exc.__traceback__.tb_next else "?"))[:220]))


def new_page(browser, mobile):
    ctx = browser.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1360, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    tag = "mobile" if mobile else "desktop"
    page.on("console", lambda m: problems.append((tag, "console", m.text)) if m.type == "error" and "401" not in m.text and "422" not in m.text else None)
    page.on("pageerror", lambda e: problems.append((tag, "pageerror", str(e))))
    page.on("response", lambda r: problems.append((tag, "http", f"{r.status} {r.url}")) if r.status >= 400 and r.status not in (401, 422) and not any(x in r.url for x in EXPECTED) else None)
    return ctx, page


def run(browser, mobile):
    tag = "mobile" if mobile else "desktop"
    ctx, page = new_page(browser, mobile)

    def go(path, wait=1500):
        page.goto(f"{BASE}/#{path}")
        page.wait_for_timeout(wait)

    def no_error_state():
        assert page.locator("[role=alert]").count() == 0, f"error state shown: {page.locator('[role=alert]').first.inner_text()[:120]}"
        assert "Something went wrong" not in page.content()

    def no_overflow():
        w = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        assert w[0] <= w[1] + 1, f"horizontal overflow {w}"

    def shot(name, full=True):
        page.screenshot(path=str(SHOTS / f"{tag}-{name}.png"), full_page=full)

    def page_ok(name, path, wait=1800, full=True):
        def f():
            go(path, wait)
            no_error_state()
            if mobile:
                no_overflow()
            shot(name, full)
        check(f"[{tag}] {name} loads without errors", f)

    # ---------------------------------------------------------------- public pages
    check(f"[{tag}] landing", lambda: (go("/", 1800), expect(page.get_by_role("heading", level=1)).to_be_visible(), no_overflow() if mobile else None, shot("landing", False)))

    def dashboard():
        go("/dashboard", 2200)
        no_error_state()
        assert page.locator(".kpi").count() == 6, page.locator(".kpi").count()
        assert page.locator(".kpi .year-chip").count() == 6, "every KPI must show its reporting year"
        assert page.locator(".map-wrap circle").count() > 150, "map dots"
        assert page.locator("canvas, .kpi .spark").count() == 0, "decorative sparklines should be gone"
        assert "partial" in page.inner_text(".note-partial").lower()
        years = {c.inner_text() for c in page.locator(".kpi .year-chip").all()}
        assert {"2024", "2025", "2020", "2019"} <= years, years
        if mobile:
            no_overflow()
        shot("dashboard")
    check(f"[{tag}] dashboard: 6 KPIs with per-indicator years, map, partial-year note", dashboard)

    def dash_map_switch():
        go("/dashboard", 1800)
        page.get_by_role("button", name="Electricity access").click()
        page.wait_for_timeout(1200)
        assert "2020" in page.inner_text(".card:has(.map-wrap) .sub")
    check(f"[{tag}] dashboard map uses each indicator's own year", dash_map_switch)

    def renewables():
        go("/renewables", 2200)
        no_error_state()
        expect(page.get_by_text("Generation is not the same as final energy")).to_be_visible()
        assert "Hydropower" in page.inner_text("table")
        for tab in ("Country ranking", "Compare countries", "Dominant source", "Fastest change"):
            page.get_by_role("tab", name=tab).click()
            page.wait_for_timeout(1300)
            no_error_state()
        page.get_by_role("tab", name="Country ranking").click()
        page.wait_for_timeout(800)
        page.get_by_role("button", name="Wind").click()
        page.wait_for_timeout(1200)
        assert page.locator(".card .row.spread").count() > 0
        if mobile:
            no_overflow()
        shot("renewables")
    check(f"[{tag}] renewables: world, ranking, compare, dominant, movers", renewables)

    def atlas():
        go("/atlas", 2200)
        no_error_state()
        expect(page.get_by_text("countries report")).to_be_visible()
        boxes = page.locator("input[type=checkbox]")
        boxes.nth(0).check()
        boxes.nth(1).check()
        expect(page.get_by_role("link", name="Compare selected")).to_be_visible()
        if mobile:
            no_overflow()
        shot("atlas", False)
    check(f"[{tag}] atlas: availability chip, multi-select compare", atlas)

    def compare():
        go("/compare?c=India,China,Germany,Brazil,Norway&metric=co2_per_capita_t", 2200)
        no_error_state()
        assert "World average" in page.inner_text("table")
        assert page.locator(".chip button").count() == 5
        page.get_by_role("button", name="Solar").click()
        page.wait_for_timeout(1500)
        no_error_state()
        if mobile:
            no_overflow()
        shot("compare")
    check(f"[{tag}] compare: 5 countries + world average + solar", compare)

    def country():
        go("/country/Spain", 2600)
        no_error_state()
        expect(page.get_by_text("Official 2030 target: 81")).to_be_visible()
        expect(page.get_by_text("like-for-like")).to_be_visible()
        page.get_by_role("tab", name="Renewable sources").click()
        page.wait_for_timeout(900)
        assert "dominant" in page.inner_text(".page").lower(), page.inner_text(".page")[:300]
        page.locator("details.more summary", has_text="Data availability").click()
        assert "Solar electricity" in page.inner_text("details.more[open]")
        if mobile:
            no_overflow()
        shot("country-spain")
    check(f"[{tag}] country: forecast + verified official target + sources + availability", country)

    def country_no_target():
        go("/country/India", 2400)
        no_error_state()
        assert page.get_by_text("Official 2030 target").count() == 0
    check(f"[{tag}] country without a verified target shows none", country_no_target)

    page_ok("dataset", "/data", 1800)

    def dataset_catalog():
        go("/data", 1500)
        page.locator("details.more summary").first.click()
        assert "Grid carbon intensity" in page.inner_text("details.more[open]")
        assert "partial" in page.inner_text("details.more[open]")
    check(f"[{tag}] dataset: indicator catalog with sources and partial years", dataset_catalog)

    # ---------------------------------------------------------------- carbon (anonymous)
    def carbon_simple():
        go("/carbon", 2000)
        no_error_state()
        expect(page.get_by_text("estimated household operational carbon footprint").first).to_be_visible()
        page.get_by_role("button", name="₹2,000").click()
        page.get_by_role("button", name="Occasionally").click()
        page.get_by_role("button", name="300–600").click()
        page.wait_for_timeout(1500)
        expect(page.get_by_text("kg CO₂e").first).to_be_visible()
        assert page.locator(".result-total").count() == 1 and float(__import__("re").match(r"[\d,\.]+", page.inner_text(".result-total")).group().replace(",", "")) > 20
        page.locator("details.more summary", has_text="How each part").click()
        assert "estimated" in page.inner_text("details.more[open]")
        page.locator("details.more summary", has_text="Methodology").click()
        assert "tw-carbon-2" in page.inner_text("[data-testid=methodology]")
        assert "₹7/kWh" in page.inner_text("[data-testid=methodology]")
        # skip a question: electricity skipped -> no electricity line
        page.get_by_label("Skip: Electricity").check()
        page.wait_for_timeout(1200)
        assert "Electricity (" not in page.inner_text(".result-total >> xpath=ancestor::div[contains(@class,'card')]")
        if mobile:
            no_overflow()
        shot("carbon-simple")
    check(f"[{tag}] carbon simple mode: approximate answers, estimated flags, methodology, skip", carbon_simple)

    def carbon_advanced():
        go("/carbon", 1500)
        page.get_by_role("button", name="Advanced").click()
        page.wait_for_timeout(500)
        page.locator(".q-card:has-text('Exact quantities') input[type=number]").first.fill("250")
        page.wait_for_timeout(1300)
        page.wait_for_selector(".result-total"); assert "actual" in page.inner_text(".page")
        shot("carbon-advanced")
    check(f"[{tag}] carbon advanced mode: exact inputs counted as actual", carbon_advanced)

    # ---------------------------------------------------------------- what-if
    def whatif():
        go("/lab?country=India", 2500)
        no_error_state()
        expect(page.get_by_text("Model estimate")).to_be_visible()
        base = page.inner_text(".big-num >> nth=1")
        page.get_by_role("button", name="High solar adoption").click()
        page.wait_for_timeout(1500)
        no_error_state()
        expect(page.get_by_text("Electricity mix result")).to_be_visible()
        assert "Solar generation × 3" in page.inner_text(".card:has-text('What changed')")
        page.get_by_role("button", name="Save for comparison").click()
        page.get_by_role("button", name="Improved electricity access").click()
        page.wait_for_timeout(1200)
        page.get_by_role("button", name="Save for comparison").click()
        expect(page.get_by_text("Scenario comparison")).to_be_visible()
        assert page.locator(".card:has-text('Scenario comparison') tbody tr").count() == 2
        with page.expect_download() as d:
            page.get_by_role("button", name="Download PDF report").click()
        assert d.value.suggested_filename.endswith(".pdf")
        page.get_by_role("button", name="Reset all").click()
        page.wait_for_timeout(1200)
        assert page.inner_text(".big-num >> nth=1") == base
        assert page.get_by_text("Nothing yet").count() == 1
        # country with missing model inputs is flagged, never an error screen
        go("/lab?country=Bolivia", 2500)
        no_error_state()
        expect(page.get_by_text("not reported", exact=False).first).to_be_visible()
        if mobile:
            no_overflow()
        shot("whatif")
    check(f"[{tag}] what-if: presets, comparison, PDF, reset, low-reliability country", whatif)

    # ---------------------------------------------------------------- model lab
    def models():
        go("/models", 2500)
        no_error_state()
        expect(page.get_by_text("Models loaded")).to_be_visible()
        for tab, needle in (("Forecasting", "Honest summary"), ("Regression", "Example predictions"), ("Classification", "Confusion matrix"),
                            ("K-Means", "Silhouette by K"), ("Gaussian mixture", "Model selection (BIC")):
            page.get_by_role("tab", name=tab).click()
            page.wait_for_timeout(2500 if tab == "Forecasting" else 1300)
            no_error_state()
            assert needle in page.inner_text(".card:has(.tabs)"), f"{tab}: '{needle}' missing"
            for label in ("Purpose", "Limitations"):
                assert label.upper() in page.inner_text(".card:has(.tabs)").upper(), f"{tab}: {label} missing"
            shot(f"models-{tab.lower().replace(' ', '-')}")
        if mobile:
            no_overflow()
    check(f"[{tag}] model lab: all five tabs load with explanations", models)

    # ---------------------------------------------------------------- authenticated journey (desktop only)
    if not mobile:
        email = f"e2e{int(time.time())}@example.com"

        def journey():
            go("/register", 1200)
            page.fill("#name", "E2E Tester")
            page.fill("#email", email)
            page.fill("#password", "Str0ngPass99")
            page.click("button[type=submit]")
            page.wait_for_url("**/#/dashboard")
            page.wait_for_timeout(1200)
            # baseline month: bill 2400, 4 people, LPG 1, motorcycle
            go("/carbon", 1800)
            page.get_by_role("button", name="₹3,500").click()
            page.locator("input[type=month]").fill("2026-08")
            page.locator("input[type=month]").dispatch_event("change")
            page.get_by_role("button", name="1 a month").click()
            page.get_by_role("button", name="300–600").click()
            page.wait_for_timeout(1300)
            page.get_by_role("button", name="Save 2026-08 to my account").click()
            page.wait_for_timeout(1200)
            expect(page.get_by_text("Your saved months")).to_be_visible()
            # sustainability: set 10% goal
            go("/sustainability", 2000)
            no_error_state()
            expect(page.get_by_text("Set your monthly goal")).to_be_visible()
            page.get_by_role("button", name="Set my goal").click()
            page.wait_for_timeout(1800)
            assert page.locator("[data-badge=green_beginner][data-unlocked=true]").count() == 1
            assert page.locator("[data-badge=eco_warrior][data-unlocked=false]").count() == 1
            shot("sustainability-goal-set")
            # later months with far lower electricity: achieves target, passes 20% -> eco warrior + planet protector
            for month in ("2026-09", "2026-10"):
                go("/carbon", 1800)
                page.get_by_role("button", name="₹1,000").click()
                page.locator("input[type=month]").fill(month)
                page.locator("input[type=month]").dispatch_event("change")
                page.get_by_role("button", name="1 a month").click()
                page.get_by_role("button", name="300–600").click()
                page.wait_for_timeout(1300)
                page.get_by_role("button", name=f"Save {month} to my account").click()
                page.wait_for_timeout(1200)
            go("/sustainability", 2000)
            no_error_state()
            for key, state in (("green_beginner", "true"), ("eco_warrior", "true"), ("planet_protector", "true"), ("consistent_saver", "false")):
                assert page.locator(f"[data-badge={key}][data-unlocked={state}]").count() == 1, f"badge {key} should be unlocked={state}"
            body = page.inner_text(".page"); body_l = body.lower()
            assert "target achieved this month" in body_l and "months on target" in body_l, body[:400]
            shot("sustainability-progress")
            # a month with a different household size is excluded, with its reason shown
            go("/carbon", 1800)
            page.locator("input[type=number]").first.fill("2")
            page.get_by_role("button", name="₹1,000").click()
            page.locator("input[type=month]").fill("2026-11")
            page.locator("input[type=month]").dispatch_event("change")
            page.wait_for_timeout(1200)
            page.get_by_role("button", name="Save 2026-11 to my account").click()
            page.wait_for_timeout(1200)
            go("/sustainability", 2000)
            page.locator("details.more summary", has_text="not counted").click()
            assert "household size" in page.inner_text("details.more[open]")
            # persistence across a fresh browser context: log in again
            page.get_by_role("button", name="Sign out").click()
            page.wait_for_timeout(800)
            go("/login", 800)
            page.fill("#email", email)
            page.fill("#password", "Str0ngPass99")
            page.click("button[type=submit]")
            page.wait_for_url("**/#/dashboard")
            go("/sustainability", 2000)
            assert page.locator("[data-badge=planet_protector][data-unlocked=true]").count() == 1
        check("[desktop] journey: register -> save months -> goal -> badges -> exclusion -> re-login persistence", journey)

        def anon_sustainability_redirects():
            ctx2, p2 = new_page(browser, False)
            p2.goto(f"{BASE}/#/sustainability")
            p2.wait_for_timeout(1200)
            assert "/login" in p2.url
            ctx2.close()
        check("[desktop] sustainability requires sign-in", anon_sustainability_redirects)

        def dark():
            page.locator(".icon-btn[aria-label='Toggle dark mode']").click()
            page.wait_for_timeout(300)
            go("/dashboard", 2000)
            shot("dashboard-dark", False)
        check("[desktop] dark theme", dark)
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for mobile in (False, True):
        run(browser, mobile)
    browser.close()

for name, ok, msg in results:
    print(("PASS " if ok else "FAIL ") + name + (f"  -> {msg}" if msg else ""))
console = [x for x in problems]
print(f"\n{sum(ok for _, ok, _ in results)}/{len(results)} checks passed; {len(console)} console/HTTP problems")
for x in console[:25]:
    print("  PROBLEM", x)
sys.exit(0 if all(ok for _, ok, _ in results) and not console else 1)
