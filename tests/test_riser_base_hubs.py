"""Riser-base hub count edits must not be silently ignored by the enable checkbox."""
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, drag_ports
from subsea.equipment import removed_port_errors
from subsea.html import build_html
from subsea.spec import validate


def run():
    spec = {
        "freeform": True, "host": None, "animate": False, "showLegend": False,
        "chain": [
            {"id": "base", "type": "riser_base", "x": 100, "y": 180},
            {"id": "plet", "type": "plet", "x": 600, "y": 180},
        ],
    }
    with tempfile.TemporaryDirectory(prefix="subsea-base-hubs-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
        assert not page.locator("#i_ports_enabled").is_checked()
        page.fill("#i_inlets", "2")
        page.fill("#i_outlets", "3")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.evaluate("window.__subsea.spec.chain[0].portConfig") == {
            "mode": "additional", "lane": "P", "inlets": 2, "outlets": 3,
        }
        assert page.locator('[data-id="base"] .custom-hub').count() == 5
        assert_internal_hubs(page, "base")
        assert page.locator('[data-id="base"] .connection-port').count() == 7
        assert page.locator("#i_ports_enabled").is_checked()
        print("PASS: entering riser-base hub counts automatically enables customization instead of discarding the counts")
        page.locator("#insp").evaluate("e => e.style.display='none'")
        page.click("#b_connect")
        drag_ports(page, ("base", "P-out-3"), ("plet", "P-left"))
        assert_attached(page, ("base", "P-out-3"), ("plet", "P-left"))
        page.click("#b_connect")
        page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
        page.fill("#i_inlets", "4")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="base"] .custom-hub').count() == 7
        assert_internal_hubs(page, "base")
        assert_attached(page, ("base", "P-out-3"), ("plet", "P-left"))
        page.uncheck("#i_ports_enabled")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_equipment_error").text_content()
        assert page.locator('[data-id="base"] .custom-hub').count() == 7
        saved = page.evaluate("window.__subsea.spec")
        html.write_text(build_html(saved), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator('[data-id="base"] .custom-hub').count() == 7
        assert_attached(page, ("base", "P-out-3"), ("plet", "P-left"))
        for type_id in ("riser_base", "riser_skid"):
            candidate = {**saved, "chain": [{**saved["chain"][0], "type": type_id}, saved["chain"][1]]}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.check("#i_service_ports")
            page.check("#i_umbilical_ports")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator('[data-id="base"] .connection-port').count() == 13, page.evaluate("window.__subsea.spec.chain[0]")
            assert_internal_hubs(page, "base")
            assert_attached(page, ("base", "P-out-3"), ("plet", "P-left"))
            page.locator("#insp").evaluate("e => e.style.display='none'")
            page.click("#b_connect")
            for lane, index in (("S", 1), ("U", 2)):
                drag_ports(page, ("base", f"{lane}-right"), ("plet", f"{lane}-left"))
                assert_attached(page, ("base", f"{lane}-right"), ("plet", f"{lane}-left"), index)
                page.locator("#insp").evaluate("e => e.style.display='none'")
            assert page.locator("#connection-line-1").get_attribute("stroke") == "#E87500"
            connected = page.evaluate("window.__subsea.spec")
            assert validate(connected) == []
            html.write_text(build_html(connected), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            for lane, index in (("S", 1), ("U", 2)):
                assert_attached(page, ("base", f"{lane}-right"), ("plet", f"{lane}-left"), index)
            assert_internal_hubs(page, "base")
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            for field, checkbox in (("servicePorts", "#i_service_ports"), ("umbilicalPorts", "#i_umbilical_ports")):
                page.uncheck(checkbox)
                page.locator("#insp").click(position={"x": 1, "y": 1})
                assert "connected" in page.locator("#i_equipment_error").text_content()
                assert removed_port_errors(connected, {**connected["chain"][0], field: False})
                assert page.locator(".connection").count() == 3
                page.check(checkbox)
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            auxiliary_export = Path(directory) / "auxiliary.svg"
            downloaded.value.save_as(auxiliary_export)
            exported = browser.new_page()
            exported.goto(auxiliary_export.as_uri())
            assert_internal_hubs(exported, "base")
            assert exported.locator(".custom-hub[data-hub='S-right']").count() == 1
            assert exported.locator(".custom-hub[data-hub='U-right']").count() == 1
            exported.close()
        print("PASS: optional S/U pairs on base and skid connect beside process/custom hubs, survive reload/export and protect occupied ports")
        for type_id in ("riser_base", "riser_skid"):
            for mode in ("additional", "replace"):
                for lane in ("P", "S", "U"):
                    for count in (1, 3, 24):
                        candidate = {
                            **saved, "connections": [],
                            "chain": [{"id": "base", "type": type_id, "x": 100, "y": 180,
                                       "servicePorts": True, "umbilicalPorts": True,
                                       "portConfig": {"mode": mode, "lane": lane, "inlets": count, "outlets": count}}],
                        }
                        page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
                        assert_internal_hubs(page, "base")
                        assert page.locator('[data-id="base"] .connection-port').evaluate_all("""ports =>
                          ports.every((port, index) => ports.slice(index + 1).every(other =>
                            Math.hypot(+port.dataset.x - +other.dataset.x,
                              +port.dataset.y - +other.dataset.y) >= 22))""")
        print("PASS: base/skid frames contain all hub piping and labels for P/S/U, additional/total modes and 1-24 hubs")
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        export = Path(directory) / "internal-hubs.svg"
        downloaded.value.save_as(export)
        exported = browser.new_page()
        exported.goto(export.as_uri())
        assert_internal_hubs(exported, "base")
        exported.close()
        print("PASS: exported SVG retains the equipment enclosure and its internal hub connections")
        assert not errors, errors
        browser.close()
        print("PASS: additional hubs connect, grow without losing routes, survive reload and cannot be disabled while connected")
    test_settings_form()


def assert_internal_hubs(page, item_id):
    problems = page.locator(f'[data-id="{item_id}"]').evaluate("""element => {
      const frame = element.querySelector('.riser-frame rect').getBBox(), problems = [];
      for (const hub of element.querySelectorAll('.custom-hub')) {
        const box = hub.getBBox();
        if (box.x < frame.x || box.y < frame.y
          || box.x + box.width > frame.x + frame.width + .01
          || box.y + box.height > frame.y + frame.height + .01) problems.push(hub.dataset.hub);
      }
      return problems;
    }""")
    assert not problems, f"Custom hub branches/labels outside equipment box: {problems}"


def test_settings_form():
    from streamlit.testing.v1 import AppTest
    with tempfile.TemporaryDirectory(prefix="subsea-base-form-") as directory:
        previous_path = os.environ.get("SUBSEA_CASES_PATH")
        previous_logging = logging.root.manager.disable
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state.spec = {
                "freeform": True, "host": None,
                "chain": [{"id": "base", "type": "riser_base", "x": 100, "y": 200}],
            }
            app.session_state.selected_element = "base"
            app.run()
            next(check for check in app.checkbox if check.label == "Include chemical / service connections").check()
            next(check for check in app.checkbox if check.label == "Include umbilical connections").check()
            for label, value in (("Inlet connections", 3), ("Outlet connections", 2)):
                next(input_ for input_ in app.number_input if input_.label == label).set_value(value)
            app.run()
            assert not app.exception and not app.error
            assert app.session_state.spec["chain"][0]["portConfig"] == {
                "mode": "additional", "lane": "P", "inlets": 3, "outlets": 2,
            }
            assert next(check for check in app.checkbox if check.label == "Customize inlet/outlet hubs").value
            assert app.session_state.spec["chain"][0]["servicePorts"] is True
            assert app.session_state.spec["chain"][0]["umbilicalPorts"] is True
            next(check for check in app.checkbox if check.label == "Customize inlet/outlet hubs").uncheck()
            next(check for check in app.checkbox if check.label == "Include chemical / service connections").uncheck()
            next(check for check in app.checkbox if check.label == "Include umbilical connections").uncheck()
            app.run()
            assert "portConfig" not in app.session_state.spec["chain"][0]
            assert app.session_state.spec["chain"][0]["servicePorts"] is False
            assert app.session_state.spec["chain"][0]["umbilicalPorts"] is False
            assert not app.exception and not app.error
        finally:
            logging.disable(previous_logging)
            if previous_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = previous_path
    print("PASS: settings below the drawing enable optional service/umbilical pairs and hub counts; unused options can be disabled")


if __name__ == "__main__":
    run()
