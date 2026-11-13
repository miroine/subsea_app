"""Detailed riser-base topology, editing and live persistence."""
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
import unittest
import xml.etree.ElementTree as ET
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect, sync_playwright
from streamlit.testing.v1 import AppTest

from subsea.cases import CaseStore
from subsea.equipment import customization_errors, removed_port_errors
from subsea.html import build_html
from subsea.riser_detail import blank_element_configuration, illustrated_riser_configuration
from subsea.spec import chain_to_df, df_to_chain, validate
from test_connections import browser_executable

ROOT = Path(__file__).resolve().parents[1]


def spec():
    return {"freeform": True, "showLegend": False, "animate": False,
            "chain": [{"id": "rb", "type": "riser_base", "x": 200, "y": 200},
                      {"id": "p", "type": "plet", "x": 800, "y": 300}]}


def point(page, x, y):
    return page.locator("#rd-svg").evaluate("""(svg, at) => {
        const p=svg.createSVGPoint();p.x=at.x;p.y=at.y;
        const q=p.matrixTransform(svg.getScreenCTM());return {x:q.x,y:q.y};
    }""", {"x": x, "y": y})


def click(page, x, y):
    p = point(page, x, y)
    page.mouse.click(p["x"], p["y"])


def drag(page, x, y, to_x, to_y):
    a, b = point(page, x, y), point(page, to_x, to_y)
    page.mouse.move(a["x"], a["y"])
    page.mouse.down()
    page.mouse.move(b["x"], b["y"], steps=8)
    page.mouse.up()


def edit(page, field, value):
    page.locator("#rd-field-" + field).fill(str(value))
    page.locator("#rd-field-" + field).press("Tab")


