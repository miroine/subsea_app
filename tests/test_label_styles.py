"""Per-element label appearance, placement, persistence and settings regressions."""
import copy
import json
import logging
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable
from subsea.cases import CaseStore, apply_equipment_rows, equipment_rows
from subsea.catalog import NODE_IDS, LINK_IDS, HOST_IDS
from subsea.html import build_html
from subsea.spec import validate


STYLE = dict(size=18, font="serif", weight="normal", italic=True,
             dx=24, dy=32, rotation=25, anchor="end")
SPEC = {"freeform": True, "host": None, "showLegend": False, "animate": False,
        "chain": [{"id": "p", "type": "plet", "x": 120, "y": 120},
                  {"id": "q", "type": "plet", "x": 500, "y": 120}],
        "connections": [{"from": "p", "to": "q", "fromPort": "P-right",
                         "toPort": "P-left", "lane": "P", "label": "Tieback"}]}


def caption(page, item="p"):
    return page.locator(f'[data-id="{item}"] > .element-label text').first


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-labels-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(SPEC), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        before = caption(page).evaluate("e => ({x:+e.getAttribute('x'), y:+e.getAttribute('y'), size:e.getAttribute('font-size')})")
        internals = page.locator('[data-id="p"] text').evaluate_all(
            "texts => texts.filter(e=>!e.closest('.element-label')).map(e=>e.outerHTML)")
        point = page.locator('[data-id="p"]').evaluate("""element => {
            const p=element.ownerSVGElement.createSVGPoint();p.x=35;p.y=5;
            const at=p.matrixTransform(element.getScreenCTM());return {x:at.x,y:at.y};
        }""")
        page.mouse.click(point["x"], point["y"])
        page.locator("#insp summary").filter(has_text="Label font and placement").click()
        page.fill("#i_label_size", "18")
        page.locator("#i_label_size").press("Tab")
        page.select_option("#i_label_font", "serif")
        page.select_option("#i_label_weight", "normal")
        page.check("#i_label_italic")
        for field in ("dx", "dy", "rotation"):
            page.fill(f"#i_label_{field}", str(STYLE[field]))
            page.locator(f"#i_label_{field}").press("Tab")
        page.select_option("#i_label_anchor", "end")
        text = caption(page)
        assert text.get_attribute("font-size") == "18"
        assert "Georgia" in text.get_attribute("font-family")
        assert text.get_attribute("font-weight") == "400"
        assert text.get_attribute("font-style") == "italic"
        assert text.get_attribute("text-anchor") == "end"
        assert "rotate(25 " in text.get_attribute("transform")
        assert float(text.get_attribute("x")) == before["x"] + 24
        assert float(text.get_attribute("y")) == before["y"] + 32
        # Formatting the caption must not enlarge the port letters.
        assert page.locator('[data-id="p"] text').evaluate_all(
            "texts => texts.filter(e=>!e.closest('.element-label')).map(e=>e.outerHTML)") == internals
        assert_attached(page, ("p", "P-right"), ("q", "P-left"))
        with page.expect_download() as downloaded:
            page.click("#b_json")
        exported = Path(directory) / "styled.json"
        downloaded.value.save_as(exported)
        saved = json.loads(exported.read_text(encoding="utf-8"))
        assert saved["chain"][0]["labelStyle"] == STYLE
        store = CaseStore(Path(directory) / "cases.sqlite3")
        case_id, version = store.save("Styled case", saved)
        loaded = store.load(case_id, version)
        # Inventory edits must retain the style along with all other properties.
        rows = equipment_rows(loaded)
        rows[0]["Label"] = "Custom PLET"
        loaded = apply_equipment_rows(loaded, rows)
        html.write_text(build_html(loaded), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert caption(page).text_content() == "Custom PLET"
        assert caption(page).get_attribute("font-size") == "18"
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        exported = Path(directory) / "styled.svg"
        downloaded.value.save_as(exported)
        svg = exported.read_text(encoding="utf-8")
        assert 'font-size="18"' in svg and 'font-family="Georgia' in svg and "Custom PLET" in svg
        # Every available node/link/host supports the same primary-caption style.
        all_symbols = []
        for index, type_ in enumerate(NODE_IDS + LINK_IDS + HOST_IDS):
            all_symbols.append({"id": f"e{index}", "type": type_, "label": f"Label {type_}",
                                "labelStyle": STYLE, "x": index % 8 * 300, "y": index // 8 * 350})
        catalog = {**SPEC, "chain": all_symbols, "connections": [],
                   "customSymbols": [{"id": "custom_test", "shape": "box", "abbr": "Custom"}]}
        catalog["chain"].append({"id": "custom", "type": "custom_test", "label": "Custom", "labelStyle": STYLE})
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", catalog)
        for item in catalog["chain"]:
            label = page.locator(f'[data-id="{item["id"]}"] .element-label text').filter(has_text=item["label"]).first
            assert label.count(), item["type"]
            assert label.get_attribute("font-size") == "18", item["type"]
        styled = copy.deepcopy(SPEC)
        styled["host"] = {"id": "host", "type": "jacket", "label": "Topside", "labelStyle": STYLE, "slots": []}
        styled["connections"][0]["labelStyle"] = STYLE
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", styled)
        assert caption(page, "host").get_attribute("font-size") == "18"
        assert page.locator(".connection .element-label text").get_attribute("font-size") == "18"
        # Connection inspector uses the same controls and does not change routing.
        page.locator("#insp").evaluate("element => element.style.display='none'")
        point = page.locator("#connection-line-0").evaluate("""line => {
            const at=line.getPointAtLength(line.getTotalLength()/2).matrixTransform(line.getScreenCTM());
            return {x:at.x,y:at.y};
        }""")
        page.mouse.click(point["x"], point["y"])
        page.locator("#insp summary").filter(has_text="Label font and placement").click()
        page.fill("#i_label_size", "21")
        page.locator("#i_label_size").press("Tab")
        assert page.locator(".connection .element-label text").get_attribute("font-size") == "21"
        assert_attached(page, ("p", "P-right"), ("q", "P-left"))
        themed = copy.deepcopy(saved)
        themed["themeName"] = "blueprint"
        themed.setdefault("overrides", {}).setdefault("p", {})["scale"] = 1.4
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", themed)
        assert caption(page).get_attribute("font-size") == "18"
        assert "Georgia" in caption(page).get_attribute("font-family")
        assert_attached(page, ("p", "P-right"), ("q", "P-left"))
        # Reset restores the default size and original placement.
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", saved)
        point = page.locator('[data-id="p"]').evaluate("""element => {
            const p=element.ownerSVGElement.createSVGPoint();p.x=35;p.y=5;
            const at=p.matrixTransform(element.getScreenCTM());return {x:at.x,y:at.y};
        }""")
        page.mouse.click(point["x"], point["y"])
        page.click("#i_copy")
        assert caption(page, "p_2").get_attribute("font-size") == "18"
        assert page.evaluate("() => window.__subsea.spec.chain.find(e=>e.id==='p_2').labelStyle") == STYLE
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", saved)
        page.mouse.click(point["x"], point["y"])
        page.locator("#insp summary").filter(has_text="Label font and placement").click()
        page.click("#i_label_reset")
        assert caption(page).get_attribute("font-size") == before["size"]
        assert float(caption(page).get_attribute("x")) == before["x"]
        assert float(caption(page).get_attribute("y")) == before["y"]
        assert not errors, errors
        browser.close()
        check_form(directory)
    print("PASS: per-element fonts/placement, all symbols, host/connection captions, reset, exports and case/form persistence")


def check_form(directory):
    from streamlit.testing.v1 import AppTest
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "forms.sqlite3")
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        app.session_state.spec = copy.deepcopy(SPEC)
        app.session_state.selected_element = "p"
        app.session_state.ver += 1
        app.run()
        next(widget for widget in app.number_input if widget.label == "Label font size (0 = automatic)").set_value(18.0)
        next(widget for widget in app.number_input if widget.label == "Label horizontal offset").set_value(24.0)
        next(widget for widget in app.number_input if widget.label == "Label vertical offset").set_value(32.0)
        next(widget for widget in app.selectbox if widget.label == "Label font").set_value("serif")
        app.run()
        assert not app.exception and not app.error
        item = app.session_state.spec["chain"][0]
        assert item["labelStyle"]["size"] == 18 and item["labelStyle"]["dx"] == 24
        assert "label" not in app.session_state.spec["overrides"]["p"], "Style-only edits must preserve automatic labels"
        app.run()
        assert next(widget for widget in app.selectbox if widget.label == "Label font").value == "serif"
        next(widget for widget in app.checkbox if widget.label == "Reset label font and placement to defaults").check()
        app.run()
        assert app.session_state.spec["chain"][0]["labelStyle"] == {}
        app.session_state.selected_connection = 0
        app.run()
        next(widget for widget in app.number_input if widget.label == "Label rotation (degrees)").set_value(45.0)
        app.run()
        assert app.session_state.spec["connections"][0]["labelStyle"]["rotation"] == 45
        assert not app.exception and not app.error
    finally:
        logging.disable(old_logging)
        if old_path is None:
            os.environ.pop("SUBSEA_CASES_PATH", None)
        else:
            os.environ["SUBSEA_CASES_PATH"] = old_path


def test_invalid_styles():
    assert validate(SPEC) == []
    for style in (None, [], {"size": -1}, {"size": 73}, {"size": True},
                  {"dx": float("nan")}, {"dy": float("inf")}, {"rotation": 181},
                  {"font": "invalid"}, {"anchor": "invalid"}, {"weight": "invalid"}, {"italic": "yes"}):
        spec = copy.deepcopy(SPEC)
        spec["chain"][0]["labelStyle"] = style
        assert any("label" in error for error in validate(spec)), style
        spec = copy.deepcopy(SPEC)
        spec["connections"][0]["labelStyle"] = style
        assert any("label" in error for error in validate(spec)), style


if __name__ == "__main__":
    test_invalid_styles()
    run()
