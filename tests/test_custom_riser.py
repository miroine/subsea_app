"""Independent FURB ports and explicit internal piping, including umbilical take-offs."""
import copy
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, drag_ports
from test_riser_base_hubs import assert_internal_hubs
from subsea.cases import CaseStore, compare_designs
from subsea.equipment import (customization_errors, removed_port_errors, furb_configuration,
                              riser_hub_counts, riser_port_ids)
from subsea.html import build_html
from subsea.spec import validate


def custom_base(type_id="riser_base"):
    return {
        "id": "base", "type": type_id, "x": 100, "y": 180,
        "riserPorts": {"P": {"inlets": 1, "outlets": 1}, "S": {"inlets": 0, "outlets": 2},
                       "U": {"inlets": 1, "outlets": 1}},
        "internalRoutes": [
            {"id": "process", "from": "P-left", "to": "P-right", "connectionType": "gas"},
            {"id": "umb", "from": "U-left", "to": "U-right", "connectionType": "umbilical_static"},
            {"id": "chem", "from": "@umb", "to": "S-right", "connectionType": "chemical"},
        ],
    }


def test_validation():
    base = custom_base()
    assert customization_errors(base) == []
    assert riser_hub_counts({"type": "riser_base"}) == {
        "P": {"inlets": 1, "outlets": 1}, "S": {"inlets": 0, "outlets": 0}, "U": {"inlets": 0, "outlets": 0},
    }
    for mode in ("additional", "replace"):
        for lane in ("P", "S", "U"):
            legacy = {"id": "base", "type": "riser_base",
                      "portConfig": {"mode": mode, "lane": lane, "inlets": 3, "outlets": 2}}
            migrated = {"id": "base", "type": "riser_base", "riserPorts": riser_hub_counts(legacy)}
            assert riser_port_ids(legacy) <= riser_port_ids(migrated)
    for field in ("from", "to", "connectionType", "id"):
        invalid = copy.deepcopy(base)
        invalid["internalRoutes"][2][field] = "missing"
        if field == "id":
            invalid["internalRoutes"][2][field] = "umb"
        assert customization_errors(invalid), field
    for value in (True, -1, 25, 1.5, None):
        invalid = copy.deepcopy(base)
        invalid["riserPorts"]["S"]["outlets"] = value
        assert customization_errors(invalid)
    invalid = copy.deepcopy(base)
    invalid["internalRoutes"][1]["from"] = "@chem"
    assert customization_errors(invalid)
    invalid = {**base, "internalRoutes": []}
    assert customization_errors(invalid) == []
    assert customization_errors({**base, "internalRoutes": None})
    bundled = {"id": "base", "type": "riser_base", "servicePorts": True, "umbilicalPorts": True,
               "bundleServiceInlet": True}
    assert customization_errors(bundled) == []
    assert "S-left" not in riser_port_ids(bundled)
    assert "S-left" in riser_port_ids(bundled, include_bundled=True)
    assert removed_port_errors({"connections": [{"from": "base", "fromPort": "S-left", "lane": "S"}]}, bundled)
    assert customization_errors({**bundled, "umbilicalPorts": False})
    assert customization_errors({**bundled, "bundleServiceInlet": "yes"})
    assert customization_errors({**bundled, "portOverrides": {"U-left": {"lane": "S"}}})
    assert customization_errors({**bundled, "portOverrides": {"U-left": {"lane": "U", "connectionType": "chemical"}}})
    assert customization_errors({**bundled, "internalRoutes": [
        {"id": "chem", "from": "S-left", "to": "S-right", "connectionType": "chemical"},
    ]}) == []
    for lane in ("P", "S", "U"):
        spec = {"connections": [{"from": "base", "fromPort": f"{lane}-right", "lane": lane}]}
        assert removed_port_errors(spec, base) == []
        reduced = copy.deepcopy(base)
        reduced["internalRoutes"] = []
        reduced["riserPorts"][lane]["outlets"] = 0
        assert removed_port_errors(spec, reduced)
    print("PASS: independent counts, internal endpoints, unique route IDs, junction references and occupied ports validated")


