"""Presentation polish must never move symbols, ports or routed connections."""
import copy
import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable
from subsea.cases import CaseStore
from subsea.html import build_html
from subsea.presets import PRESETS, get_preset


SPEC = {
    "freeform": True, "host": None, "animate": False, "showLegend": False,
    "themeName": "classic", "showGrid": True,
    "chain": [
        {"id": "p", "type": "plet", "x": 180, "y": 120, "label": "Inlet PLET"},
        {"id": "q", "type": "plet", "x": 560, "y": 200, "tag": "PLET-101",
         "label": "Export PLET", "labelStyle": {"size": 20, "font": "serif", "dx": 12,
                                               "dy": -15, "rotation": 10, "weight": "normal"}},
        {"id": "base", "type": "riser_base", "x": 800, "y": 120, "tag": ""},
        {"id": "host", "type": "jacket", "x": 0, "y": -80, "label": "Platform A"},
        {"id": "sensor", "type": "pt_sensor", "x": 420, "y": 120},
    ],
    "overrides": {"q": {"scale": .6, "dx": 30, "dy": 15}},
    "connections": [{"from": "p", "fromPort": "P-right", "to": "q", "toPort": "P-left",
                     "lane": "P", "connectionType": "gas", "label": "Gas export",
                     "waypoints": [{"x": 340, "y": 120}, {"x": 340, "y": 210}]}],
}


