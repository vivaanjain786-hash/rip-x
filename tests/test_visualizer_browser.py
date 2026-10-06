"""End-to-end check that the browser visualizer is driven by the Python engine.

Skipped when Playwright or a Chromium build is not available.
"""

import os
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from ripx.server import create_server  # noqa: E402


def _chromium_path():
    for candidate in ("/opt/pw-browsers/chromium", os.environ.get("RIPX_CHROMIUM", "")):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


@pytest.fixture()
def page():
    server = create_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_path())
        except Exception as error:  # no browser installed
            server.shutdown()
            pytest.skip(f"Chromium unavailable: {error}")
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        page.errors = []
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
        page.wait_for_function("document.getElementById('engineVal').textContent !== '…'")
        yield page
        browser.close()
    server.shutdown()
    server.server_close()


def test_page_uses_the_python_engine_and_converges(page):
    assert page.inner_text("#engineVal") == "Python"
    for _ in range(6):
        page.click("#btnStep")
        page.wait_for_timeout(150)
    assert page.inner_text("#convergenceStatusText") == "Network Converged"
    assert page.inner_text("#activeRoutesVal") == "25"  # 5 routers x 5 destinations
    assert page.errors == []


def test_failing_a_router_updates_the_page_from_engine_state(page):
    for _ in range(6):
        page.click("#btnStep")
        page.wait_for_timeout(150)
    page.click("#btnToggleNodeState")
    page.wait_for_function("document.getElementById('inspectorStatus').textContent.startsWith('FAILED')")
    page.wait_for_timeout(400)
    assert page.inner_text("#activeRoutesVal") != "25"
    assert page.errors == []


def test_switching_profile_reloads_the_network_with_ripx_settings(page):
    page.select_option("#profileSelect", "ripx")
    page.wait_for_function("document.getElementById('eventLogContainer').textContent.includes('Profile ripx')")
    for _ in range(30):
        page.click("#btnStep")
        page.wait_for_timeout(60)
    page.wait_for_timeout(300)
    assert "updates every" in page.inner_text("#inspectorStatus")
    assert page.errors == []


def test_dashboard_renders_comparison_and_traffic_engineering(page):
    page.goto(page.url.rsplit("/", 1)[0] + "/dashboard.html")
    page.wait_for_selector("#cmpCards .card", timeout=60000)
    assert page.locator("#cmpCharts svg").count() == 4
    page.click("#teGo")
    page.wait_for_selector("#teCards .card", timeout=60000)
    assert "%" in page.inner_text("#teCards")
    assert "Traffic engineering" in page.inner_text("#bm") or "seeds" in page.inner_text("#bmBody")
    assert page.errors == []


def test_dashboard_kpi_tiles_count_up_to_the_measured_values(page):
    base = page.url.rsplit("/", 1)[0]
    page.goto(base + "/dashboard.html")
    page.wait_for_selector("#cmpCards .kpi", timeout=60000)
    assert page.locator("#cmpCards .kpi").count() == 6
    page.wait_for_timeout(2500)  # let the count-up finish
    settled = page.eval_on_selector_all("#cmpCards [data-to]", "els => els.map(e => [e.textContent, Number(e.dataset.to)])")
    assert settled
    for text, value in settled:
        assert text.replace(",", "") == str(value) or abs(float(text.replace(",", "")) - value) < 0.051
    assert page.errors == []


def test_dashboard_respects_reduced_motion(page):
    page.emulate_media(reduced_motion="reduce")
    page.goto(page.url.rsplit("/", 1)[0] + "/dashboard.html")
    page.wait_for_selector("#cmpCards .kpi.on", timeout=60000)
    # With reduced motion the final numbers are in place immediately and no tile is animated by script.
    first = page.eval_on_selector("#cmpCards .kpi .b", "e => [e.textContent, e.dataset.to]")
    assert first[0].replace(",", "") == first[1]
    assert page.evaluate("getComputedStyle(document.querySelector('.kpi'), '::before').animationName") == "none"
    assert page.errors == []