def assert_internal_routes(page):
    assert page.locator('[data-id="base"] .internal-route').count() == 3
    assert page.locator('[data-id="base"] .internal-route[data-route="chem"] circle').count() == 1
    assert page.locator('[data-id="base"]').get_by_text("GL", exact=True).count() == 0
    assert page.locator('[data-id="base"]').evaluate("""element => {
        const frame = element.querySelector('.riser-frame rect').getBBox();
        return [...element.querySelectorAll('.internal-route')].every(route => {
            const box = route.getBBox();
            return box.x >= frame.x && box.y >= frame.y &&
                box.x + box.width <= frame.x + frame.width &&
                box.y + box.height <= frame.y + frame.height;
        });
    }""")
    assert page.locator('[data-route="process"] path').first.get_attribute("stroke") == "#D32F2F"
    assert page.locator('[data-route="umb"] path').first.get_attribute("stroke") == "#667085"
    assert page.locator('[data-route="chem"] path').first.get_attribute("stroke") == "#E87500"
    assert_internal_hubs(page, "base")
    assert page.locator('[data-id="base"]').evaluate("""element => {
        const trunk = element.querySelector('[data-route="umb"] path');
        const branch = element.querySelector('[data-route="chem"] path');
        const start = branch.getPointAtLength(0);
        const junction = trunk.getPointAtLength(trunk.getTotalLength() / 2);
        return Math.hypot(start.x - junction.x, start.y - junction.y) < .01;
    }""")


