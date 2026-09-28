"""Take dashboard screenshots with headless Chrome via Playwright."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = "docs"
TABS = ["Funnel", "Linkage decisions", "Match quality", "Eligibility & schemes", "Outreach queues",
        "Student drill-down", "Scenarios", "Admin", "Match Outcomes", "36-Scenario Matrix"]
SLUG = {"36-Scenario Matrix": "scenarios36"}
ONLY = [t for t in sys.argv[2:]]  # optional: tab names to capture (default: all)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1600, "height": 2300})
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_selector("text=Scholarship Intelligence", timeout=60000)
    pg.wait_for_timeout(5000)
    errors = []
    for i, t in enumerate(TABS, start=1):
        if ONLY and t not in ONLY:
            continue
        pg.get_by_role("tab", name=t, exact=True).click()
        pg.wait_for_timeout(6000 if t == "Student drill-down" else 3000)
        body = pg.inner_text("body")
        if "Traceback" in body or "Error" in body.split("Scholarship Intelligence")[-1][:0] or "StreamlitAPIException" in body:
            errors.append(t)
        slug = SLUG.get(t) or t.lower().replace(' & ', '_').replace(' ', '_').replace('-', '')
        name = f"{OUT}/dashboard_{i:02d}_{slug}.png"
        pg.screenshot(path=name, full_page=True)
        print("saved", name)
    print("errors:", errors)
    b.close()
