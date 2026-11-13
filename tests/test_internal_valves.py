"""Internal valve editing, route anchoring, validation and persisted metadata."""
import copy
from io import BytesIO
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
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl import load_workbook
from playwright.sync_api import expect, sync_playwright
from streamlit.testing.v1 import AppTest

from subsea.bom import equipment_list
from subsea.cases import CaseStore
from subsea.catalog import NODE_IDS
from subsea.equipment import customization_errors, furb_configuration
from subsea.html import build_html
from subsea.installation import costing_excel, costing_pdf, installation_list
from subsea.valves import VALVE_TYPES, internal_valve_errors
from test_connections import assert_attached, browser_executable


ROOT = Path(__file__).resolve().parents[1]


def example():
    return {
        "freeform": True, "host": None, "animate": False, "showLegend": False,
        "chain": [{"id": "p", "type": "plet", "x": 100, "y": 120, "installationStatus": "New"},
                  {"id": "base", "type": "riser_base", "x": 450, "y": 260, **furb_configuration()}],
        "connections": [{"from": "p", "to": "base", "fromPort": "P-right", "toPort": "P-left", "lane": "P"}],
    }


def configured_valve(**changes):
    return {"id": "v1", "pipe": "P-1", "kind": "control", "position": 60,
            "closed": True, "tag": "CV-101", "label": "Injection isolation",
            "provider": "Supplier A", "rating": "10 K psi", **changes}


