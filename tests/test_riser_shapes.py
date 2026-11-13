"""Integrated PLET ports and explicitly classified risers with persistent curved bends."""
import copy
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, screen_port
from test_drawing_tools import drag, line_point
from subsea.connections import RISER_STYLES
from subsea.html import build_html
from subsea.spec import validate
from subsea.presets import get_preset


def assert_topside_psv(page, host_id, slot, at_start, preset=False):
    marker = page.locator("#riser-annotations .riser-psv")
    assert marker.count() == 1
    assert marker.evaluate("""(marker, options) => {
        const host = document.querySelector(`[data-id="${CSS.escape(options.host)}"]`);
        const guide = host.querySelector(`.j-tube-guide[data-tube="${options.slot}"] .j-tube-bore`);
        const route = guide || document.querySelector(options.preset
            ? '[data-riser-host] > path:not(.legacy-riser-hit)' : '#connection-line-0');
        const point = route.getPointAtLength(guide || options.atStart ? 0 : route.getTotalLength());
        const expected = new DOMPoint(point.x, point.y).matrixTransform(route.getScreenCTM());
        const actual = new DOMPoint(0, 0).matrixTransform(marker.getScreenCTM());
        return Math.hypot(expected.x - actual.x, expected.y - actual.y) < .1;
    }""", {"host": host_id, "slot": slot, "atStart": at_start, "preset": preset})
    assert marker.locator(".riser-psv-symbol").evaluate("""symbol => {
        const box = symbol.querySelector('path').getBBox();
        const matrix = symbol.transform.baseVal.consolidate().matrix;
        const scale = Math.hypot(matrix.a, matrix.b);
        return box.width * scale <= 10 && box.height * scale <= 18;
    }""")
    visibility = marker.locator(".riser-psv-symbol > path").evaluate("""path => {
        const inspector = document.querySelector('#insp');
        const previousDisplay = inspector?.style.display;
        const previousEvents = path.style.pointerEvents;
        try {
            if (inspector) inspector.style.display = 'none';
            path.style.pointerEvents = 'all';
            const point = new DOMPoint(0, -15).matrixTransform(path.getScreenCTM());
            const hit = document.elementFromPoint(point.x, point.y);
            return {visible: hit === path, x: point.x, y: point.y,
                covering: hit?.outerHTML.slice(0, 250)};
        } finally {
            path.style.pointerEvents = previousEvents;
            if (inspector) inspector.style.display = previousDisplay;
        }
    }""")
    assert visibility["visible"], f"Platform geometry must not cover the PSV: {visibility}"


