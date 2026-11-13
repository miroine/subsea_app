"""Browser regressions for connection placement. Run: python tests\\test_connections.py."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from subsea.html import build_html
from subsea.presets import get_preset


def browser_executable():
    override = os.environ.get("CHROME_EXECUTABLE")
    if override:
        return override
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def screen_port(page, item_id, port_id):
    return page.locator(f'[data-id="{item_id}"] [data-port="{port_id}"]').evaluate(
        """port => {
          const point = port.ownerSVGElement.createSVGPoint();
          point.x = +port.dataset.x; point.y = +port.dataset.y;
          const position = point.matrixTransform(port.closest('.el').getScreenCTM());
          return {x: position.x, y: position.y};
        }"""
    )


def drag_ports(page, source, target):
    start = screen_port(page, *source)
    end = screen_port(page, *target)
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(end["x"], end["y"], steps=12)
    page.mouse.up()


def assert_attached(page, source, target, index=0):
    path = page.locator('.connection path:not(.connection-hit)').nth(index)
    ends = path.evaluate(
        """path => {
          const matrix = path.getScreenCTM();
          const a = path.getPointAtLength(0).matrixTransform(matrix);
          const b = path.getPointAtLength(path.getTotalLength()).matrixTransform(matrix);
          return [{x:a.x, y:a.y}, {x:b.x, y:b.y}];
        }"""
    )
    expected = [screen_port(page, *source), screen_port(page, *target)]
    for actual, port in zip(ends, expected):
        assert abs(actual["x"] - port["x"]) < 0.1, (actual, port)
        assert abs(actual["y"] - port["y"]) < 0.1, (actual, port)
    assert path.get_attribute("fill") == "none"

def component_width(page, item_id):
    return page.locator(f'.el[data-id="{item_id}"]').evaluate(
        "element => element.getBoundingClientRect().width"
    )


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-connections-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1200, "height": 780}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        spec = {
            "title": "New subsea layout", "freeform": True, "host": None,
            "showLegend": False, "animate": False,
            "chain": [
                {"id": "plem", "type": "plem", "x": 100, "y": 120},
                {"id": "template", "type": "template", "x": 500, "y": 105},
                {"id": "plet", "type": "plet", "x": 300, "y": 300},
            ],
        }
        html_file = Path(directory) / "drawing.html"
        html_file.write_text(build_html(spec), encoding="utf-8")
        page.goto(html_file.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        source, target = ("plem", "P-right"), ("template", "P-left")
        page.click("#b_connect")
        assert page.locator('[data-id="template"] [data-port="P-left"]').is_visible()
        drag_ports(page, source, target)
        assert page.locator(".connection").count() == 1
        assert_attached(page, source, target)
        saved = page.evaluate("window.__subsea.spec")
        assert saved["connections"] == [{
            "installationStatus": "New",
            "from": "plem", "to": "template", "fromPort": "P-right", "toPort": "P-left", "lane": "P",
        }]
        print("PASS: PLEM-to-template port drag and exact endpoint alignment")

        page.click("#b_in")
        assert_attached(page, source, target)
        page.set_viewport_size({"width": 1500, "height": 900})
        assert_attached(page, source, target)
        page.click("#b_fit")
        assert_attached(page, source, target)
        drag_ports(page, ("plet", "P-right"), ("template", "P-right"))
        assert page.locator(".connection").count() == 2
        assert_attached(page, ("plet", "P-right"), ("template", "P-right"), index=1)
        print("PASS: zoom/resize/fit and PLET-to-template drag")

        page.click("#b_connect")
        page.locator('[data-id="plem"] .hit').click(force=True)
        assert page.locator("#i_scale").input_value() == "100"
        original_width = component_width(page, "plem")
        neighbour_width = component_width(page, "template")
        view_box = page.locator("#svg").get_attribute("viewBox")
        page.locator("#i_scale").fill("150")
        page.locator("#i_scale").press("Tab")
        assert abs(component_width(page, "plem") / original_width - 1.5) < 0.001
        assert component_width(page, "template") == neighbour_width
        assert page.locator("#svg").get_attribute("viewBox") == view_box
        assert_attached(page, source, target)
        page.click("#i_smaller")
        assert page.locator("#i_scale").input_value() == "140"
        page.click("#i_larger")
        assert page.locator("#i_scale").input_value() == "150"
        page.click("#i_size_reset")
        assert abs(component_width(page, "plem") - original_width) < 0.001
        page.locator("#i_scale").fill("0")
        page.locator("#i_scale").press("Tab")
        assert not page.locator("#i_scale").evaluate("input => input.checkValidity()")
        assert abs(component_width(page, "plem") - original_width) < 0.001
        page.locator("#i_scale").fill("150")
        page.locator("#i_scale").press("Tab")
        print("PASS: selected component sizing, reset, invalid input, and unchanged neighbours/zoom")

        page.locator("#insp").evaluate("element => element.style.display = 'none'")
        start = screen_port(page, "plem", "P-right")
        page.mouse.move(start["x"] - 8, start["y"])
        page.mouse.down()
        page.mouse.move(start["x"] + 20, start["y"] + 35, steps=8)
        page.mouse.up()
        moved = screen_port(page, *source)
        assert abs(moved["x"] - start["x"]) > 10
        assert abs(moved["y"] - start["y"]) > 10
        assert page.evaluate("window.__subsea.spec.overrides.plem.scale") == 1.5
        assert abs(component_width(page, "plem") / original_width - 1.5) < 0.001
        assert_attached(page, source, target)
        print("PASS: moving equipment keeps connector attached")

        with page.expect_download() as downloaded:
            page.click("#b_svg")
        export = Path(directory) / "drawing.svg"
        downloaded.value.save_as(export)
        svg_text = export.read_text(encoding="utf-8")
        assert 'class="connection-hit"' not in svg_text
        assert 'class="connection-port"' not in svg_text
        assert re.search(r'<path[^>]+fill="none"[^>]+stroke="#', svg_text)
        exported = browser.new_page()
        exported.goto(export.as_uri())
        style = exported.locator(".connection path").first.evaluate(
            """path => ({
                fill:getComputedStyle(path).fill, stroke:getComputedStyle(path).stroke,
                width:getComputedStyle(path).strokeWidth
            })"""
        )
        assert style["fill"] == "none", style
        assert style["stroke"] != "none", style
        assert style["width"] == "2.5px", style
        exported.close()
        print("PASS: standalone SVG has thin, unfilled connectors and no editor handles")

        with page.expect_download() as downloaded:
            page.click("#b_json")
        saved_json = Path(directory) / "drawing.json"
        downloaded.value.save_as(saved_json)
        html_file.write_text(build_html(json.loads(saved_json.read_text(encoding="utf-8"))), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator(".connection").count() == 2
        assert_attached(page, source, target)
        assert_attached(page, ("plet", "P-right"), ("template", "P-right"), index=1)
        assert page.evaluate("window.__subsea.spec.overrides.plem.scale") == 1.5
        page.locator('[data-id="plem"] .hit').click(force=True)
        page.click("#i_copy")
        copy_id = page.evaluate("window.__subsea.sel")
        assert page.evaluate("(id) => window.__subsea.spec.overrides[id].scale", copy_id) == 1.5
        assert abs(component_width(page, copy_id) - component_width(page, "plem")) < 0.001
        print("PASS: JSON export/reload preserves port attachments")
        print("PASS: resized component retains size after dragging, JSON reload, and copying")

        legacy = get_preset("Two-template tieback to platform")
        legacy["connections"] = [{"from": "plem", "to": "t1"}]
        html_file.write_text(build_html(legacy), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_attached(page, ("plem", "P-right"), ("t1", "P-left"))
        page.click("#b_in")
        assert_attached(page, ("plem", "P-right"), ("t1", "P-left"))
        print("PASS: existing connections without port IDs snap to nearest production ports")
        for item_id in ("plem", page.locator(".el.link").first.get_attribute("data-id")):
            page.locator(f'[data-id="{item_id}"] .hit').click(force=True)
            before = component_width(page, item_id)
            page.locator("#i_scale").fill("75")
            page.locator("#i_scale").press("Tab")
            assert abs(component_width(page, item_id) / before - 0.75) < 0.001
            page.click("#i_copy")
            copy_id = page.evaluate("window.__subsea.sel")
            assert page.evaluate("(id) => window.__subsea.spec.overrides[id].scale", copy_id) == 0.75
        assert_attached(page, ("plem", "P-right"), ("t1", "P-left"))
        print("PASS: preset equipment and line symbols resize and copy with attached connectors")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    run()