def run():
    test_validation()
    with tempfile.TemporaryDirectory(prefix="subsea-custom-riser-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        for type_id in ("riser_base", "riser_skid"):
            spec = {"freeform": True, "host": None, "animate": False, "showLegend": False,
                    "chain": [{"id": "base", "type": type_id, "x": 100, "y": 180},
                              {"id": "template", "type": "template", "x": 650, "y": 180}]}
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.check("#i_independent_hubs")
            for lane, counts in custom_base()["riserPorts"].items():
                for side, count in counts.items():
                    page.fill(f"#i_count_{lane}_{side}", str(count))
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator('[data-id="base"] .connection-port').count() == 6
            page.check("#i_custom_piping")
            rows = page.locator(".internal-route-row")
            assert rows.count() == 2
            rows.nth(0).locator(".route-id").fill("process")
            rows.nth(0).locator(".route-service").select_option("gas")
            rows.nth(1).locator(".route-id").fill("umb")
            page.click("#i_add_route")
            row = rows.nth(2)
            for selector, value in ((".route-id", "chem"), (".route-from", "@umb"), (".route-to", "S-right")):
                row.locator(selector).fill(value)
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator("#i_equipment_error").text_content() == ""
            assert_internal_routes(page)
            assert page.evaluate("window.__subsea.getSelectedPorts().find(port => port.id === 'P-right').connectionType") == ""
            assert page.locator('[data-id="base"] [data-port="P-right"]').get_attribute("data-connection-type") == "gas"
            assert page.evaluate("window.__subsea.spec.chain[0].riserPorts") == custom_base()["riserPorts"]
            page.locator("#insp").evaluate("e => e.style.display='none'")
            page.click("#b_connect")
            for index, lane in enumerate(("P", "S", "U")):
                drag_ports(page, ("base", f"{lane}-right"), ("template", f"{lane}-left"))
                assert_attached(page, ("base", f"{lane}-right"), ("template", f"{lane}-left"), index)
                page.locator("#insp").evaluate("e => e.style.display='none'")
            saved = page.evaluate("window.__subsea.spec")
            assert validate(saved) == []
            assert page.locator("#connection-line-0").get_attribute("stroke") == "#D32F2F"
            assert page.locator("#connection-line-1").get_attribute("stroke") == "#E87500"
            assert page.locator("#connection-line-2").get_attribute("stroke") == "#667085"
            store = CaseStore(Path(directory) / "versions.sqlite3")
            case_id, version = store.save("Custom FURB", saved)
            restored = CaseStore(store.path).load(case_id, version)
            assert restored == saved and not compare_designs(saved, restored)
            html.write_text(build_html(saved), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert_internal_routes(page)
            for index, lane in enumerate(("P", "S", "U")):
                assert_attached(page, ("base", f"{lane}-right"), ("template", f"{lane}-left"), index)
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            export = Path(directory) / "furb.svg"
            downloaded.value.save_as(export)
            exported = browser.new_page()
            exported.goto(export.as_uri())
            assert_internal_routes(exported)
            exported.close()
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.locator(".internal-route-row").nth(1).locator(".remove-route").click()
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert "junction" in page.locator("#i_equipment_error").text_content()
            assert_internal_routes(page)
            while page.locator(".remove-route").count():
                page.locator(".remove-route").first.click()
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator('[data-id="base"] .internal-route').count() == 0
            assert page.evaluate("window.__subsea.spec.chain[0].internalRoutes") == []
            assert page.locator(".connection").count() == 3
            page.fill("#i_count_U_outlets", "0")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert "connected" in page.locator("#i_equipment_error").text_content()
            assert page.locator('[data-id="base"] [data-port="U-right"]').count() == 1
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", spec)
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.click("#i_furb_example")
            assert_internal_routes(page)
            assert page.evaluate("window.__subsea.spec.chain[0].riserPorts") == furb_configuration()["riserPorts"]
            for count in (1, 3, 24):
                maximum = custom_base(type_id)
                maximum["internalRoutes"] = []
                maximum["riserPorts"] = {lane: {"inlets": count, "outlets": count} for lane in ("P", "S", "U")}
                page.evaluate("spec => window.__subsea.replaceSpec(spec)", {**spec, "chain": [maximum]})
                assert page.locator('[data-id="base"] .connection-port').count() == count * 6
                assert_internal_hubs(page, "base")
                assert page.locator('[data-id="base"] .connection-port').evaluate_all("""ports =>
                    ports.every((port, index) => ports.slice(index + 1).every(other =>
                        Math.hypot(+port.dataset.x - +other.dataset.x,
                            +port.dataset.y - +other.dataset.y) >= 22))""")
            legacy_custom = {"id": "base", "type": type_id, "x": 100, "y": 180, "internalRoutes": []}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", {**spec, "chain": [legacy_custom]})
            assert page.locator('[data-id="base"] .connection-port').count() == 2
            assert page.locator('[data-id="base"] .internal-route').count() == 0
            assert_internal_hubs(page, "base")
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", {**spec, "freeform": False, "chain": [legacy_custom]})
            assert page.locator('[data-id="base"] .internal-route').count() == 0
            assert page.locator('.train > line').count() == 0
            connected_legacy = {
                **spec, "chain": [{
                    "id": "base", "type": type_id, "x": 100, "y": 180,
                    "servicePorts": True, "umbilicalPorts": True,
                    "portConfig": {"mode": "additional", "lane": "P", "inlets": 1, "outlets": 2},
                }, spec["chain"][1]],
                "connections": [
                    {"from": "base", "to": "template", "fromPort": "P-out-2", "toPort": "P-left",
                     "lane": "P", "kind": "riser", "riserStyle": "lazywave",
                     "waypoints": [{"x": 400, "y": 300}]},
                    {"from": "base", "to": "template", "fromPort": "S-left", "toPort": "S-left", "lane": "S"},
                    {"from": "base", "to": "template", "fromPort": "U-right", "toPort": "U-left", "lane": "U"},
                ],
            }
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", connected_legacy)
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.click("#i_furb_example")
            assert page.locator("#i_equipment_error").text_content() == ""
            assert_internal_routes(page)
            assert page.evaluate("window.__subsea.spec.connections") == connected_legacy["connections"]
            for index, (source, target) in enumerate((("P-out-2", "P-left"), ("S-left", "S-left"), ("U-right", "U-left"))):
                assert_attached(page, ("base", source), ("template", target), index)
            assert validate(page.evaluate("window.__subsea.spec")) == []
            applied = page.evaluate("window.__subsea.spec")
            html.write_text(build_html(applied), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert_internal_routes(page)
            assert page.evaluate("window.__subsea.spec.connections") == connected_legacy["connections"]
        test_bundle(page, html, directory)
        assert not errors, errors
        browser.close()
        test_form(directory)
    print("PASS: FURB process/umbilical through-lines, chemical take-off, independent ports, blank piping, reload/export and guards")


def test_bundle(page, html, directory):
    for type_id in ("riser_base", "riser_skid"):
        for independent in (False, True):
            base = {"id": "base", "type": type_id, "x": 100, "y": 300,
                    "servicePorts": True, "umbilicalPorts": True}
            if independent:
                base["riserPorts"] = {lane: {"inlets": 1, "outlets": 1} for lane in ("P", "S", "U")}
                base["internalRoutes"] = [
                    {"id": lane, "from": f"{lane}-left", "to": f"{lane}-right", "connectionType": service}
                    for lane, service in (("P", "gas"), ("S", "chemical"), ("U", "umbilical_static"))
                ]
            else:
                base["portConfig"] = {"mode": "additional", "lane": "P", "inlets": 1, "outlets": 1}
            spec = {"freeform": True, "host": None, "animate": False, "showLegend": False, "chain": [
                base, {"id": "host", "type": "jacket", "x": 700, "y": 100, "slots": ["J1"]},
                {"id": "template", "type": "template", "x": 650, "y": 450},
            ]}
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            process_branch = None if independent else page.locator(
                '[data-id="base"] .custom-hub[data-hub="P-in-1"] path').get_attribute("d")
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.check("#i_bundle_service")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator("#i_equipment_error").text_content() == ""
            assert page.locator('[data-id="base"] [data-port="S-left"]').count() == 0
            assert page.locator('[data-id="base"] [data-port="U-left"]').get_attribute("data-lane") == "U"
            assert "U + chemical" in page.locator('[data-id="base"] [data-port="U-left"]').get_attribute("data-label")
            assert page.locator('[data-id="base"] .connection-port').count() == (5 if independent else 7)
            if not independent:
                assert page.locator('[data-id="base"] .custom-hub[data-hub="P-in-1"] path').get_attribute("d") == process_branch
                assert page.locator('[data-id="base"]').get_by_text("GL", exact=True).count() == (1 if type_id == "riser_base" else 0)
            assert page.locator('[data-id="base"]').evaluate("""element => {
                const trunk = element.querySelector('.bundled-inlet path');
                const branch = element.querySelector('[data-route="S"] path');
                const end = trunk.getPointAtLength(trunk.getTotalLength()), start = branch.getPointAtLength(0);
                return Math.hypot(end.x - start.x, end.y - start.y) < .01;
            }""")
            page.locator("#insp").evaluate("e => e.style.display='none'")
            page.click("#b_connect")
            drag_ports(page, ("base", "S-right"), ("template", "S-left"))
            page.locator("#insp").evaluate("e => e.style.display='none'")
            drag_ports(page, ("base", "U-left"), ("host", "J-0"))
            assert_attached(page, ("base", "S-right"), ("template", "S-left"), 0)
            assert_attached(page, ("base", "U-left"), ("host", "J-0"), 1)
            saved = page.evaluate("window.__subsea.spec")
            assert validate(saved) == []
            assert saved["connections"][1]["lane"] == "U"
            assert saved["connections"][1]["kind"] == "riser"
            assert saved["connections"][1]["connectionType"] == "umbilical_static"
            saved["connections"][1].update(
                kind="riser", riserStyle="lazywave", waypoints=[{"x": 400, "y": 550}])
            store = CaseStore(Path(directory) / "bundled.sqlite3")
            case_id, version = store.save("Bundled riser", saved)
            restored = CaseStore(store.path).load(case_id, version)
            html.write_text(build_html(restored), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert_attached(page, ("base", "U-left"), ("host", "J-0"), 1)
            assert page.locator('[data-id="base"] [data-port="S-left"]').count() == 0
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            export = Path(directory) / "bundled.svg"
            downloaded.value.save_as(export)
            assert 'class="bundled-inlet"' in export.read_text(encoding="utf-8")
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.select_option("#i_port_id", "U-left")
            page.select_option("#i_port_service", "chemical")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert "bundled inlet" in page.locator("#i_port_error").text_content()
            page.uncheck("#i_bundle_service")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator('[data-id="base"] [data-port="S-left"]').count() == 1
            assert_attached(page, ("base", "U-left"), ("host", "J-0"), 1)
            assert page.evaluate("window.__subsea.spec.connections") == saved["connections"]
            occupied = {**spec, "connections": [
                {"from": "base", "to": "template", "fromPort": "S-left", "toPort": "S-left", "lane": "S"},
            ]}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", occupied)
            page.locator('[data-id="base"] .hit').click(force=True, position={"x": 60, "y": 12})
            page.check("#i_bundle_service")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert "connected" in page.locator("#i_equipment_error").text_content()
            assert_attached(page, ("base", "S-left"), ("template", "S-left"))
    print("PASS: bundled S/U inlet shares one umbilical riser/J-tube, keeps chemical outlet, saves/exports and blocks occupied S-inlets")


def test_form(directory):
    from streamlit.testing.v1 import AppTest
    previous_path = os.environ.get("SUBSEA_CASES_PATH")
    previous_logging = logging.root.manager.disable
    os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        app.session_state.spec = {"freeform": True, "host": None,
                                  "chain": [{"id": "base", "type": "riser_base", "x": 100, "y": 180}]}
        app.session_state.selected_element = "base"
        app.run()
        next(check for check in app.checkbox if check.label == "Independent process / service / umbilical hubs").check()
        app.run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["riserPorts"]["S"]["outlets"] == 0
        next(button for button in app.button if button.label == "Load FURB starting layout").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["internalRoutes"] == furb_configuration()["internalRoutes"]
        app.session_state.spec = {"freeform": True, "host": None, "chain": [{
            "id": "base", "type": "riser_base", "servicePorts": True, "umbilicalPorts": True,
            "portConfig": {"mode": "additional", "lane": "P", "inlets": 1, "outlets": 2},
        }, {"id": "template", "type": "template"}], "connections": [{
            "from": "base", "to": "template", "fromPort": "P-out-2", "toPort": "P-left", "lane": "P",
        }]}
        app.session_state.ver += 1
        app.run()
        connected = copy.deepcopy(app.session_state.spec["connections"])
        next(button for button in app.button if button.label == "Load FURB starting layout").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["riserPorts"]["P"]["outlets"] == 3
        assert app.session_state.spec["connections"] == connected
        assert validate(app.session_state.spec) == []
        app.session_state.spec = {"freeform": True, "host": None, "chain": [custom_base()]}
        app.session_state.ver += 1
        app.session_state.selected_element = "base"
        app.run()
        assert not app.exception
        next(number for number in app.number_input if number.label == "Chemical / service outlets").set_value(3)
        app.run()
        assert not app.exception and not app.error
        base = app.session_state.spec["chain"][0]
        assert base["riserPorts"]["S"]["outlets"] == 3
        assert base["internalRoutes"] == custom_base()["internalRoutes"]
        key = f"internal_routes_base_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {}, "added_rows": [], "deleted_rows": [0, 1, 2]}
        app.run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["internalRoutes"] == []
        app.session_state.spec = {"freeform": True, "host": None, "chain": [{
            "id": "base", "type": "riser_base", "servicePorts": True, "umbilicalPorts": True,
        }]}
        app.session_state.ver += 1
        app.run()
        next(check for check in app.checkbox if check.label == "Bundle S inlet into U inlet (one umbilical riser)").check()
        app.run()
        assert not app.exception and not app.error
        assert app.session_state.spec["chain"][0]["bundleServiceInlet"] is True
        assert validate(app.session_state.spec) == []
    finally:
        logging.disable(previous_logging)
        if previous_path is None:
            os.environ.pop("SUBSEA_CASES_PATH", None)
        else:
            os.environ["SUBSEA_CASES_PATH"] = previous_path
    print("PASS: below-drawing form edits independent service counts and routes; empty piping persists")


if __name__ == "__main__":
    run()
