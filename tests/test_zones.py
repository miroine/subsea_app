"""Editable empty zone tables and freeform zones following actual equipment positions."""
import copy
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from test_connections import browser_executable
from subsea.html import build_html
from subsea.cases import CaseStore
from subsea.presets import get_preset
from subsea.spec import validate


SPEC = {"freeform": True, "host": None, "showLegend": False, "animate": False,
        "chain": [{"id": "p1", "type": "plet", "x": 600, "y": 120},
                  {"id": "p2", "type": "plet", "x": 950, "y": 160}],
        "overrides": {"p1": {"scale": .6, "dx": 40, "dy": 20}}}


def assert_span(page):
    assert page.locator(".design-zone").evaluate("""zone => {
        const svg = zone.ownerSVGElement;
        const bounds = id => {
            const element = svg.querySelector(`[data-id="${id}"]`), box = element.querySelector('.hit').getBBox();
            const p = svg.createSVGPoint();
            return [[box.x,box.y],[box.x+box.width,box.y+box.height]].map(([x,y]) => {
                p.x=x;p.y=y;return p.matrixTransform(element.getCTM()).x;
            });
        };
        const bar = zone.querySelector('.zone-span'), matrix = bar.getCTM(), p = svg.createSVGPoint();
        p.x = +bar.getAttribute('x1'); p.y = +bar.getAttribute('y1');
        const a = p.matrixTransform(matrix);
        p.x = +bar.getAttribute('x2');
        const b = p.matrixTransform(matrix);
        const edges = [...bounds('p1'),...bounds('p2')];
        return Math.abs(a.x - Math.min(...edges)) < .1 && Math.abs(b.x - Math.max(...edges)) < .1;
    }""")


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-zones-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        spec = {**SPEC, "zones": [{"from": "p1", "to": "p2", "label": "Fortified zone", "edges": "both"}]}
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator(".design-zone").count() == 1
        assert_span(page)
        span_before = float(page.locator(".zone-span").get_attribute("x2"))
        moved = copy.deepcopy(spec)
        moved["chain"][1]["x"] += 200
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", moved)
        assert_span(page)
        assert abs(float(page.locator(".zone-span").get_attribute("x2")) - span_before - 200) < .1
        moved["overrides"]["p2"] = {"scale": 1.4}
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", moved)
        assert_span(page)
        moved["zones"][0].update({"from": "p2", "to": "p1", "edges": "none"})
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", moved)
        assert_span(page)
        assert page.locator(".design-zone > line").count() == 1
        # Actual drag refreshes zone geometry without reloading the document.
        point = page.locator('[data-id="p2"]').evaluate("""element => {
            const box=element.querySelector('.hit').getBBox(), p=element.ownerSVGElement.createSVGPoint();
            p.x=box.x+box.width/2;p.y=box.y+box.height/2;
            const at=p.matrixTransform(element.getScreenCTM());return {x:at.x,y:at.y};
        }""")
        before_drag = float(page.locator(".zone-span").get_attribute("x2"))
        page.mouse.move(point["x"], point["y"])
        page.mouse.down()
        page.mouse.move(point["x"] + 80, point["y"] + 25, steps=10)
        page.mouse.up()
        assert_span(page)
        assert float(page.locator(".zone-span").get_attribute("x2")) > before_drag + 10
        assert page.locator(".design-zone .zone-label").text_content() == "Fortified zone"
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        export = Path(directory) / "zones.svg"
        downloaded.value.save_as(export)
        assert "Fortified zone" in export.read_text(encoding="utf-8")
        with page.expect_download() as downloaded:
            page.click("#b_json")
        export = Path(directory) / "zones.json"
        downloaded.value.save_as(export)
        saved = json.loads(export.read_text(encoding="utf-8"))
        assert saved["zones"] == moved["zones"]
        store = CaseStore(Path(directory) / "zones.sqlite3")
        case_id, version = store.save("Zones", saved)
        saved = store.load(case_id, version)
        html.write_text(build_html(saved), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert_span(page)
        # Mirrored branch transforms, and host starts on either side.
        mirrored = {**saved, "chain": [], "branches": [{"chain": saved["chain"], "mirror": True}]}
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", mirrored)
        assert_span(page)
        hosted = copy.deepcopy(spec)
        hosted["chain"].append({"id": "h", "type": "jacket", "x": 0, "y": 0, "slots": []})
        hosted["zones"][0]["fromHost"] = True
        for x in (0, 1500):
            hosted["chain"][-1]["x"] = x
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", hosted)
            assert page.locator(".design-zone").evaluate("""zone => {
                const h=document.querySelector('[data-id="h"]'), box=h.querySelector('.hit').getBBox();
                const p=h.ownerSVGElement.createSVGPoint();p.x=box.x;p.y=box.y;
                const a=p.matrixTransform(h.getCTM()).x;p.x+=box.width;
                const b=p.matrixTransform(h.getCTM()).x;
                const bar=zone.querySelector('.zone-span'), m=bar.getCTM();
                p.x=+bar.getAttribute('x1');p.y=+bar.getAttribute('y1');
                const left=p.matrixTransform(m).x;p.x=+bar.getAttribute('x2');
                const right=p.matrixTransform(m).x;
                return Math.abs(left-Math.max(a,b))<.1 || Math.abs(right-Math.min(a,b))<.1;
            }""")
        # A physical-distance annotation has a fixed schematic span, not a metre-to-pixel scale.
        distance = copy.deepcopy(SPEC)
        distance["zones"] = [{"from": "p1", "label": "Clearance", "distanceM": 500, "distanceDirection": "right"}]
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", distance)
        assert page.locator(".distance-zone .zone-label").text_content() == "Clearance - 500 m (NOT TO SCALE)"
        assert page.locator(".zone-span").evaluate("e => +e.getAttribute('x2') - +e.getAttribute('x1')") == 140
        before_distance = float(page.locator(".zone-span").get_attribute("x1"))
        distance["chain"][0]["x"] += 80
        distance["zones"][0]["distanceM"] = 1500
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", distance)
        assert abs(float(page.locator(".zone-span").get_attribute("x1")) - before_distance - 80) < .1
        assert page.locator(".zone-span").evaluate("e => +e.getAttribute('x2') - +e.getAttribute('x1')") == 140
        distance["zones"][0]["distanceDirection"] = "left"
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", distance)
        assert float(page.locator(".zone-span").get_attribute("x1")) < before_distance
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        distance_export = Path(directory) / "distance.svg"
        downloaded.value.save_as(distance_export)
        assert "1500 m (NOT TO SCALE)" in distance_export.read_text(encoding="utf-8")
        case_id, version = store.save("Distance zone", distance)
        html.write_text(build_html(store.load(case_id, version)), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert "1500 m (NOT TO SCALE)" in page.locator(".distance-zone").text_content()
        preset = get_preset("Two-template tieback to platform")
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", preset)
        assert page.locator("#design-zones .zone-span[marker-start]").count() == len(preset["zones"])
        preset["zones"].append({"from": preset["chain"][0]["id"], "distanceM": 50})
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", preset)
        assert page.locator(".distance-zone").count() == 1
        assert "50 m (NOT TO SCALE)" in page.locator(".distance-zone").text_content()
        check_adjustments(page, directory)
        assert not errors, errors
        browser.close()
        check_form(directory)
        check_live(directory, pw)
    print("PASS: zone dragging, units, anchoring, live synchronization, table edits and case/SVG persistence")


def check_adjustments(page, directory):
    def edit(name, value):
        page.locator("#z_" + name).fill(str(value))
        page.locator("#z_" + name).press("Tab")

    def geometry(index=0):
        return page.locator(f'.design-zone[data-zone="{index}"]').evaluate("""zone => {
            const span = zone.querySelector('.zone-span'), label = zone.querySelector('.zone-label text');
            return {left:+span.getAttribute('x1'),right:+span.getAttribute('x2'),y:+span.getAttribute('y1'),
                labelX:+label.getAttribute('x'),labelY:+label.getAttribute('y')};
        }""")

    def drag(part, dx, dy, cancel=False):
        target = page.locator(f'#svg [data-zone="0"][data-zone-part="{part}"]').last
        point = target.evaluate("""element => {
            const box=element.getBBox(), p=element.ownerSVGElement.createSVGPoint();
            p.x=box.x+box.width/2;p.y=box.y+box.height/2;
            const at=p.matrixTransform(element.getScreenCTM());
            const matrix=element.getScreenCTM();
            return {x:at.x,y:at.y,scale:matrix.a};
        }""")
        page.mouse.move(point["x"], point["y"])
        page.mouse.down()
        page.mouse.move(point["x"] + dx * point["scale"], point["y"] + dy * point["scale"], steps=8)
        if cancel:
            page.locator("#svg").dispatch_event("pointercancel")
        page.mouse.up()

    page.evaluate("spec => window.__subsea.replaceSpec(spec)", {"freeform": True, "chain": [], "showLegend": False})
    page.click("#b_palette")
    page.click('.palette-item[data-type="plet"]')
    page.click("#palette-close")
    page.click("#b_zone")
    assert "placement" not in (page.locator("#svg").get_attribute("class") or "").split()
    assert page.locator(".design-zone").count() == 1
    edit("label", "LC1")
    initial = geometry()
    drag("left", -35, 0)
    assert abs(geometry()["left"] - initial["left"] + 35) < .1
    assert abs(geometry()["right"] - initial["right"]) < .1
    drag("right", 65, 0)
    assert abs(geometry()["right"] - initial["right"] - 65) < .1
    drag("height", 0, -30)
    assert abs(geometry()["y"] - initial["y"] + 30) < .1
    before_label = geometry()
    drag("label", 18, -16)
    assert abs(geometry()["labelX"] - before_label["labelX"] - 18) < .1
    assert abs(geometry()["labelY"] - before_label["labelY"] + 16) < .1
    before_bottom = float(page.locator("#z_bottom").input_value())
    drag("bottom", 0, 40)
    assert abs(float(page.locator("#z_bottom").input_value()) - before_bottom - 40) < .1
    before_cancel = page.evaluate("structuredClone(window.__subsea.spec.zones[0])")
    drag("left", -20, 0, cancel=True)
    assert page.evaluate("window.__subsea.spec.zones[0]") == before_cancel
    # Unit changes preserve the physical value; boundary edits never change it.
    edit("distance", 2500)
    page.select_option("#z_unit", "km")
    assert float(page.locator("#z_distance").input_value()) == 2.5
    assert "2.5 km (NOT TO SCALE)" in page.locator(".zone-label").text_content()
    drag("right", 30, 0)
    assert page.evaluate("window.__subsea.spec.zones[0].distanceM") == 2500
    edit("distance", -1)
    assert "positive" in page.locator("#z_error").text_content()
    assert page.evaluate("window.__subsea.spec.zones[0].distanceM") == 2500
    edit("distance", 2.5)
    page.select_option("#z_arrows", "right")
    assert page.locator(".zone-span").get_attribute("marker-start") is None
    assert page.locator(".zone-span").get_attribute("marker-end") == "url(#arr)"
    first = page.evaluate("structuredClone(window.__subsea.spec.zones[0])")
    page.click("#z_add")
    edit("label", "LC2")
    page.click("#z_add")
    edit("label", "Fortified zone")
    assert page.locator(".design-zone").count() == 3
    page.select_option("#z_select", "0")
    assert page.evaluate("window.__subsea.spec.zones[0]") == first
    saved = page.evaluate("structuredClone(window.__subsea.spec)")
    assert not validate(saved)
    for update in ({"distanceUnit": "yards"}, {"labelDx": float("inf")}, {"rightOffset": first["leftOffset"]}):
        invalid = copy.deepcopy(saved)
        invalid["zones"][0].update(update)
        assert validate(invalid), update
    # The drawing geometry is retained in exports and case versions, without editing handles.
    expected = geometry()
    with page.expect_download() as downloaded:
        page.click("#b_svg")
    export = Path(directory) / "adjusted.svg"
    downloaded.value.save_as(export)
    svg = export.read_text(encoding="utf-8")
    assert all(label in svg for label in ("LC1", "LC2", "Fortified zone", "2.5 km"))
    assert "zone-controls" not in svg and 'class="zone-handle"' not in svg
    store = CaseStore(Path(directory) / "adjusted.sqlite3")
    case_id, version = store.save("Adjusted zones", saved)
    html = Path(directory) / "adjusted.html"
    html.write_text(build_html(store.load(case_id, version)), encoding="utf-8")
    page.goto(html.as_uri())
    page.wait_for_function("() => !!window.__subsea")
    assert geometry() == expected
    # Free/anchored conversion keeps the visible geometry, then follows its equipment.
    saved["chain"] = copy.deepcopy(SPEC["chain"])
    page.evaluate("spec => window.__subsea.replaceSpec(spec)", saved)
    page.click('#svg [data-zone="0"][data-zone-part="label"]')
    expected = geometry()
    page.select_option("#z_placement", "anchored")
    assert geometry() == expected
    anchored = page.evaluate("structuredClone(window.__subsea.spec)")
    anchored["chain"][0]["x"] += 90
    page.evaluate("spec => window.__subsea.replaceSpec(spec)", anchored)
    assert abs(geometry()["left"] - expected["left"] - 90) < .1
    assert abs(geometry()["right"] - expected["right"] - 90) < .1
    expected = geometry()
    page.select_option("#z_placement", "free")
    assert geometry() == expected
    free = page.evaluate("structuredClone(window.__subsea.spec)")
    free["chain"][0]["x"] += 90
    page.evaluate("spec => window.__subsea.replaceSpec(spec)", free)
    assert geometry() == expected
    page.click("#z_delete")
    assert page.locator(".design-zone").count() == 2
    # + Zone uses the currently selected equipment as an anchor.
    page.locator('[data-id="p1"] .hit').click()
    page.click("#b_zone")
    assert page.evaluate("window.__subsea.spec.zones.at(-1).from") == "p1"
    assert page.evaluate("window.__subsea.spec.zones.at(-1).placement") == "anchored"
    # Existing preset-style geometry stays unchanged when first edited, then follows equipment.
    legacy = {"chain": [{"id": "p1", "type": "plet"}, {"id": "p2", "type": "plet"}],
              "zones": [{"from": "p1", "to": "p2", "label": "Legacy zone"}], "showLegend": False}
    page.evaluate("spec => window.__subsea.replaceSpec(spec)", legacy)
    page.click("#b_fit")
    original = geometry()
    page.click('[data-zone="0"][data-zone-part="label"]')
    edit("label", "Adjusted legacy")
    assert all(abs(geometry()[key] - value) < .5 for key, value in original.items())
    legacy = page.evaluate("structuredClone(window.__subsea.spec)")
    legacy["overrides"]["p1"] = {"dx": -80}
    page.evaluate("spec => window.__subsea.replaceSpec(spec)", legacy)
    assert abs(geometry()["left"] - original["left"] + 80) < .1
    assert abs(geometry()["right"] - original["right"]) < .1


def check_form(directory):
    from streamlit.testing.v1 import AppTest
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        app.session_state.spec = copy.deepcopy(SPEC)
        app.session_state.ver += 1
        app.run()
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {}, "added_rows": [
            {"from": "p1", "to": "p2", "label": "Test zone", "edges": "both", "fromHost": False},
        ], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["zones"][0]["label"] == "Test zone"
        app.run()
        assert app.session_state.spec["zones"][0]["to"] == "p2"
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"label": "Edited zone"}}, "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert app.session_state.spec["zones"][0]["label"] == "Edited zone"
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {}, "added_rows": [], "deleted_rows": [0]}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert app.session_state.spec["zones"] == []
        assert not app.exception and not app.error
        # A partial new row must report an error rather than silently disappear.
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {}, "added_rows": [{"label": "Needs endpoints"}], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert any("select a start item" in error.value for error in app.error)
        assert app.session_state.spec["zones"] == []
        app.session_state.spec = {**copy.deepcopy(SPEC), "zones": [{"from": "p1"}]}
        app.session_state.ver += 1
        app.run()
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"to": "p2", "label": "Loaded zone"}}, "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert app.session_state.spec["zones"][0]["label"] == "Loaded zone"
        assert not app.exception and not app.error
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"distanceM": 250, "distanceDirection": "left"}},
                                  "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["zones"][0]["distanceM"] == 250
        assert app.session_state.spec["zones"][0]["distanceDirection"] == "left"
        previous = copy.deepcopy(app.session_state.spec["zones"])
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"distanceM": -1}}, "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert app.session_state.spec["zones"] == previous
        assert app.error
        # Editing the bulk table must not discard free geometry or label adjustments.
        free = {"placement": "free", "leftOffset": 100, "rightOffset": 400, "yOffset": 0,
                "bottomOffset": 200, "labelDx": 10, "labelDy": -12, "distanceM": 2500,
                "distanceUnit": "km", "arrows": "right", "edges": "both", "label": "LC1"}
        app.session_state.spec = {**copy.deepcopy(SPEC), "zones": [free]}
        app.session_state.ver += 1
        app.run()
        key = f"zones_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"label": "Updated LC1"}}, "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply zones").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["zones"] == [{**free, "label": "Updated LC1"}]
    finally:
        logging.disable(old_logging)
        if old_path is None:
            os.environ.pop("SUBSEA_CASES_PATH", None)
        else:
            os.environ["SUBSEA_CASES_PATH"] = old_path


