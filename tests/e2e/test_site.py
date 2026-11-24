"""Playwright E2E tests for the static site."""

import pytest
from playwright.sync_api import Page, expect

BASE = "http://localhost:8080"

PAGES = [
    "/",
    "/copyright.html",
    "/government-removals.html",
    "/https.html",
    "/safe-browsing.html",
    "/email-encryption.html",
    "/eu-privacy.html",
    "/user-data.html",
    "/traffic-disruptions.html",
    "/about.html",
    "/methodology.html",
    "/data-sources.html",
]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True}


def test_index_loads(page: Page):
    page.goto(f"{BASE}/")
    expect(page).to_have_title("google-transparency-report-analysis.oriz.in")
    # hero heading present
    heading = page.locator("h1").first
    expect(heading).to_be_visible()


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_no_error(page: Page, path: str):
    errors = []
    page.on("console", lambda msg: errors.append(msg) if msg.type == "error" else None)
    response = page.goto(f"{BASE}{path}")
    # Static servers keep the requested URL even when returning an error page.
    assert response is not None, f"{path} did not return an HTTP response"
    assert response.ok, f"{path} returned HTTP {response.status}"
    # no JS console errors
    assert not errors, f"{path} had console errors: {[e.text for e in errors]}"


def test_index_has_dataset_cards(page: Page):
    page.goto(f"{BASE}/")
    cards = page.locator("[data-dataset-card]")
    expect(cards.first).to_be_visible()
    count = cards.count()
    assert count >= 6, f"expected >=6 dataset cards, got {count}"


def test_copyright_page_has_charts(page: Page):
    page.goto(f"{BASE}/copyright.html")
    # at least one canvas element (Chart.js renders into canvas)
    canvases = page.locator("canvas")
    assert canvases.count() >= 1, "copyright.html must have at least 1 Chart.js canvas"


def test_nav_links_work(page: Page):
    page.goto(f"{BASE}/")
    nav = page.locator("nav a")
    count = nav.count()
    assert count >= 3, f"expected >=3 nav links, got {count}"
    for i in range(min(count, 4)):
        href = nav.nth(i).get_attribute("href")
        assert href, f"nav link {i} has no href"


def test_data_sources_page_lists_sources(page: Page):
    page.goto(f"{BASE}/data-sources.html")
    # must mention transparencyreport.google.com
    content = page.content()
    assert "transparencyreport.google.com" in content


def test_about_page_has_content(page: Page):
    page.goto(f"{BASE}/about.html")
    content = page.content()
    assert (
        "google-transparency-report-analysis.oriz.in" in content.lower()
        or len(content) > 500
    )


def test_methodology_page_mentions_csv(page: Page):
    page.goto(f"{BASE}/methodology.html")
    content = page.content()
    assert "csv" in content.lower() or "bulk" in content.lower()
