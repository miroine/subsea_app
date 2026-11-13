"""Costing quantities, tagging persistence and export regressions."""
import copy
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from subsea.installation import (apply_installation_rows, costing_excel, costing_notes,
                                 costing_pdf, installation_list, new_installation_summary)
from subsea.presets import get_preset
from subsea.catalog import BY_ID
from subsea.html import build_html
from subsea.cases import CaseStore
from test_connections import browser_executable, drag_ports
from playwright.sync_api import sync_playwright


class InstallationTests(unittest.TestCase):
    def setUp(self):
        tag = dict(installationStatus="New", provider="Supplier A",
                   installationType="VXT", rating="10 K psi")
        self.spec = {
            "host": {"type": "jacket", "id": "host", "installationStatus": "Existing",
                     "risers": [{"lane": "P", **tag}]},
            "chain": [{"type": "vxt", "id": "a", **tag},
                      {"type": "vxt", "id": "b", **tag},
                      {"type": "vxt", "id": "old", "installationStatus": "Existing"},
                      {"type": "vxt", "id": "unclassified"}],
            "connections": [{"from": "a", "to": "b", "kind": "jumper", **tag,
                             "installedLengthKm": 1.25}],
        }

    def test_exact_scope_and_grouping(self):
        inventory = installation_list(self.spec)
        self.assertEqual(len(inventory), 7)
        summary = new_installation_summary(inventory)
        trees = summary.loc[summary["Equipment"] == BY_ID["vxt"]["name"]]
        self.assertEqual(int(trees["Qty"].sum()), 2)
        self.assertEqual(int(summary["Qty"].sum()), 4)
        self.assertEqual(summary["Installed length (km)"].sum(), 1.25)
        self.assertEqual(int(summary["Unknown lengths"].sum()), 3)
        self.assertTrue(any("1 Unspecified" in note for note in costing_notes(inventory)))

    def test_atomic_tagging_preserves_design(self):
        before = copy.deepcopy(self.spec)
        rows = installation_list(self.spec).to_dict("records")
        next(row for row in rows if row["Reference"] == "main/host/risers/0")["Rating"] = "15 K psi"
        result = apply_installation_rows(self.spec, rows)
        self.assertEqual(result["host"]["risers"][0]["rating"], "15 K psi")
        self.assertEqual(self.spec, before)
        self.assertEqual(result["connections"][0]["installedLengthKm"], 1.25)
        with tempfile.TemporaryDirectory(prefix="subsea-installation-case-") as directory:
            store = CaseStore(Path(directory) / "cases.sqlite3")
            case_id, version = store.save("Tagged installation", result)
            self.assertEqual(store.load(case_id, version), result)
            self.assertEqual(int(new_installation_summary(installation_list(store.load(case_id, version)))["Qty"].sum()), 4)
        rows[1]["Provider"] = None
        cleared = apply_installation_rows(self.spec, rows)
        self.assertEqual(cleared["chain"][0]["provider"], "")
        rows[-1]["Installed length (km)"] = -1
        with self.assertRaises(ValueError):
            apply_installation_rows(self.spec, rows)
        self.assertEqual(self.spec, before)

    def test_excel_exact_rows_and_literal_text(self):
        self.spec["chain"][0]["provider"] = "=SUM(1,2)"
        inventory = installation_list(self.spec)
        book = load_workbook(BytesIO(costing_excel(inventory)))
        sheet = book["New equipment"]
        self.assertEqual(sheet.max_row, 5)
        rows = list(sheet.values)
        provider_index = rows[0].index("Provider")
        self.assertIn("=SUM(1,2)", [row[provider_index] for row in rows[1:]])
        self.assertTrue(all(cell.data_type != "f" for row in sheet for cell in row))
        self.assertEqual(sum(row[list(book["Quantities"].values)[0].index("Qty")]
                             for row in list(book["Quantities"].values)[1:]), 4)
        self.assertTrue(costing_pdf(inventory).startswith(b"%PDF-"))
        empty = installation_list(get_preset("Blank canvas – draw your own"))
        self.assertEqual(load_workbook(BytesIO(costing_excel(empty)))["New equipment"].max_row, 1)
        self.assertTrue(costing_pdf(empty).startswith(b"%PDF-"))

    def test_blank_start_and_selected_tags(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.spec["chain"], [])
        self.assertIsNone(app.session_state.spec["host"])
        app.session_state.spec = copy.deepcopy(self.spec)
        app.session_state.selected_element = "a"
        app.session_state.ver += 1
        app.run()
        self.assertFalse(app.exception)
        next(widget for widget in app.text_input if widget.label == "Rating").set_value("15 K psi")
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.spec["chain"][0]["rating"], "15 K psi")

    def test_drawing_defaults_tags_copy_and_reload(self):
        spec = {"freeform": True, "host": None, "showLegend": False, "animate": False,
                "chain": [{"type": "plet", "id": "a", "x": 100, "y": 120},
                          {"type": "plet", "id": "b", "x": 450, "y": 260}]}
        with tempfile.TemporaryDirectory(prefix="subsea-installation-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable())
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            html = Path(directory) / "drawing.html"
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            page.locator('[data-id="a"] .hit').click(force=True, position={"x": 3, "y": 3})
            self.assertEqual(page.locator("#i_installationStatus").input_value(), "Unspecified")
            page.select_option("#i_installationStatus", "Existing")
            for key, value in (("provider", "Supplier A"), ("installationType", "PLET"), ("rating", "10 K psi")):
                page.fill(f"#i_{key}", value)
                page.locator(f"#i_{key}").press("Tab")
            page.click("#i_copy")
            copied = page.evaluate("window.__subsea.spec.chain.find(i => i.id === 'a_2')")
            self.assertEqual(copied["installationStatus"], "New")
            self.assertEqual(copied["rating"], "10 K psi")
            page.click("#i_delete")
            page.click("#b_connect")
            drag_ports(page, ("a", "P-right"), ("b", "P-left"))
            self.assertEqual(page.evaluate("window.__subsea.spec.connections[0].installationStatus"), "New")
            page.click("#b_connect")
            saved = page.evaluate("window.__subsea.spec")
            html.write_text(build_html(saved), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            loaded = page.evaluate("window.__subsea.spec")
            self.assertEqual(loaded["chain"][0]["rating"], "10 K psi")
            self.assertEqual(loaded["chain"][0]["installationStatus"], "Existing")
            self.assertEqual(loaded["connections"][0]["installationStatus"], "New")
            self.assertFalse(errors)
            browser.close()


if __name__ == "__main__":
    unittest.main()