class RiserDetailTests(unittest.TestCase):
    def test_custom_shape_validation(self):
        item = {"id": "custom", "type": "custom_element", **blank_element_configuration()}
        item["riserDetail"]["shapes"] = [
            {"id": "box", "kind": "rect", "x": 10, "y": 10, "width": 100, "height": 80},
            {"id": "circle", "kind": "ellipse", "x": 140, "y": 10, "width": 80, "height": 80},
            {"id": "line", "kind": "line", "x": 20, "y": 120, "x2": 200, "y2": 120},
            {"id": "text", "kind": "text", "x": 20, "y": 150, "text": "<Module & pump>", "fontSize": 14},
        ]
        self.assertFalse(customization_errors(item))
        for index, key, value in [(0, "width", -1), (0, "x", 400), (1, "fill", "url(http://example.com)"),
                                  (2, "x2", float("inf")), (3, "fontSize", True), (3, "text", []),
                                  (1, "id", "box"), (0, "strokeWidth", 100)]:
            bad = copy.deepcopy(item)
            bad["riserDetail"]["shapes"][index][key] = value
            self.assertTrue(customization_errors(bad), (index, key))
        restored, problems = df_to_chain(chain_to_df([item]))
        self.assertFalse(problems)
        self.assertEqual(restored[0]["riserDetail"], item["riserDetail"])

    def test_custom_element_drawing_reuse_and_network(self):
        with tempfile.TemporaryDirectory(prefix="subsea-custom-element-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1800, "height": 1100}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                html = Path(directory) / "custom.html"
                html.write_text(build_html({**spec(), "chain": [spec()["chain"][1]]}), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                page.click("#b_custom_element")
                expect(page.get_by_role("dialog", name="Custom element designer")).to_be_visible()
                model = lambda: page.evaluate("structuredClone(window.__subsea.spec.chain.find(i=>i.type==='custom_element'))")
                self.assertEqual(model()["riserDetail"], blank_element_configuration()["riserDetail"])
                self.assertEqual(page.locator('[data-id="custom_element_1"] .connection-port').count(), 0)
                for kind, a, b in [("rect", (20, 30), (120, 100)), ("ellipse", (180, 30), (260, 110)),
                                   ("line", (30, 150), (260, 150))]:
                    page.click(f'[data-mode="{kind}"]')
                    drag(page, *a, *b)
                    self.assertEqual(model()["riserDetail"]["shapes"][-1]["kind"], kind)
                page.click('[data-mode="text"]')
                click(page, 140, 185)
                edit(page, "text", "Custom <pump> & skid")
                page.locator("#rd-field-stroke").fill("#0070c0")
                page.locator("#rd-field-stroke").press("Tab")
                self.assertIn("Custom <pump> & skid", page.locator("#rd-svg").text_content())
                # Move and resize a shape without disturbing other geometry.
                click(page, 20, 50)
                original = model()["riserDetail"]["shapes"][0]
                drag(page, 20, 50, 40, 60)
                moved = model()["riserDetail"]["shapes"][0]
                self.assertAlmostEqual(moved["x"], original["x"] + 20, delta=.01)
                self.assertAlmostEqual(moved["y"], original["y"] + 10, delta=.01)
                drag(page, moved["x"] + moved["width"], moved["y"] + moved["height"], 160, 130)
                self.assertAlmostEqual(model()["riserDetail"]["shapes"][0]["width"], 120, delta=.01)
                before = model()["riserDetail"]
                edit(page, "width", -1)
                self.assertIn("Changes not saved", page.locator("#rd-error").text_content())
                self.assertEqual(model()["riserDetail"], before)
                # Decorative lines can be removed independently of connected piping.
                click(page, 100, 150)
                page.keyboard.press("Delete")
                self.assertEqual(len(model()["riserDetail"]["shapes"]), 3)
                page.click('[data-mode="hub"]')
                click(page, 0, 240)
                click(page, 420, 240)
                page.click('[data-mode="pipe"]')
                click(page, 0, 240)
                click(page, 420, 240)
                page.click('[data-mode="valve"]')
                click(page, 210, 240)
                edit(page, "tag", "XV-CUSTOM")
                network = page.evaluate("structuredClone(window.__subsea.spec)")
                network["connections"] = [{"from": "custom_element_1", "fromPort": "P-out-1",
                                           "to": "p", "toPort": "P-left", "lane": "P"}]
                page.evaluate("s=>window.__subsea.replaceSpec(s)", network)
                self.assertFalse(validate(network))
                self.assertTrue(page.locator("#connection-line-0").evaluate("""path=>{
                    const port=document.querySelector('.el[data-id="custom_element_1"] .connection-port[data-port="P-out-1"]');
                    const p=path.ownerSVGElement.createSVGPoint();p.x=+port.dataset.x;p.y=+port.dataset.y;
                    const at=p.matrixTransform(path.getCTM().inverse().multiply(port.closest('.el').getCTM()));
                    const start=path.getPointAtLength(0);return Math.hypot(at.x-start.x,at.y-start.y)<.01;
                }"""))
                before = model()
                page.click("#rd-template-load")
                self.assertIn("Connected hub", page.locator("#rd-error").text_content())
                self.assertEqual(model(), before)
                with page.expect_download() as downloaded:
                    page.click("#rd-export")
                template = Path(directory) / "template.json"
                downloaded.value.save_as(template)
                text = next(s for s in model()["riserDetail"]["shapes"] if s["kind"] == "text")
                page.click('[data-mode="select"]')
                click(page, text["x"] + 5, text["y"] - 3)
                edit(page, "text", "Changed wording")
                page.locator("#rd-import").set_input_files(template)
                page.wait_for_function("()=>window.__subsea.spec.chain.find(i=>i.type==='custom_element').riserDetail.shapes.some(s=>s.text==='Custom <pump> & skid')")
                self.assertEqual(model()["riserDetail"], before["riserDetail"])
                click(page, 350, 310)
                page.locator("#rd-show-frame").uncheck()
                page.locator("#rd-width").fill("500")
                page.locator("#rd-width").press("Tab")
                self.assertFalse(model()["riserDetail"]["showFrame"])
                self.assertAlmostEqual(model()["riserDetail"]["shapes"][0]["width"], 120 * 500 / 420, delta=.01)
                page.click("#rd-close")
                with page.expect_download() as downloaded:
                    page.click("#b_svg")
                exported = Path(directory) / "custom.svg"
                downloaded.value.save_as(exported)
                root = ET.fromstring(exported.read_text(encoding="utf-8"))
                self.assertIn("Custom <pump> & skid", "".join(root.itertext()))
                self.assertIn("XV-CUSTOM", "".join(root.itertext()))
                self.assertEqual(page.locator(".detail-shape").count(), 3)
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertFalse(validate(saved))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case, version = store.save("Custom drawing", saved)
                html.write_text(build_html(store.load(case, version)), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                self.assertEqual(page.locator(".detail-shape").count(), 3)
                page.locator('[data-id="custom_element_1"] .hit').click(force=True, position={"x": 3, "y": 3})
                page.click("#b_copy")
                self.assertEqual(page.locator(".detail-shape").count(), 6)
                copies = page.evaluate("window.__subsea.spec.chain.filter(i=>i.type==='custom_element')")
                self.assertEqual(copies[0]["riserDetail"], copies[1]["riserDetail"])
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_validation_and_connected_hubs(self):
        item = {**spec()["chain"][0], **illustrated_riser_configuration()}
        self.assertFalse(customization_errors(item))
        for path, value in [
            (("width",), False),
            (("hubs", 0, "x"), 5),
            (("junctions", 0, "y"), float("inf")),
            (("routes", 0, "to"), "@missing"),
            (("routes", 0, "service"), []),
            (("routes", 0, "points"), [{"x": 1, "y": None}]),
        ]:
            invalid = copy.deepcopy(item)
            target = invalid["riserDetail"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            self.assertTrue(customization_errors(invalid), path)
        invalid = copy.deepcopy(item)
        invalid["internalValves"][0]["pipe"] = "route-missing"
        self.assertTrue(customization_errors(invalid))
        # Removing an unused but externally connected hub must still be blocked.
        item["riserDetail"]["hubs"].append(
            {"id": "S-in-8", "x": 300, "y": 340, "side": "bottom", "service": "meg", "label": "Extra"})
        network = {**spec(), "connections": [{"from": "rb", "fromPort": "S-in-8", "to": "p", "toPort": "S-left", "lane": "S"}]}
        item["riserDetail"]["hubs"].pop()
        self.assertTrue(removed_port_errors(network, item))
        self.assertFalse(validate({**spec(), "chain": [item, spec()["chain"][1]]}))

    def test_graphical_editor_and_exports(self):
        with tempfile.TemporaryDirectory(prefix="subsea-riser-detail-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable())
            try:
                page = browser.new_page(viewport={"width": 1700, "height": 1100}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                html = Path(directory) / "detail.html"
                html.write_text(build_html(spec()), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("() => !!window.__subsea")
                page.locator('[data-id="rb"] .hit').click(force=True, position={"x": 3, "y": 3})
                page.click("#b_riser_detail")
                expect(page.locator(".riser-detail-editor")).to_be_visible()
                self.assertEqual(page.locator(".riser-detail-body").count(), 1)
                before = page.locator('[data-rd-type="valve"][data-rd-id="v1"]').get_attribute("transform")
                page.click('[data-mode="junction"]')
                click(page, 190, 130)
                self.assertEqual(page.locator('[data-rd-type="valve"][data-rd-id="v1"]').get_attribute("transform"), before)
                item = page.evaluate("structuredClone(window.__subsea.spec.chain[0])")
                self.assertFalse(customization_errors(item))
                self.assertEqual(item["riserDetail"]["routes"][1]["to"], "@j1")
                page.click('[data-mode="pipe"]')
                click(page, 190, 130)
                click(page, 190, 180)
                click(page, 260, 205)
                item = page.evaluate("structuredClone(window.__subsea.spec.chain[0])")
                branch = item["riserDetail"]["routes"][-1]
                self.assertEqual((branch["from"], branch["to"]), ("@j1", "@cross_lower"))
                page.click('[data-mode="valve"]')
                click(page, 190, 160)
                page.click('[data-mode="select"]')
                click(page, 190, 160)
                page.select_option("#rd-field-kind", "check")
                edit(page, "tag", "NRV-NEW")
                edit(page, "rating", "10 K psi")
                page.locator('[data-field="closed"]').check()
                item = page.evaluate("structuredClone(window.__subsea.spec.chain[0])")
                valve = next(v for v in item["internalValves"] if v["tag"] == "NRV-NEW")
                self.assertEqual((valve["kind"], valve["rating"], valve["closed"]), ("check", "10 K psi", True))
                drag(page, 190, 160, 215, 190)
                new_valve = page.evaluate("window.__subsea.spec.chain[0].internalValves.find(v=>v.tag==='NRV-NEW')")
                self.assertNotEqual(new_valve["position"], valve["position"])
                self.assertEqual(new_valve["pipe"], valve["pipe"])
                drag(page, 190, 130, 205, 120)
                junction = page.evaluate("window.__subsea.spec.chain[0].riserDetail.junctions.find(j=>j.id==='j1')")
                self.assertAlmostEqual(junction["x"], 205, delta=.01)
                self.assertAlmostEqual(junction["y"], 120, delta=.01)
                location = page.locator("#rd-route-" + branch["id"]).evaluate(
                    "p=>{const q=p.getPointAtLength(p.getTotalLength()*.15);return {x:q.x,y:q.y};}")
                click(page, location["x"], location["y"])
                bend = page.locator(".rd-bend").first
                location = bend.evaluate("c=>({x:+c.getAttribute('cx'),y:+c.getAttribute('cy')})")
                drag(page, location["x"], location["y"], 220, 185)
                route = page.evaluate("id=>window.__subsea.spec.chain[0].riserDetail.routes.find(r=>r.id===id)", branch["id"])
                self.assertAlmostEqual(route["points"][0]["x"], 220, delta=.01)
                page.select_option("#rd-service", "meg")
                page.click('[data-mode="hub"]')
                click(page, 300, 340)
                edit(page, "label", "Future takeoff")
                hub = page.evaluate("window.__subsea.spec.chain[0].riserDetail.hubs.at(-1)")
                self.assertEqual(hub["side"], "bottom")
                connected = page.evaluate("structuredClone(window.__subsea.spec)")
                connected["connections"] = [{"from": "rb", "fromPort": hub["id"], "to": "p", "toPort": "S-left", "lane": "S"}]
                page.evaluate("s=>window.__subsea.replaceSpec(s)", connected)
                page.click('[data-mode="select"]')
                click(page, 300, 340)
                page.keyboard.press("Delete")
                self.assertIn("Connected hub", page.locator("#rd-error").text_content())
                page.select_option("#rd-field-service", "spare")
                self.assertIn("cannot change lane", page.locator("#rd-error").text_content())
                self.assertEqual(page.locator(f'.connection-port[data-port="{hub["id"]}"]').get_attribute("data-axis"), "y")
                # Attachment geometry is verified, not only a port inventory entry.
                self.assertTrue(page.locator("#connection-line-0").evaluate("""path => {
                    const port=document.querySelector('.el[data-id="rb"] .connection-port[data-axis="y"][data-port="S-in-4"]');
                    const el=port.closest('.el'), p=path.ownerSVGElement.createSVGPoint();
                    p.x=+port.dataset.x;p.y=+port.dataset.y;
                    const at=p.matrixTransform(path.getCTM().inverse().multiply(el.getCTM())), first=path.getPointAtLength(0);
                    return Math.hypot(at.x-first.x,at.y-first.y)<.01;
                }"""))
                with page.expect_download() as downloaded:
                    page.click("#rd-export")
                template = Path(directory) / "layout.json"
                downloaded.value.save_as(template)
                data = json.loads(template.read_text(encoding="utf-8"))
                self.assertFalse(customization_errors({"id": "copy", "type": "riser_base", **{
                    k: data[k] for k in ("riserDetail", "internalValves")}}))
                edit(page, "label", "Changed after export")
                page.locator("#rd-import").set_input_files(template)
                page.wait_for_function("id=>window.__subsea.spec.chain[0].riserDetail.hubs.find(h=>h.id===id)?.label==='Future takeoff'",
                                       arg=hub["id"])
                self.assertEqual(page.evaluate("window.__subsea.spec.chain[0].riserDetail"), data["riserDetail"])
                page.click("#rd-close")
                with page.expect_download() as downloaded:
                    page.click("#b_svg")
                export = Path(directory) / "detail.svg"
                downloaded.value.save_as(export)
                drawing = export.read_text(encoding="utf-8")
                self.assertIn("NRV-NEW", drawing)
                self.assertIn("riser-detail-body", drawing)
                self.assertNotIn("rd-svg", drawing)
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertFalse(validate(saved))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case, version = store.save("Detailed riser", saved)
                html.write_text(build_html(store.load(case, version)), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("() => !!window.__subsea")
                self.assertEqual(page.locator(".custom-internal-valve").count(), len(saved["chain"][0]["internalValves"]))
                self.assertEqual(page.locator(".detailed-internal-route").count(), len(saved["chain"][0]["riserDetail"]["routes"]))
                page.locator('[data-id="rb"] .hit').click(force=True, position={"x": 3, "y": 3})
                page.click("#b_riser_detail")
                # Clicking two pipes directly creates a crossover with connected junctions on both.
                original_nodes = len(saved["chain"][0]["riserDetail"]["junctions"])
                page.select_option("#rd-service", "production")
                page.click('[data-mode="pipe"]')
                click(page, 320, 130)
                click(page, 320, 180)
                click(page, 150, 205)
                changed = page.evaluate("structuredClone(window.__subsea.spec.chain[0])")
                self.assertEqual(len(changed["riserDetail"]["junctions"]), original_nodes + 2)
                crossover = changed["riserDetail"]["routes"][-1]
                self.assertTrue(crossover["from"].startswith("@") and crossover["to"].startswith("@"))
                self.assertFalse(customization_errors(changed))
                self.assertEqual(len(changed["internalValves"]), len(saved["chain"][0]["internalValves"]))
                page.click('[data-mode="select"]')
                click(page, 20, 20)
                page.locator("#rd-width").fill("500")
                page.locator("#rd-width").press("Tab")
                resized = page.evaluate("structuredClone(window.__subsea.spec.chain[0])")
                self.assertEqual(resized["riserDetail"]["width"], 500)
                self.assertFalse(customization_errors(resized))
                self.assertEqual(resized["internalValves"], changed["internalValves"])
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_parent_settings_preserve_detail(self):
        with tempfile.TemporaryDirectory(prefix="subsea-detail-settings-") as directory:
            old = os.environ.get("SUBSEA_CASES_PATH")
            old_logging = logging.root.manager.disable
            os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
            logging.disable(logging.WARNING)
            try:
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
                original = {**spec()["chain"][0], **illustrated_riser_configuration()}
                app.session_state.spec = {**spec(), "chain": [original]}
                app.session_state.selected_element = "rb"
                app.session_state.ver += 1
                app.run()
                next(field for field in app.text_input if field.label == "Element label").set_value("My detailed base").run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertEqual(app.session_state.spec["chain"][0]["riserDetail"], original["riserDetail"])
                self.assertNotIn("riserPorts", app.session_state.spec["chain"][0])
                self.assertNotIn("internalRoutes", app.session_state.spec["chain"][0])
            finally:
                logging.disable(old_logging)
                if old is None:
                    os.environ.pop("SUBSEA_CASES_PATH", None)
                else:
                    os.environ["SUBSEA_CASES_PATH"] = old

    def test_live_detail_editor_synchronization(self):
        with tempfile.TemporaryDirectory(prefix="subsea-detail-live-") as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            environment = {**os.environ, "SUBSEA_CASES_PATH": str(Path(directory) / "live.sqlite3")}
            with (Path(directory) / "server.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless=true",
                     "--server.address=127.0.0.1", f"--server.port={port}", "--browser.gatherUsageStats=false"],
                    env=environment, stdout=log, stderr=subprocess.STDOUT)
                try:
                    url = f"http://127.0.0.1:{port}"
                    for _ in range(100):
                        self.assertIsNone(process.poll(), "Test Streamlit server exited.")
                        try:
                            with urlopen(url + "/_stcore/health", timeout=1) as response:
                                if response.status == 200:
                                    break
                        except URLError:
                            time.sleep(.2)
                    else:
                        self.fail("Test Streamlit server did not become ready.")
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(executable_path=browser_executable())
                        try:
                            page = browser.new_page(viewport={"width": 1800, "height": 1200})
                            errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.on("dialog", lambda dialog: dialog.accept())
                            page.goto(url)
                            page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000)
                            page.locator('input[type="file"]').set_input_files({
                                "name": "base.json", "mimeType": "application/json", "buffer": json.dumps(spec()).encode()})
                            parent = page.get_by_label("Spec", exact=True)
                            expect(parent).to_have_value(re.compile(r'.*"id": "rb".*', re.DOTALL), timeout=20000)
                            component = page.locator('iframe[title="subsea.viewer.subsea_editor"]').element_handle().content_frame()
                            frame = component.wait_for_selector("#editor").content_frame()
                            frame.wait_for_function("()=>window.__subsea.spec.chain.some(i=>i.id==='rb')", timeout=20000)
                            frame.locator('[data-id="rb"] .hit').click(force=True, position={"x": 3, "y": 3})
                            frame.click("#b_riser_detail")
                            frame.locator('[data-rd-type="valve"][data-rd-id="v1"]').click(force=True)
                            edit(frame, "tag", "XV-LIVE")
                            edit(frame, "rating", "10 K psi")
                            expect(parent).to_have_value(re.compile(r'.*"XV-LIVE".*', re.DOTALL), timeout=20000)
                            expect(parent).to_have_value(re.compile(r'.*"10 K psi".*', re.DOTALL), timeout=20000)
                            expected = frame.evaluate("structuredClone(window.__subsea.spec.chain[0].riserDetail)")
                            page.get_by_label("Element label", exact=True).fill("Detailed live base")
                            page.get_by_label("Element label", exact=True).press("Tab")
                            try:
                                frame.wait_for_function("()=>window.__subsea.spec.overrides.rb?.label==='Detailed live base'", timeout=20000)
                            except PlaywrightTimeoutError:
                                self.fail("Parent label edit failed: " + str({
                                    "errors": page.get_by_test_id("stAlert").all_text_contents(),
                                    "exception": page.get_by_test_id("stException").all_text_contents(),
                                    "label": page.get_by_label("Element label", exact=True).input_value(),
                                    "overrides": frame.evaluate("window.__subsea.spec.overrides"),
                                }))
                            self.assertEqual(frame.evaluate("window.__subsea.spec.chain[0].riserDetail"), expected)
                            self.assertEqual(frame.evaluate("window.__subsea.spec.chain[0].internalValves[0].rating"), "10 K psi")
                            page.locator('iframe[title="subsea.viewer.subsea_editor"]').scroll_into_view_if_needed()
                            frame.click("#rd-close")
                            frame.click("#b_custom_element")
                            frame.click('[data-mode="text"]')
                            frame.locator("#rd-svg").click()
                            edit(frame, "text", "CUSTOM-LIVE-DRAWING")
                            expect(parent).to_have_value(re.compile(r'.*"CUSTOM-LIVE-DRAWING".*', re.DOTALL), timeout=20000)
                            custom_layout = frame.evaluate("structuredClone(window.__subsea.spec.chain.find(i=>i.type==='custom_element').riserDetail)")
                            page.get_by_label("Element label", exact=True).fill("My custom module")
                            page.get_by_label("Element label", exact=True).press("Tab")
                            frame.wait_for_function("()=>window.__subsea.spec.overrides.custom_element_1?.label==='My custom module'", timeout=20000)
                            self.assertEqual(frame.evaluate("window.__subsea.spec.chain.find(i=>i.type==='custom_element').riserDetail"), custom_layout)
                            self.assertIn("CUSTOM-LIVE-DRAWING", frame.locator("#rd-svg").text_content())
                            page.locator('iframe[title="subsea.viewer.subsea_editor"]').scroll_into_view_if_needed()
                            frame.click("#rd-close")
                            frame.click("#b_3d")
                            frame.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0 || document.querySelector('#scene3d-error').textContent", timeout=30000)
                            self.assertEqual(frame.locator("#scene3d-error").text_content(), "")
                            frame.evaluate("()=>{window.retained3D=window.__subsea.scene3D;window.__subsea.move3DEquipment('custom_element_1',32,18)}")
                            expect(parent).to_have_value(re.compile(r'.*"dx": 32.*"dy": 18.*', re.DOTALL), timeout=20000)
                            before_camera = frame.evaluate("window.__subsea.scene3D.diagnostics().camera")
                            page.get_by_label("Element label", exact=True).fill("Live 3D module")
                            page.get_by_label("Element label", exact=True).press("Tab")
                            frame.wait_for_function("()=>window.__subsea.spec.overrides.custom_element_1?.label==='Live 3D module'", timeout=20000)
                            self.assertTrue(frame.evaluate("window.retained3D===window.__subsea.scene3D && window.__subsea.scene3D.diagnostics().active"))
                            self.assertEqual(frame.evaluate("window.__subsea.scene3D.diagnostics().camera"), before_camera)
                            self.assertEqual(frame.evaluate("window.__subsea.spec.chain.find(i=>i.type==='custom_element').riserDetail"), custom_layout)
                            self.assertEqual(frame.evaluate("window.__subsea.spec.overrides.custom_element_1.dx"), 32)
                            self.assertEqual(page.get_by_test_id("stException").count(), 0)
                            self.assertFalse(errors, errors)
                        finally:
                            browser.close()
                finally:
                    process.terminate()
                    process.wait(timeout=20)


if __name__ == "__main__":
    unittest.main()