def run():
    spec = {
        "freeform": True, "host": None, "lanes": {"S": False, "U": False},
        "showLegend": False, "animate": False,
        "chain": [
            {"id": "p", "type": "plet", "x": 120, "y": 280},
            {"id": "t", "type": "template", "x": 620, "y": 400},
            {"id": "h", "type": "jacket", "x": 900, "y": 60, "slots": ["J1", "J2"]},
        ],
        "connections": [{"from": "p", "to": "t", "fromPort": "P-right", "toPort": "P-left", "lane": "P"}],
    }
    with tempfile.TemporaryDirectory(prefix="subsea-riser-shapes-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        bounds = page.locator('[data-id="p"] .plet-frame rect').evaluate(
            "e => ({top:+e.getAttribute('y'), bottom:+e.getAttribute('y') + +e.getAttribute('height')})")
        for lane in ("P", "S", "U"):
            for side in ("left", "right"):
                y = float(page.locator(f'[data-id="p"] [data-port="{lane}-{side}"]').get_attribute("data-y"))
                assert bounds["top"] < y < bounds["bottom"], (lane, y, bounds)
        assert page.locator('[data-id="p"] .lane-hub').count() == 0
        print("PASS: PLET frame encloses process, service and umbilical ports; no detached S/U stubs")

        point = line_point(page)
        page.mouse.click(point["x"], point["y"])
        original_route = page.locator("#connection-line-0").get_attribute("d")
        for kind in ("jumper", "spool"):
            page.select_option("#i_connection_kind", kind)
            assert page.evaluate("window.__subsea.spec.connections[0].kind") == kind
            assert page.locator("#insp b").text_content() == kind.title()
            assert page.locator("#connection-line-0").get_attribute("d") == original_route
            tagged = page.evaluate("window.__subsea.spec")
            assert validate(tagged) == []
            html.write_text(build_html(tagged), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert page.evaluate("window.__subsea.spec.connections[0].kind") == kind
            point = line_point(page)
            page.mouse.click(point["x"], point["y"])
            assert page.locator("#i_connection_kind").input_value() == kind
        print("PASS: Jumper/Spool tags survive JSON reload and preserve routes and port attachments")
        page.locator("#i_connection_kind").select_option("riser")
        page.check("#i_psv")
        page.fill("#i_psv_tag", "PSV-101")
        page.locator("#i_psv_tag").press("Tab")
        page.fill("#i_psv_position", "25")
        page.locator("#i_psv_position").press("Tab")
        assert page.locator(".riser-psv").count() == 1
        assert "PSV-101" in page.locator(".riser-psv").text_content()
        assert page.locator(".riser-psv").evaluate("""marker => {
            const route = document.querySelector('#connection-line-0');
            const point = route.getPointAtLength(route.getTotalLength() * .25);
            const position = marker.transform.baseVal.getItem(0).matrix;
            return Math.abs(position.e-point.x)<.01 && Math.abs(position.f-point.y)<.01;
        }""")
        shapes = {}
        for shape in RISER_STYLES:
            page.select_option("#i_riser_style", shape)
            assert page.evaluate("window.__subsea.spec.connections[0].kind") == "riser"
            assert page.evaluate("window.__subsea.spec.connections[0].style") == shape
            shapes[shape] = page.locator("#connection-line-0").get_attribute("d")
            assert "C" in shapes[shape] or "Q" in shapes[shape]
            assert_attached(page, ("p", "P-right"), ("t", "P-left"))
            assert page.locator(".riser-psv").count() == 1
        assert len(set(shapes.values())) == len(RISER_STYLES)
        print("PASS: arbitrary equipment connection can be a riser; rigid, catenary, lazy-wave and S-shape differ")
        page.click("#i_add_bend")
        points = page.evaluate("window.__subsea.spec.connections[0].waypoints")
        for shape in RISER_STYLES:
            page.select_option("#i_riser_style", shape)
            d = page.locator("#connection-line-0").get_attribute("d")
            assert ("Q" if shape == "rigid" else "C") in d
            assert page.evaluate("window.__subsea.spec.connections[0].waypoints") == points
        page.select_option("#i_connection_type", "gas")
        page.fill("#i_connection_width", "8")
        page.locator("#i_connection_width").press("Tab")
        page.fill("#i_connection_label", "S-shaped gas riser")
        page.locator("#i_connection_label").press("Tab")
        assert page.locator("#connection-line-0").get_attribute("d") == d
        assert page.locator(".riser-psv").count() == 1
        for theme in ("mono", "blueprint", "classic", "consulting"):
            page.evaluate("(theme) => {const spec=structuredClone(window.__subsea.spec);spec.themeName=theme;window.__subsea.replaceSpec(spec);}", theme)
            assert page.locator("#connection-line-0").get_attribute("d") == d
            assert_attached(page, ("p", "P-right"), ("t", "P-left"))
        saved = page.evaluate("window.__subsea.spec")
        html.write_text(build_html(saved), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator("#connection-line-0").get_attribute("d") == d
        assert validate(saved) == []
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg = Path(directory) / "riser.svg"
        downloaded.value.save_as(svg)
        assert d in svg.read_text(encoding="utf-8")
        assert "PSV-101" in svg.read_text(encoding="utf-8")
        print("PASS: manual riser bends stay curved and survive service/width/label/theme edits and JSON/SVG round-trips")

        # Both drag directions and moved/resized hosts keep the selected shape and attached ends.
        for reverse in (False, True):
            candidate = copy.deepcopy(spec)
            connection = {"from": "p", "to": "h", "fromPort": "U-right", "toPort": "J-1", "lane": "U", "kind": "riser",
                          "psv": True, "psvTag": "PSV-TOPSIDE", "psvPosition": 85}
            if reverse:
                connection["from"], connection["to"] = connection["to"], connection["from"]
                connection["fromPort"], connection["toPort"] = connection["toPort"], connection["fromPort"]
            for show_tubes in (False, True):
                candidate["chain"][2].update(showJTubes=show_tubes, jTubeSide="right" if reverse else "left")
                for shape in RISER_STYLES:
                    connection["style"] = shape
                    candidate["connections"] = [copy.deepcopy(connection)]
                    candidate["overrides"] = {"h": {"scale": 1.3, "dx": 40, "dy": 10}}
                    page.evaluate("(spec) => window.__subsea.replaceSpec(spec)", candidate)
                    a = ("h", "J-1") if reverse else ("p", "U-right")
                    b = ("p", "U-right") if reverse else ("h", "J-1")
                    assert_attached(page, a, b)
                    assert_topside_psv(page, "h", 1, reverse)
                    assert "NaN" not in page.locator("#connection-line-0").get_attribute("d")
            candidate["chain"][2]["type"] = "platform"
            for show_tubes in (False, True):
                candidate["chain"][2]["showJTubes"] = show_tubes
                page.evaluate("(spec) => window.__subsea.replaceSpec(spec)", candidate)
                assert_topside_psv(page, "h", 1, reverse)
            page.locator("#b_fit").click()
            point = line_point(page)
            page.mouse.click(point["x"], point["y"])
            assert page.locator("#i_psv_position").is_disabled()
        print("PASS: compact PSV stays at the topside for every shape, direction and J-tube display despite old positions")
        candidate = copy.deepcopy(spec)
        candidate["connections"] = [{
            "from": "p", "to": "h", "fromPort": "U-right", "toPort": "J-1", "lane": "U",
            "kind": "riser", "style": "s_shape", "waypoints": [{"x": 400, "y": 260}, {"x": 600, "y": 250}],
        }]
        page.evaluate("(spec) => window.__subsea.replaceSpec(spec)", candidate)
        point = line_point(page)
        page.mouse.click(point["x"], point["y"])
        page.locator("#insp").evaluate("e => e.style.display='none'")
        end = page.locator('.route-end[data-end="to"]').bounding_box()
        destination = screen_port(page, "t", "U-right")
        start = {"x": end["x"] + end["width"] / 2, "y": end["y"] + end["height"] / 2}
        drag(page, start, destination["x"] - start["x"], destination["y"] - start["y"])
        reconnected = page.evaluate("window.__subsea.spec.connections[0]")
        assert reconnected["to"] == "t" and reconnected["toPort"] == "U-right"
        assert reconnected["kind"] == "riser" and reconnected["style"] == "s_shape"
        assert reconnected["waypoints"] == candidate["connections"][0]["waypoints"]
        assert_attached(page, ("p", "U-right"), ("t", "U-right"))
        print("PASS: reconnecting a riser away from a host keeps classification, selected shape and manual bends")
        preset = get_preset("Two-template tieback to platform")
        preset["host"]["showJTubes"] = True
        preset["host"]["risers"][0].update(psv=True, psvTag="PSV-PRESET", psvPosition=65)
        page.evaluate("(spec) => window.__subsea.replaceSpec(spec)", preset)
        assert page.locator("#riser-annotations .riser-psv").count() == 1
        host_id = page.locator("[data-riser-host]").first.get_attribute("data-riser-host")
        assert_topside_psv(page, host_id, 0, True, preset=True)
        page.click("#b_fit")
        page.locator("#insp").evaluate("element => element.style.display='none'")
        location = page.locator("[data-riser-host] .legacy-riser-hit").first.evaluate("""route => {
            for (const fraction of [.9, .8, .7, .6, .5]) {
                const point = route.getPointAtLength(route.getTotalLength() * fraction);
                const svgPoint = route.ownerSVGElement.createSVGPoint();
                svgPoint.x=point.x; svgPoint.y=point.y;
                const screen=svgPoint.matrixTransform(route.getScreenCTM());
                if (document.elementFromPoint(screen.x, screen.y)?.closest('[data-riser-host]'))
                    return {x:screen.x,y:screen.y};
            }
            throw new Error('No exposed preset riser segment');
        }""")
        page.mouse.click(location["x"], location["y"])
        converted = page.evaluate("window.__subsea.spec.connections.find(c => c.psvTag === 'PSV-PRESET')")
        assert converted and converted["psv"] is True and converted["psvPosition"] == 65
        assert page.locator("#riser-annotations .riser-psv").count() == 1
        assert_topside_psv(page, host_id, 0, True)
        converted_spec = page.evaluate("window.__subsea.spec")
        html.write_text(build_html(converted_spec), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_topside_psv(page, host_id, 0, True)
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg = Path(directory) / "topside-psv.svg"
        downloaded.value.save_as(svg)
        exported = browser.new_page()
        exported.goto(svg.as_uri())
        assert_topside_psv(exported, host_id, 0, True)
        exported.close()
        print("PASS: compact preset PSV keeps its topside anchor through conversion, reload and SVG export")
        assert not errors, errors
        browser.close()
        invalid = copy.deepcopy(saved)
        invalid["connections"][0]["style"] = "bad-shape"
        assert any("riser shape" in error for error in validate(invalid))
        print("PASS: every shape attaches in either direction to moved/resized J-tubes; invalid riser shapes rejected")
    test_settings_form(spec)


def test_settings_form(spec):
    from streamlit.testing.v1 import AppTest
    with tempfile.TemporaryDirectory(prefix="subsea-riser-form-") as directory:
        previous_path = os.environ.get("SUBSEA_CASES_PATH")
        previous_logging = logging.root.manager.disable
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state.spec = copy.deepcopy(spec)
            app.session_state.spec["connections"][0]["waypoints"] = [{"x": 400, "y": 300}, {"x": 450, "y": 450}]
            app.session_state.selected_connection = 0
            app.run()
            next(select for select in app.selectbox if select.label == "Physical connection").set_value("riser")
            next(select for select in app.selectbox if select.label == "Riser shape").set_value("s_shape")
            next(widget for widget in app.checkbox if widget.label == "Add PSV to riser").set_value(True)
            next(widget for widget in app.text_input if widget.label == "PSV tag").set_value("PSV-FORM")
            next(widget for widget in app.number_input if widget.label == "PSV position (%)").set_value(80)
            app.run()
            assert not app.exception, [error.message for error in app.exception]
            connection = app.session_state.spec["connections"][0]
            assert connection["kind"] == "riser" and connection["style"] == "s_shape"
            assert connection["psv"] is True and connection["psvPosition"] == 80 and connection["psvTag"] == "PSV-FORM"
            assert connection["waypoints"] == [{"x": 400, "y": 300}, {"x": 450, "y": 450}]
            next(input_ for input_ in app.text_input if input_.label == "Connection label").set_value("S riser")
            app.run()
            assert app.session_state.spec["connections"][0]["style"] == "s_shape"
            assert app.session_state.spec["connections"][0]["waypoints"] == connection["waypoints"]
            for kind in ("jumper", "spool"):
                next(widget for widget in app.checkbox if widget.label == "Add PSV to riser").set_value(False)
                next(select for select in app.selectbox if select.label == "Physical connection").set_value(kind)
                app.run()
                assert not app.exception
                assert app.session_state.spec["connections"][0]["kind"] == kind
                assert app.session_state.spec["connections"][0]["waypoints"] == connection["waypoints"]
                assert validate(app.session_state.spec) == []
            next(widget for widget in app.checkbox if widget.label == "Add PSV to riser").set_value(True)
            app.run()
            assert app.session_state.spec["connections"][0]["kind"] == "riser"
            assert next(select for select in app.selectbox if select.label == "Physical connection").value == "riser"
            app.session_state.spec["connections"][0].update(
                to="h", toPort="J-1", fromPort="U-right", lane="U")
            app.run()
            assert next(widget for widget in app.number_input if widget.label == "PSV position (%)").disabled
        finally:
            logging.disable(previous_logging)
            if previous_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = previous_path
    print("PASS: settings below the drawing classify any connection as a shaped riser and retain manual bends")


if __name__ == "__main__":
    run()