def geometry(page):
    return page.evaluate("""() => {
        const svg=document.querySelector('#svg');
        const points=e => {
            const matrix=svg.getScreenCTM().inverse().multiply(e.getScreenCTM());
            return [matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f].map(v=>Math.round(v*1e6)/1e6);
        };
        return {
            view:svg.getAttribute('viewBox'),
            elements:[...svg.querySelectorAll('#content .el')].map(e=>[e.dataset.id,points(e)]),
            ports:[...svg.querySelectorAll('.connection-port')].map(e=>[e.dataset.port,e.dataset.x,e.dataset.y,points(e)]),
            routes:[...svg.querySelectorAll('#connections path:not(.connection-hit)')].map(e=>[e.id,e.getAttribute('d'),e.getAttribute('stroke'),e.getAttribute('stroke-width')]),
            hardware:[...svg.querySelectorAll('#content .el path,#content .el rect:not(.hit),#content .el line')]
                .filter(e=>!e.closest('.element-label,.equipment-tag,.connection-port'))
                .map(e=>e.outerHTML)
        };
    }""")


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-improve-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1700, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        html.write_text(build_html(SPEC), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        initial = page.evaluate("() => window.__subsea.spec")
        before = geometry(page)
        custom = page.locator('[data-id="q"] .element-label > text').first.evaluate("e=>e.outerHTML")
        assert page.locator("#b_undo_improve").is_disabled()
        page.click("#b_improve")
        improved = page.evaluate("() => window.__subsea.spec")
        assert improved["professionalAppearance"] is True
        assert improved["chain"][0]["tag"] == "PLET-102"
        assert improved["chain"][1]["tag"] == "PLET-101"
        assert improved["chain"][2]["tag"] == ""
        assert improved["chain"][3]["tag"] == "HOST-101"
        assert improved["chain"][4]["tag"] == "PT-101"
        allowed = copy.deepcopy(improved)
        allowed.pop("professionalAppearance")
        for before_item, after_item in zip(initial["chain"], allowed["chain"]):
            if "tag" not in before_item:
                after_item.pop("tag", None)
        assert allowed == initial, "Improve changed data other than missing tags and appearance"
        assert geometry(page) == before, "Presentation polish moved geometry or changed routes/colours"
        assert page.locator('[data-id="q"] .element-label > text').first.evaluate("e=>e.outerHTML") == custom
        assert page.locator("#hatch").get_attribute("width") == "6"
        assert page.locator("#hatch line").get_attribute("stroke-width") == "0.65"
        assert page.locator('[data-id="p"] .element-label > text').first.get_attribute("font-size") == "10.5"
        assert page.locator('[data-id="p"] .element-label > text').first.get_attribute("fill") == "#1F2328"
        assert page.locator('[data-id="p"] .equipment-tag').text_content() == "PLET-102"
        assert page.locator('[data-id="host"] .equipment-tag').text_content() == "HOST-101"
        assert page.locator('[data-id="sensor"] text').filter(has_text="101").count() >= 1
        assert_attached(page, ("p", "P-right"), ("q", "P-left"))
        assert not page.locator("#b_undo_improve").is_disabled()
        page.click("#b_improve")
        assert page.evaluate("() => window.__subsea.spec") == improved
        page.click("#b_undo_improve")
        assert page.evaluate("() => window.__subsea.spec") == initial
        assert geometry(page) == before
        assert page.locator("#hatch").get_attribute("width") == "4"
        page.click("#b_improve")
        with page.expect_download() as downloaded:
            page.click("#b_json")
        exported = Path(directory) / "polished.json"
        downloaded.value.save_as(exported)
        saved = json.loads(exported.read_text(encoding="utf-8"))
        assert saved == improved
        store = CaseStore(Path(directory) / "cases.sqlite3")
        case_id, version = store.save("Polished layout", saved)
        saved = store.load(case_id, version)
        html.write_text(build_html(saved), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator("#hatch line").get_attribute("stroke-width") == "0.65"
        assert page.locator('[data-id="p"] .equipment-tag').text_content() == "PLET-102"
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        exported = Path(directory) / "polished.svg"
        downloaded.value.save_as(exported)
        svg = exported.read_text(encoding="utf-8")
        assert "PLET-102" in svg and 'stroke-width="0.65"' in svg
        # Undo must never overwrite edits made after polishing.
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", initial)
        page.click("#b_improve")
        changed = copy.deepcopy(improved)
        changed["chain"][0]["x"] += 50
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", changed)
        page.wait_for_function("() => document.querySelector('#b_undo_improve').disabled")
        assert page.evaluate("() => window.__subsea.spec.chain[0].x") == changed["chain"][0]["x"]
        # Tag suppression is intentional; honour it and do not invent tags.
        suppressed = copy.deepcopy(initial)
        suppressed["autoTag"] = False
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", suppressed)
        page.click("#b_improve")
        result = page.evaluate("() => window.__subsea.spec")
        assert all(item.get("tag") == original.get("tag") for item, original in zip(result["chain"], initial["chain"]))
        # Small symbols retain legible automatic captions; manual sizes are untouched.
        small = copy.deepcopy(initial)
        small["overrides"]["p"] = {"scale": .5}
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", small)
        before = geometry(page)
        page.click("#b_improve")
        assert geometry(page) == before
        assert page.locator('[data-id="p"] .element-label > text').first.get_attribute("font-size") == "21"
        assert page.locator('[data-id="p"] .equipment-tag text').get_attribute("font-size") == "15"
        # Newly added symbols can be polished without renumbering existing ones.
        expanded = page.evaluate("() => window.__subsea.spec")
        expanded["chain"].append({"id": "new", "type": "plet", "x": 400, "y": 400})
        page.evaluate("spec => window.__subsea.replaceSpec(spec)", expanded)
        page.click("#b_improve")
        result = page.evaluate("() => window.__subsea.spec")
        assert result["chain"][-1]["tag"] == "PLET-103"
        assert result["chain"][0]["tag"] == "PLET-102"
        page.click("#b_undo_improve")
        assert page.evaluate("() => window.__subsea.spec") == expanded
        # Every preset, including mirrored/branched trains, preserves exact geometry.
        for name in PRESETS:
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", get_preset(name))
            before = geometry(page)
            page.click("#b_improve")
            assert geometry(page) == before, name
        assert not errors, errors
        browser.close()
    print("PASS: professional typography, subtle textures, unique missing tags, exact geometry/route preservation, undo, all presets and persistent exports/cases")


if __name__ == "__main__":
    run()
