"""Equipment option browser tests: python tests\\test_equipment_options.py."""
import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import browser_executable, drag_ports, assert_attached
from subsea.catalog import NODE_IDS
from subsea.html import build_html
from subsea.spec import validate


def select_item(page, item_id):
    page.locator(f'.el[data-id="{item_id}"] .hit').click(force=True, position={"x": 2, "y": 2})


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-equipment-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "equipment.html"
        spec = {
            "freeform": True, "host": None, "animate": False, "showLegend": False,
            "designLimits": {"pressureBar": 345, "temperatureC": 120, "waterDepthM": 1500, "flowM3Day": 5000},
            "chain": [
                {"id": "base", "type": "riser_base", "x": 80, "y": 300},
                {"id": "template", "type": "template", "x": 600, "y": 300},
                {"id": "skid", "type": "riser_skid", "x": 400, "y": 600},
            ],
        }
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        select_item(page, "base")
        page.check("#i_ports_enabled")
        page.select_option("#i_port_mode", "replace")
        page.fill("#i_inlets", "2")
        page.fill("#i_outlets", "3")
        page.fill("#i_limit_pressureBar", "450")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="base"] .connection-port').count() == 5
        assert page.locator('[data-id="base"] .custom-hub').count() == 5
        assert "450" in page.locator('[data-id="base"] > title').text_content()
        assert page.locator("#i_limit_waterDepthM").get_attribute("placeholder") == "Default: 1500"
        select_item(page, "template")
        page.uncheck("#i_hipps")
        page.fill("#i_wells", "6")
        page.select_option("#i_tree", "hxt")
        page.check("#i_ports_enabled")
        page.fill("#i_inlets", "2")
        page.fill("#i_outlets", "1")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator(".template-tree").count() == 6
        assert page.locator('.template-tree[data-tree-type="hxt"]').count() == 6
        assert page.locator(".template-hipps").count() == 0
        assert page.locator('[data-id="template"] .custom-hub').count() == 3
        print("PASS: riser base inlet/outlet counts, template HIPPS/trees/wells, and inherited design limits")
        page.locator("#insp").evaluate("element => element.style.display='none'")
        page.click("#b_connect")
        source, target = ("base", "P-out-2"), ("template", "P-in-1")
        drag_ports(page, source, target)
        assert_attached(page, source, target)
        page.click("#b_connect")
        select_item(page, "template")
        page.fill("#i_inlets", "0")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_equipment_error").text_content()
        assert page.evaluate("window.__subsea.spec.chain[1].portConfig.inlets") == 2
        page.fill("#i_inlets", "2")
        page.check("#i_hipps")
        page.select_option("#i_tree", "vxt")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator(".template-hipps").count() == 1
        assert page.locator('.template-tree[data-tree-type="vxt"]').count() == 6
        assert_attached(page, source, target)
        page.fill("#i_limit_pressureBar", "0")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "greater than" in page.locator("#i_equipment_error").text_content()
        page.fill("#i_limit_pressureBar", "")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert_attached(page, source, target)
        page.click("#i_copy")
        copy_id = page.evaluate("window.__subsea.sel")
        assert page.locator(f'[data-id="{copy_id}"] .template-tree').count() == 6
        assert page.locator(f'[data-id="{copy_id}"] .custom-hub').count() == 3
        page.click("#i_delete")
        print("PASS: custom hub dragging, connected-port removal guard, HIPPS/tree changes, invalid limits, copy")
        with page.expect_download() as downloaded:
            page.click("#b_json")
        saved = Path(directory) / "equipment.json"
        downloaded.value.save_as(saved)
        restored = json.loads(saved.read_text(encoding="utf-8"))
        assert validate(restored) == [], validate(restored)
        html.write_text(build_html(restored), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_attached(page, source, target)
        assert page.locator(".template-hipps").count() == 1
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg = Path(directory) / "equipment.svg"
        downloaded.value.save_as(svg)
        exported = browser.new_page()
        exported.goto(svg.as_uri())
        assert exported.locator(".connection-port").count() == 0
        assert exported.locator(".custom-hub").count() == 8
        assert exported.locator(".template-tree").count() == 6
        assert "450" in exported.locator('[data-id="base"] > title').text_content()
        exported.close()
        print("PASS: JSON/SVG preserve configured hubs, tree symbols, HIPPS, limits, and attachments")
        spec["chain"] = [
            {"id": type_id, "type": type_id, "x": 100 + (index % 8) * 400, "y": 200 + (index // 8) * 400,
             "portConfig": {"mode": "additional", "lane": "P", "inlets": 2, "outlets": 3}}
            for index, type_id in enumerate(NODE_IDS)
        ]
        html.write_text(build_html(spec), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        for type_id in NODE_IDS:
            assert page.locator(f'[data-id="{type_id}"] .custom-hub').count() == 5, type_id
        ids = page.evaluate("window.Subsea.ids()")
        assert set(NODE_IDS) == set(ids["node"])
        print(f"PASS: configurable inlet/outlet hubs render on all {len(NODE_IDS)} equipment types")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    run()
