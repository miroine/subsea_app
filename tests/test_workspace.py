"""Workspace navigation, safe template loading and responsive toolbar regressions."""
import copy
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from streamlit.testing.v1 import AppTest

from test_connections import assert_attached, browser_executable
from test_host_tab import SPEC
from subsea.presets import PRESETS, get_preset


ROOT = Path(__file__).resolve().parents[1]


def check_forms():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    labels = [tab.label for tab in app.tabs]
    for label in ("Edit design", "Review design", "Save & export", "Symbol reference",
                  "Selected item", "All equipment", "Host & risers", "Saved cases"):
        assert label in labels
    baseline = copy.deepcopy(app.session_state.spec)
    assert baseline["freeform"] and baseline["chain"] == [] and baseline["host"] is None
    template = next(widget for widget in app.selectbox if widget.label == "Preset")
    template.set_value(next(name for name in PRESETS if name != "Blank canvas – draw your own")).run()
    assert app.session_state.spec == baseline
    template.set_value("Blank canvas – draw your own").run()
    next(widget for widget in app.button if widget.label == "Load template").click().run()
    assert not app.exception
    assert app.session_state.spec["freeform"] and app.session_state.spec["chain"] == []
    assert app.session_state.spec["host"] is None
    app.session_state.spec["gap"] = 17
    app.session_state.spec["mirror"] = True
    app.session_state.ver += 1
    app.run()
    assert app.session_state.spec["gap"] == 17 and app.session_state.spec["mirror"] is True
    assert next(widget for widget in app.slider if widget.label == "Gap after host (px)").value == 17
    print("PASS: grouped navigation, explicit template loading and blank-design state")


def check_browser(url):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1800, "height": 1200})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000)
        frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        upload = page.locator('input[type="file"]')
        upload.set_input_files({"name": "workspace.json", "mimeType": "application/json",
                               "buffer": json.dumps(SPEC).encode()})
        frame.wait_for_function("() => window.__subsea.spec.chain.some(i => i.id === 'fpso_1')", timeout=20000)
        frame.wait_for_function("() => window.__subsea.spec.chain[0].activeSlot !== undefined", timeout=15000)
        expected = frame.evaluate("window.__subsea.spec")
        for label in ("Review design", "Save & export", "Symbol reference", "Edit design"):
            page.get_by_role("tab", name=label, exact=True).click()
            actual = frame.evaluate("window.__subsea.spec")
            assert actual == expected, {key: (expected.get(key), actual.get(key)) for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)}
        page.get_by_role("tab", name="Host & risers", exact=True).click()
        expect(page.get_by_label("Slot / riser labels (comma separated)", exact=True)).to_have_value("Production, Umbilical")
        page.get_by_role("tab", name="Selected item", exact=True).click()
        frame.locator('[data-id="fpso_1"] .hit').click(force=True, position={"x": 40, "y": 20})
        expect(page.get_by_label("Element label", exact=True)).to_be_visible(timeout=15000)
        frame.locator("#b_palette").click()
        expect(frame.locator("#b_palette")).to_have_attribute("aria-expanded", "true")
        frame.locator("#palette-close").click()
        expect(frame.locator("#b_palette")).to_have_attribute("aria-expanded", "false")
        frame.locator("#b_grid").click()
        expect(frame.locator("#b_grid")).to_have_attribute("aria-pressed", "true")
        frame.locator("#b_connect").click()
        expect(frame.locator("#b_connect")).to_have_attribute("aria-pressed", "true")
        frame.locator("#b_connect").click()
        expect(frame.locator("#b_connect")).to_have_attribute("aria-pressed", "false")
        before = frame.evaluate("!!window.__subsea.spec.animate")
        frame.locator("#b_flow").click()
        expect(frame.locator("#b_flow")).to_have_attribute("aria-pressed", str(not before).lower())
        assert_attached(frame, ("base", "P-left"), ("jacket_1", "J-0"))
        assert frame.locator(".tool-group").count() == 6
        for width in (1280, 768):
            page.set_viewport_size({"width": width, "height": 1100})
            frame.wait_for_function("""() => {
                const bar = document.querySelector('#bar');
                return bar.scrollWidth <= document.documentElement.clientWidth + 1;
            }""")
            assert frame.locator("#svg").bounding_box()["height"] > 180
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.set_viewport_size({"width": 1800, "height": 1200})
        page.get_by_role("tab", name="Save & export", exact=True).click()
        page.get_by_label("Case name", exact=True).fill("Workspace verification")
        page.get_by_role("button", name="Save case version", exact=True).click()
        expect(page.get_by_text("Saved Workspace verification: version 1.", exact=True)).to_be_visible()
        upload.set_input_files({"name": "replacement.json", "mimeType": "application/json",
                               "buffer": json.dumps(get_preset("Blank canvas – draw your own")).encode()})
        frame.wait_for_function("() => window.__subsea.spec.freeform && window.__subsea.spec.chain.length === 0")
        expect(page.get_by_text("Working drawing", exact=True)).to_be_visible()
        upload.set_input_files({"name": "invalid.json", "mimeType": "application/json", "buffer": b"[]"})
        expect(page.get_by_text("Not a valid spec file:", exact=False)).to_be_visible()
        assert frame.evaluate("window.__subsea.spec.chain.length") == 0
        assert page.get_by_test_id("stException").count() == 0
        assert not errors, errors
        browser.close()
    print("PASS: workspace navigation preserves geometry; responsive toolbar, accessibility state, host selection, saving and import checks")


def run():
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    with tempfile.TemporaryDirectory(prefix="subsea-workspace-") as directory:
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            check_forms()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with (Path(directory) / "server.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                     "--server.headless=true", "--server.address=127.0.0.1",
                     f"--server.port={port}", "--browser.gatherUsageStats=false"],
                    stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    url = f"http://127.0.0.1:{port}"
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError("Streamlit exited before readiness")
                        try:
                            with urlopen(url + "/_stcore/health", timeout=1) as response:
                                if response.status == 200:
                                    break
                        except URLError:
                            time.sleep(.2)
                    else:
                        raise RuntimeError("Streamlit did not become ready")
                    check_browser(url)
                finally:
                    process.terminate()
                    process.wait(timeout=20)
        finally:
            logging.disable(old_logging)
            if old_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = old_path


if __name__ == "__main__":
    run()
