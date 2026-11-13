"""PLET single-pair option, compatibility and occupied-port protection."""
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, drag_ports
from subsea.equipment import effective_port_lane, removed_port_errors
from subsea.html import build_html
from subsea.spec import validate


def run():
    spec = {"freeform": True, "host": None, "showLegend": False, "animate": False,
            "chain": [{"id": "p", "type": "plet", "x": 100, "y": 150},
                      {"id": "t", "type": "template", "x": 500, "y": 150}]}
    with tempfile.TemporaryDirectory(prefix="subsea-plet-ports-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator('[data-id="p"] .connection-port').count() == 6
        for lane, colour in (("S", "#E87500"), ("U", "#667085")):
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", spec)
            page.locator('[data-id="p"] .hit').click(force=True, position={"x": 35, "y": 5})
            page.select_option("#i_plet_ports", lane)
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator('[data-id="p"] .connection-port').evaluate_all(
                "ports => ports.map(port => port.dataset.port).sort()") == [f"{lane}-left", f"{lane}-right"]
            assert page.locator('[data-id="p"] .plet-port-section').count() == 2
            assert page.locator('[data-id="p"] .plet-frame rect').get_attribute("height") == "44"
            assert page.locator('[data-id="p"] .plet-port-section line').first.get_attribute("stroke") == colour
            assert page.locator('[data-id="p"]').evaluate("""element => {
                const frame = element.querySelector('.plet-frame rect').getBBox();
                return [...element.querySelectorAll('.connection-port')].every(port =>
                    +port.dataset.y > frame.y && +port.dataset.y < frame.y + frame.height);
            }""")
            page.locator("#insp").evaluate("e => e.style.display='none'")
            page.click("#b_connect")
            drag_ports(page, ("p", f"{lane}-right"), ("t", f"{lane}-left"))
            assert_attached(page, ("p", f"{lane}-right"), ("t", f"{lane}-left"))
            connected = page.evaluate("window.__subsea.spec")
            assert validate(connected) == []
            assert page.locator("#connection-line-0").get_attribute("stroke") == colour
            html.write_text(build_html(connected), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert_attached(page, ("p", f"{lane}-right"), ("t", f"{lane}-left"))
            page.locator('[data-id="p"] .hit').click(force=True, position={"x": 35, "y": 5})
            page.select_option("#i_plet_ports", "P")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert "connected" in page.locator("#i_equipment_error").text_content()
            assert removed_port_errors(connected, {**connected["chain"][0], "pletPorts": "P"})
            assert_attached(page, ("p", f"{lane}-right"), ("t", f"{lane}-left"))
        print("PASS: service-only and umbilical-only PLETs have compact matching pairs, attach correctly, reload and protect connections")
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", spec)
        page.locator('[data-id="p"] .hit').click(force=True, position={"x": 35, "y": 5})
        page.select_option("#i_plet_ports", "P")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p"] .connection-port').count() == 2
        page.select_option("#i_port_id", "P-right")
        page.fill("#i_port_label", "Chemical outlet")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p"] text').filter(has_text="Chemical outlet").count() == 1
        page.select_option("#i_port_service", "chemical")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-right"] line').first.get_attribute("stroke") == "#E87500"
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-left"] line').first.get_attribute("stroke") != "#E87500"
        page.select_option("#i_port_id", "P-left")
        page.fill("#i_port_label", "Water inlet")
        page.select_option("#i_port_service", "water_injection")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-left"] line').first.get_attribute("stroke") == "#0077CC"
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-right"] line').first.get_attribute("stroke") == "#E87500"
        individual = page.evaluate("window.__subsea.spec")
        html.write_text(build_html(individual), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator('[data-id="p"] text').filter(has_text="Chemical outlet").count() == 1
        assert page.locator('[data-id="p"] text').filter(has_text="Water inlet").count() == 1
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-left"] line').first.get_attribute("stroke") == "#0077CC"
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-right"] line').first.get_attribute("stroke-dasharray") == "5 2"
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        export = Path(directory) / "independent-plet.svg"
        downloaded.value.save_as(export)
        exported = browser.new_page()
        exported.goto(export.as_uri())
        assert exported.locator('[data-id="p"] text').filter(has_text="Chemical outlet").count() == 1
        assert exported.locator('[data-id="p"] .plet-port-section[data-section="P-left"] line').first.get_attribute("stroke") == "#0077CC"
        assert exported.locator('[data-id="p"] .plet-port-section[data-section="P-right"] line').first.get_attribute("stroke") == "#E87500"
        exported.close()
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", {**individual, "themeName": "mono"})
        for port in ("P-left", "P-right"):
            assert page.locator(f'[data-id="p"] .plet-port-section[data-section="{port}"] line').first.get_attribute("stroke") == "#111111"
        assert page.locator('[data-id="p"] .plet-port-section[data-section="P-left"] line').first.get_attribute("stroke-dasharray") == "4 4"
        print("PASS: PLET inlet/outlet independently show labels, colours and dash patterns through reload, SVG export and monochrome theme")
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", {**spec, "chain": [
            {**spec["chain"][0], "pletPorts": "P"}, spec["chain"][1],
        ]})
        assert page.locator('[data-id="p"] .connection-port').evaluate_all(
            "es => es.map(e => e.dataset.port).sort()") == ["P-left", "P-right"]
        frame_height = float(page.locator('[data-id="p"] .plet-frame rect').get_attribute("height"))
        assert frame_height == 44
        saved = page.evaluate("window.__subsea.spec")
        assert validate(saved) == []
        html.write_text(build_html(saved), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator('[data-id="p"] .connection-port').count() == 2
        saved["chain"][0]["pletPorts"] = "PSU"
        saved["connections"] = [{"from": "p", "to": "t", "fromPort": "S-right", "toPort": "S-left", "lane": "S"}]
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", saved)
        page.locator('[data-id="p"] .hit').click(force=True, position={"x": 35, "y": 5})
        page.select_option("#i_plet_ports", "P")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_equipment_error").text_content()
        assert page.locator('[data-id="p"] .connection-port').count() == 6
        assert page.locator(".connection").count() == 1
        assert removed_port_errors(saved, {**saved["chain"][0], "pletPorts": "P"})
        chemical = {
            **spec, "connections": [],
            "chain": [
                {"id": "p", "type": "plet", "pletPorts": "P", "x": 100, "y": 150,
                 "portOverrides": {"P-left": {"lane": "P", "connectionType": "chemical"},
                                   "P-right": {"lane": "P", "connectionType": "chemical"}}},
                spec["chain"][1],
            ],
        }
        legacy = {**chemical, "connections": [
            {"from": "p", "to": "t", "fromPort": "P-right", "toPort": "P-left", "lane": "P",
             "waypoints": [{"x": 350, "y": 260}]},
        ]}
        html.write_text(build_html(legacy), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_attached(page, ("p", "P-right"), ("t", "P-left"))
        assert page.evaluate("window.__subsea.spec.connections[0].waypoints") == legacy["connections"][0]["waypoints"]
        assert any("changing lane" in error for error in validate(legacy))
        print("PASS: legacy P-lane chemical PLET attachment and route remain visible; validation flags mismatch")
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", chemical)
        assert page.locator('[data-id="p"] [data-port="P-right"]').get_attribute("data-lane") == "S"
        page.locator("#insp").evaluate("e => e.style.display='none'")
        page.click("#b_connect")
        drag_ports(page, ("p", "P-right"), ("t", "S-left"))
        assert_attached(page, ("p", "P-right"), ("t", "S-left"))
        assert page.locator("#connection-line-0").get_attribute("stroke") == "#E87500"
        connected = page.evaluate("window.__subsea.spec")
        assert connected["connections"][0]["lane"] == "S"
        assert validate(connected) == []
        html.write_text(build_html(connected), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_attached(page, ("p", "P-right"), ("t", "S-left"))
        page.locator('[data-id="p"] .hit').click(force=True, position={"x": 35, "y": 5})
        page.select_option("#i_port_id", "P-right")
        page.select_option("#i_port_service", "gas")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_port_error").text_content()
        assert_attached(page, ("p", "P-right"), ("t", "S-left"))
        page.select_option("#i_port_id", "P-left")
        page.select_option("#i_port_service", "umbilical_static")
        assert page.locator("#i_port_compatible").input_value() == "U"
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p"] [data-port="P-left"]').get_attribute("data-lane") == "U"
        print("PASS: chemical-only PLET connects to orange template service port, survives reload and guards incompatible service changes")
        browser.close()
        print("PASS: PLET has exactly one inlet/outlet with compact frame; reload and connected S/U guards work")
        test_form(directory, spec)


def test_form(directory, spec):
    from streamlit.testing.v1 import AppTest
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        app.session_state.spec = spec
        app.session_state.selected_element = "p"
        app.run()
        next(select for select in app.selectbox if select.label == "PLET standard ports").set_value("P")
        app.run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["pletPorts"] == "P"
        assert "portConfig" not in app.session_state.spec["chain"][0]
        print("PASS: single-pair PLET is configurable from settings below the drawing")
        for mode in ("S", "U", "P"):
            next(select for select in app.selectbox if select.label == "PLET standard ports").set_value(mode)
            app.run()
            assert not app.exception and not app.error
            assert app.session_state.spec["chain"][0]["pletPorts"] == mode
        print("PASS: settings below the drawing switch between service-only, umbilical-only and process-only PLETs")
        app.session_state.selected_ports = [
            {"id": port, "label": port, "lane": "P", "connectionType": ""}
            for port in ("P-left", "P-right")
        ]
        app.run()
        key = f"port_settings_p_{app.session_state.ver}"
        app.session_state[key] = {
            "edited_rows": {0: {"Fluid / service": "chemical"}, 1: {"Fluid / service": "chemical"}},
            "added_rows": [], "deleted_rows": [],
        }
        app.run()
        assert not app.exception and not app.error
        plet = app.session_state.spec["chain"][0]
        assert all(effective_port_lane(plet, port) == "S" for port in ("P-left", "P-right"))
        connected = {**app.session_state.spec, "connections": [
            {"from": "p", "to": "t", "fromPort": "P-right", "toPort": "S-left", "lane": "S"},
        ]}
        assert not removed_port_errors(connected, plet)
        assert validate(connected) == []
        print("PASS: below-drawing table assigns chemical compatibility despite old process Lane value")
    finally:
        logging.disable(old_logging)
        if old_path is None:
            os.environ.pop("SUBSEA_CASES_PATH", None)
        else:
            os.environ["SUBSEA_CASES_PATH"] = old_path


if __name__ == "__main__":
    run()
