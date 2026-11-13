"""Connect an extra FURB hub internally without disturbing its external pig receiver."""
import copy
import json
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable
from test_custom_riser import custom_base
from subsea.html import build_html
from subsea.cases import CaseStore
from subsea.equipment import connect_internal_hub
from subsea.spec import validate


def example():
    base = custom_base()
    base["riserPorts"]["P"] = {"inlets": 2, "outlets": 2}
    return {"freeform": True, "host": None, "animate": False, "showLegend": False,
            "chain": [base, {"id": "receiver", "type": "pig_receiver", "x": 450, "y": 206}],
            "connections": [{"from": "base", "fromPort": "P-out-1", "to": "receiver",
                             "toPort": "P-left", "lane": "P"}]}


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-furb-branch-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        spec = example()
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
        assert page.locator("#i_connect_internal_hub").count() == 1, "No simple internal hub connection control"
        page.select_option("#i_internal_hub", "P-out-1")
        page.select_option("#i_internal_trunk", "process")
        page.click("#i_connect_internal_hub")
        saved = page.evaluate("() => window.__subsea.spec")
        branch = next(route for route in saved["chain"][0]["internalRoutes"] if route["to"] == "P-out-1")
        assert branch["from"] == "@process" and branch["connectionType"] == "gas"
        assert saved["connections"] == spec["connections"]
        assert saved["chain"][0]["internalRoutes"][:3] == spec["chain"][0]["internalRoutes"]
        assert validate(saved) == []
        assert page.locator(f'[data-route="{branch["id"]}"]').evaluate("""group => {
            const branch=group.querySelector('path'), trunk=document.querySelector('[data-route="process"] path');
            const start=branch.getPointAtLength(0), joint=trunk.getPointAtLength(trunk.getTotalLength()/2);
            const end=branch.getPointAtLength(branch.getTotalLength());
            const port=document.querySelector('[data-id="base"] [data-port="P-out-1"]');
            return Math.hypot(start.x-joint.x,start.y-joint.y)<.01
                && Math.hypot(end.x-port.dataset.x,end.y-port.dataset.y)<.01;
        }""")
        assert_attached(page, ("base", "P-out-1"), ("receiver", "P-left"))
        assert page.locator("#connection-line-0").get_attribute("stroke") == "#D32F2F"
        # A process hub must not be joined to an umbilical by this convenience control.
        page.select_option("#i_internal_hub", "P-in-1")
        page.select_option("#i_internal_trunk", "umb")
        page.click("#i_connect_internal_hub")
        assert "same service lane" in page.locator("#i_equipment_error").text_content()
        assert page.evaluate("() => window.__subsea.spec") == saved
        store = CaseStore(Path(directory) / "saved.sqlite3")
        case_id, version = store.save("FURB pig branch", saved)
        loaded = store.load(case_id, version)
        loaded["chain"][0]["type"] = "riser_skid"
        html.write_text(build_html(loaded), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator(f'[data-route="{branch["id"]}"]').count() == 1
        assert_attached(page, ("base", "P-out-1"), ("receiver", "P-left"))
        with page.expect_download() as downloaded:
            page.click("#b_json")
        exported = Path(directory) / "furb.json"
        downloaded.value.save_as(exported)
        assert json.loads(exported.read_text(encoding="utf-8"))["chain"][0]["internalRoutes"] == saved["chain"][0]["internalRoutes"]
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        exported = Path(directory) / "furb.svg"
        downloaded.value.save_as(exported)
        assert f'data-route="{branch["id"]}"' in exported.read_text(encoding="utf-8")
        assert not errors, errors
        browser.close()
        check_form(directory)
    print("PASS: P outlet 2 branches into production while retaining the external pig receiver; form and lane protection verified")


def check_form(directory):
    from streamlit.testing.v1 import AppTest
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        spec = example()
        app.session_state.spec = copy.deepcopy(spec)
        app.session_state.selected_element = "base"
        app.session_state.ver += 1
        app.run()
        next(widget for widget in app.selectbox if widget.label == "Hub to connect internally").set_value("P-out-1")
        next(widget for widget in app.selectbox if widget.label == "Internal line").set_value("process")
        next(button for button in app.button if button.label == "Connect hub to internal line").click().run()
        assert not app.exception and not app.error
        saved = app.session_state.spec
        assert any(route["to"] == "P-out-1" and route["from"] == "@process"
                   for route in saved["chain"][0]["internalRoutes"])
        assert saved["connections"] == spec["connections"]
        app.run()
        assert any(route["to"] == "P-out-1" for route in app.session_state.spec["chain"][0]["internalRoutes"])
    finally:
        logging.disable(old_logging)
        if old_path is None:
            os.environ.pop("SUBSEA_CASES_PATH", None)
        else:
            os.environ["SUBSEA_CASES_PATH"] = old_path


def test_internal_hub_validation():
    base = example()["chain"][0]
    original = copy.deepcopy(base)
    routes = connect_internal_hub(base, "P-out-1", "process")
    assert base == original
    assert routes[-1] == {"id": "branch_P-out-1", "from": "@process",
                          "to": "P-out-1", "connectionType": "gas"}
    for port, trunk in (("missing", "process"), ("P-out-1", "missing"),
                        ("P-right", "process"), ("P-out-1", "umb"), ("P-out-1", "chem")):
        try:
            connect_internal_hub(base, port, trunk)
        except ValueError:
            pass
        else:
            raise AssertionError((port, trunk))
    already_routed = {**base, "internalRoutes": routes}
    try:
        connect_internal_hub(already_routed, "P-out-1", "process")
    except ValueError as error:
        assert "already internally routed" in str(error)
    else:
        raise AssertionError("Duplicate hub route accepted")


if __name__ == "__main__":
    test_internal_hub_validation()
    run()