class InternalValveTests(unittest.TestCase):
    def test_validation(self):
        valve = configured_valve()
        item = {"id": "p", "type": "plet", "internalValves": [valve]}
        self.assertEqual(customization_errors(item), [])
        self.assertTrue(internal_valve_errors(item, {"missing"}))
        for field, value in (("id", ""), ("kind", "invalid"), ("kind", []),
                             ("position", -1), ("position", float("inf")),
                             ("position", True), ("position", None), ("closed", "yes"), ("rating", 10000)):
            invalid = {**item, "internalValves": [{**valve, field: value}]}
            self.assertTrue(customization_errors(invalid), (field, value))
        self.assertTrue(customization_errors({**item, "internalValves": [valve, valve]}))
        self.assertTrue(customization_errors({**item, "internalValves": {}}))
        self.assertEqual(customization_errors({**item, "internalValves": []}), [])

    def test_metadata_in_case_and_costing(self):
        spec = example()
        spec["chain"][0]["internalValves"] = [configured_valve()]
        with tempfile.TemporaryDirectory(prefix="subsea-valve-case-") as directory:
            store = CaseStore(Path(directory) / "cases.sqlite3")
            case_id, version = store.save("Custom internal valves", spec)
            self.assertEqual(store.load(case_id, version), spec)
        bom = equipment_list(spec)
        metadata = bom.loc[bom["Id"] == "p", "Internal valves (JSON)"].iloc[0]
        self.assertEqual(json.loads(metadata), spec["chain"][0]["internalValves"])
        inventory = installation_list(spec)
        workbook = load_workbook(BytesIO(costing_excel(inventory)))
        rows = list(workbook["New equipment"].values)
        self.assertEqual(len(rows), 2)
        self.assertEqual(json.loads(rows[1][rows[0].index("Internal valves (JSON)")])[0]["provider"], "Supplier A")
        self.assertTrue(costing_pdf(inventory).startswith(b"%PDF-"))

    def test_drawing_editor_and_anchoring(self):
        with tempfile.TemporaryDirectory(prefix="subsea-valves-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable())
            page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            spec = example()
            html = Path(directory) / "valves.html"
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            page.locator('[data-id="p"] .hit').click(force=True, position={"x": 3, "y": 3})
            options = page.evaluate("window.__subsea.getInternalValveOptions()")
            self.assertEqual(len(options["defaults"]), 1)
            self.assertTrue(options["pipes"])
            self.assertNotIn("internalValves", page.evaluate("window.__subsea.spec.chain[0]"))
            expect(page.locator("#i_valve_add")).to_be_visible()
            self.assertEqual(page.get_by_role("button", name=re.compile("Apply")).count(), 0)
            row = page.locator(".internal-valve-row").first
            valve_id = row.locator(".valve-id").input_value()
            row.locator(".valve-id").fill("invalid id")
            self.assertFalse(row.locator(".valve-id").evaluate("input => input.checkValidity()"))
            row.locator(".valve-id").fill(valve_id)
            row.locator(".valve-kind").select_option("control")
            row.locator(".valve-pipe").select_option("P-1")
            row.locator(".valve-position").fill("60")
            row.locator(".valve-closed").check()
            for field, value in (("tag", "CV-101"), ("label", "Injection isolation"),
                                 ("provider", "Supplier A"), ("rating", "10 K psi")):
                row.locator(f".valve-{field}").fill(value)
            page.locator("#insp").click(position={"x": 1, "y": 1})
            saved = page.evaluate("window.__subsea.spec")
            self.assertEqual(saved["chain"][0]["internalValves"][0]["rating"], "10 K psi")
            self.assertEqual(saved["connections"], spec["connections"])
            self.assertEqual(saved["chain"][0]["portConfig"] if "portConfig" in saved["chain"][0] else None, None)
            marker = page.locator('[data-id="p"] .custom-internal-valve')
            self.assertEqual(marker.get_attribute("data-kind"), "control")
            self.assertEqual(marker.get_attribute("data-closed"), "true")
            self.assertTrue(marker.evaluate("""marker => {
                const element = marker.closest('.el');
                const pipe = element.querySelector('[data-internal-pipe="P-1"]');
                const point = pipe.getPointAtLength(pipe.getTotalLength() * .6);
                const position = marker.transform.baseVal.getItem(0).matrix;
                return Math.hypot(position.e-point.x,position.f-point.y)<.01;
            }"""))
            assert_attached(page, ("p", "P-right"), ("base", "P-left"))
            page.click("#i_valve_add")
            second = page.locator(".internal-valve-row").last
            second.locator(".valve-kind").select_option("psv")
            second.locator(".valve-tag").fill("PSV-INTERNAL")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            self.assertEqual(page.locator('[data-id="p"] .custom-internal-valve').count(), 2)
            # Duplicate IDs must leave the last committed design unchanged.
            committed = page.evaluate("window.__subsea.spec")
            first_id = page.locator(".valve-id").first.input_value()
            page.locator(".valve-id").last.fill(first_id)
            page.locator("#insp").click(position={"x": 1, "y": 1})
            self.assertIn("unique", page.locator("#i_valve_error").text_content())
            self.assertEqual(page.evaluate("window.__subsea.spec"), committed)
            html.write_text(build_html(committed), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            self.assertEqual(page.locator('[data-id="p"] .custom-internal-valve').count(), 2)
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            export = Path(directory) / "valves.svg"
            downloaded.value.save_as(export)
            exported = export.read_text(encoding="utf-8")
            for text in ("CV-101", "PSV-INTERNAL", "Supplier A", "10 K psi"):
                self.assertIn(text, exported)
            # Custom valves can anchor to named FURB routes rather than only straight lanes.
            routed = copy.deepcopy(committed)
            routed["chain"][1]["internalValves"] = [configured_valve(pipe="route-process")]
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", routed)
            self.assertEqual(page.locator('[data-id="base"] .custom-internal-valve').count(), 1)
            self.assertEqual(page.locator(".internal-valve-error").count(), 0)
            # Moving and scaling retains the pipe fraction and external port attachments.
            routed["chain"][0]["x"] += 150
            routed["overrides"] = {"p": {"scale": .7}}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", routed)
            assert_attached(page, ("p", "P-right"), ("base", "P-left"))
            self.assertTrue(page.locator('[data-id="p"] .custom-internal-valve').first.evaluate("""marker => {
                const pipe=marker.closest('.el').querySelector('[data-internal-pipe="P-1"]');
                const point=pipe.getPointAtLength(pipe.getTotalLength()*.6);
                const position=marker.transform.baseVal.getItem(0).matrix;
                return Math.hypot(position.e-point.x,position.f-point.y)<.01;
            }"""))
            mirrored = {**routed, "chain": [], "branches": [{"chain": routed["chain"], "mirror": True}]}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", mirrored)
            self.assertTrue(page.locator('[data-id="p"] .custom-internal-valve > text').first.evaluate("""text => {
                const matrix = text.getCTM();
                return matrix.a * matrix.d - matrix.b * matrix.c > 0;
            }"""))
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", routed)
            page.locator('[data-id="p"] .hit').click(force=True, position={"x": 3, "y": 3})
            expect(page.locator("#i_valve_add")).to_be_visible()
            while page.locator(".valve-remove").count():
                page.locator(".valve-remove").first.click()
            page.locator("#insp").click(position={"x": 1, "y": 1})
            self.assertEqual(page.evaluate("window.__subsea.spec.chain[0].internalValves"), [])
            self.assertEqual(page.locator('[data-id="p"] .custom-internal-valve').count(), 0)
            page.click("#i_valve_restore")
            self.assertNotIn("internalValves", page.evaluate("window.__subsea.spec.chain[0]"))
            self.assertTrue(page.locator('[data-id="p"] .default-internal-valve').is_visible())
            self.assertFalse(errors, errors)
            browser.close()

    def test_equipment_families_and_valve_types(self):
        with tempfile.TemporaryDirectory(prefix="subsea-valve-families-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable())
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            spec = example()
            html = Path(directory) / "valves.html"
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            representative = {"plet", "plem", "template", "manifold", "riser_base", "riser_skid", "vxt", "hxt", "hipps", "mpp"}
            for equipment in NODE_IDS:
                candidate = {"freeform": True, "host": None, "animate": False, "showLegend": False,
                             "chain": [{"id": "equipment", "type": equipment, "x": 100, "y": 120}]}
                if equipment == "template":
                    candidate["chain"][0]["treeType"] = "vxt"
                page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
                pipes = page.locator('[data-id="equipment"] [data-internal-pipe]')
                if equipment in ("efl", "custom_element"):
                    self.assertEqual(pipes.count(), 0)
                    continue
                self.assertGreater(pipes.count(), 0, equipment)
                pipe_id = pipes.first.get_attribute("data-internal-pipe")
                for kind in VALVE_TYPES if equipment in representative else ("gate",):
                    candidate["chain"][0]["internalValves"] = [configured_valve(pipe=pipe_id, kind=kind)]
                    page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
                    self.assertEqual(page.locator(".custom-internal-valve").count(), 1, (equipment, kind))
                    self.assertEqual(page.locator(".internal-valve-error").count(), 0, (equipment, kind))
            candidate["chain"][0]["internalValves"][0]["pipe"] = "missing"
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
            self.assertIn("not available", page.locator(".internal-valve-error").text_content())
            browser.close()

    def test_selected_settings_automatic_updates(self):
        previous_logging = logging.root.manager.disable
        previous_path = os.environ.get("SUBSEA_CASES_PATH")
        logging.disable(logging.WARNING)
        try:
            with tempfile.TemporaryDirectory(prefix="subsea-valve-form-") as directory:
                os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
                spec = example()
                spec["chain"][0]["internalValves"] = [configured_valve()]
                app.session_state.spec = copy.deepcopy(spec)
                app.session_state.selected_element = "p"
                app.session_state.internal_valve_options = {"pipes": [{"id": "P-1", "lane": "P"}], "defaults": []}
                app.session_state.ver += 1
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state.spec["chain"], spec["chain"])
                self.assertFalse(any(button.label == "Apply element settings" for button in app.button))
                key = f"internal_valves_p_{app.session_state.ver}"
                app.session_state[key] = {"edited_rows": {0: {"kind": "check", "provider": "Supplier B", "position": 25}},
                                          "added_rows": [], "deleted_rows": []}
                app.run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                valve = app.session_state.spec["chain"][0]["internalValves"][0]
                self.assertEqual((valve["kind"], valve["provider"], valve["position"]), ("check", "Supplier B", 25))
                self.assertEqual(app.session_state.spec["connections"], spec["connections"])
                committed = copy.deepcopy(app.session_state.spec)
                next(widget for widget in app.text_area if widget.label == "Element properties (JSON)").set_value("{")
                app.run()
                self.assertTrue(app.error)
                self.assertEqual(app.session_state.spec, committed)
                next(widget for widget in app.text_area if widget.label == "Element properties (JSON)").set_value(
                    json.dumps({"x": 100, "y": 120, "installationStatus": "New"}))
                app.run()
                self.assertFalse(app.error)
                next(widget for widget in app.checkbox if widget.label == "Customize internal valves (replace defaults)").set_value(False)
                app.run()
                self.assertFalse(app.exception)
                self.assertNotIn("internalValves", app.session_state.spec["chain"][0])
        finally:
            logging.disable(previous_logging)
            if previous_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = previous_path

    def test_live_editor_synchronizes_valve_options(self):
        with tempfile.TemporaryDirectory(prefix="subsea-live-valves-") as directory:
            environment = {**os.environ, "SUBSEA_CASES_PATH": str(Path(directory) / "cases.sqlite3")}
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with (Path(directory) / "server.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                     "--server.headless=true", "--server.address=127.0.0.1",
                     f"--server.port={port}", "--browser.gatherUsageStats=false"],
                    env=environment, stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    url = f"http://127.0.0.1:{port}"
                    for _ in range(100):
                        if process.poll() is not None:
                            self.fail("Streamlit exited before readiness.")
                        try:
                            with urlopen(url + "/_stcore/health", timeout=1) as response:
                                if response.status == 200:
                                    break
                        except URLError:
                            time.sleep(.2)
                    else:
                        self.fail("Streamlit did not become ready.")
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(executable_path=browser_executable())
                        page = browser.new_page(viewport={"width": 1800, "height": 1200})
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(url)
                        page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000)
                        page.locator('input[type="file"]').set_input_files({
                            "name": "valves.json", "mimeType": "application/json",
                            "buffer": json.dumps(example()).encode(),
                        })
                        expect(page.get_by_label("Spec", exact=True)).to_have_value(
                            re.compile(r'.*"id": "p".*', re.DOTALL), timeout=20000)
                        component = page.locator('iframe[title="subsea.viewer.subsea_editor"]').element_handle().content_frame()
                        frame = component.wait_for_selector("#editor").content_frame()
                        frame.wait_for_function("() => window.__subsea.spec.chain.some(item => item.id === 'p')", timeout=20000)
                        frame.locator('[data-id="p"] .hit').click(force=True, position={"x": 3, "y": 3})
                        checkbox = page.get_by_label("Customize internal valves (replace defaults)", exact=True)
                        expect(checkbox).to_be_attached(timeout=15000)
                        page.get_by_role("tab", name="Selected item", exact=True).click()
                        page.get_by_text("Customize internal valves (replace defaults)", exact=True).click()
                        expect(checkbox).to_be_checked()
                        valve_panel = page.get_by_test_id("stExpander").filter(
                            has=page.locator("summary").get_by_text("Internal valves", exact=True))
                        expect(valve_panel.get_by_test_id("stDataFrame")).to_be_visible(timeout=5000)
                        frame.wait_for_function("() => window.__subsea.spec.chain[0].internalValves?.length === 1", timeout=15000)
                        expect(frame.locator("#i_valve_add")).to_be_visible()
                        frame.locator(".valve-tag").fill("CV-LIVE")
                        frame.locator(".valve-rating").fill("10 K psi")
                        frame.locator(".valve-rating").press("Tab")
                        frame.locator("#insp").click(position={"x": 1, "y": 1})
                        expect(page.get_by_label("Spec", exact=True)).to_have_value(
                            re.compile(r'.*CV-LIVE.*', re.DOTALL), timeout=15000)
                        # A parent-side settings edit must retain the viewer's valve customization.
                        page.get_by_label("Element label", exact=True).fill("Customized PLET")
                        page.get_by_label("Element size (%)", exact=True).fill("120")
                        page.get_by_label("Element size (%)", exact=True).press("Tab")
                        frame.wait_for_function(
                            "() => window.__subsea.spec.overrides.p?.label === 'Customized PLET' && window.__subsea.spec.overrides.p?.scale === 1.2",
                            timeout=15000)
                        self.assertEqual(frame.evaluate("window.__subsea.spec.chain[0].internalValves[0].tag"), "CV-LIVE")
                        self.assertEqual(frame.evaluate("window.__subsea.spec.chain[0].internalValves[0].rating"), "10 K psi")
                        self.assertEqual(page.get_by_test_id("stException").count(), 0)
                        self.assertFalse(errors)
                        browser.close()
                finally:
                    process.terminate()
                    process.wait(timeout=20)


if __name__ == "__main__":
    unittest.main()