def check_live(directory, pw):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {**os.environ, "SUBSEA_CASES_PATH": str(Path(directory) / "live.sqlite3")}
    with (Path(directory) / "live.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(root / "app.py"),
             "--server.headless=true", "--server.address=127.0.0.1",
             f"--server.port={port}", "--browser.gatherUsageStats=false"],
            env=environment, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(100):
                assert process.poll() is None, "Zone test server exited before readiness."
                try:
                    with urlopen(url + "/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except URLError:
                    time.sleep(.2)
            else:
                raise AssertionError("Zone test server did not become ready.")
            browser = pw.chromium.launch(executable_path=browser_executable())
            try:
                page = browser.new_page(viewport={"width": 1800, "height": 1200})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                component = page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000).content_frame()
                frame = component.wait_for_selector("#editor").content_frame()
                frame.wait_for_function("() => !!window.__subsea")
                frame.click("#b_zone")
                frame.locator("#z_label").fill("LC1 live")
                frame.locator("#z_distance").fill("1250")
                frame.locator("#z_distance").press("Tab")
                frame.select_option("#z_unit", "km")
                parent = page.get_by_label("Spec", exact=True)
                expect(parent).to_have_value(re.compile(r'.*"distanceUnit": "km".*', re.DOTALL), timeout=20000)
                zones = json.loads(parent.input_value())["zones"]
                assert zones[0]["label"] == "LC1 live" and zones[0]["distanceM"] == 1250
                right = float(frame.locator("#z_right").input_value()) + 100
                frame.locator("#z_right").fill(str(right))
                frame.locator("#z_right").press("Tab")
                stored_right = str(int(right)) if right.is_integer() else str(right)
                expect(parent).to_have_value(
                    re.compile(r'.*"rightOffset": ' + re.escape(stored_right) + r'.*', re.DOTALL), timeout=20000)
                expected = frame.evaluate("structuredClone(window.__subsea.spec.zones)")
                assert json.loads(parent.input_value())["zones"] == expected
                page.get_by_role("tab", name="Zones", exact=True).click()
                page.get_by_text("Advanced: zone table", exact=True).click()
                page.get_by_role("button", name="Apply zones", exact=True).click()
                expect(parent).to_have_value(re.compile(r'.*"LC1 live".*', re.DOTALL), timeout=20000)
                assert json.loads(parent.input_value())["zones"] == expected
                assert page.get_by_test_id("stException").count() == 0
                assert not errors, errors
            finally:
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=20)


if __name__ == "__main__":
    run()
