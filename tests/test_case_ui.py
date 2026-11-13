"""Live case-library regression. Use a server with an isolated SUBSEA_CASES_PATH."""
import json
import sys
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from test_connections import browser_executable


def run():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8517"
    case_name = f"UI regression {uuid4().hex[:8]}"
    copy_name = f"{case_name} copy"
    spec = {
        "title": "Version one", "freeform": True, "host": None,
        "lanes": {"S": False, "U": False}, "showLegend": False,
        "chain": [
            {"id": "template", "type": "template", "x": 350, "y": 120, "wells": 4},
            {"id": "host", "type": "jacket", "x": 900, "y": 80, "slots": ["J1", "J2"]},
            {"id": "riserbase", "type": "riser_base", "x": 100, "y": 300,
             "portConfig": {"mode": "additional", "lane": "U", "inlets": 1, "outlets": 1}},
        ],
        "connections": [
            {"from": "template", "to": "host", "fromPort": "U-right", "toPort": "J-1", "lane": "U",
             "kind": "riser", "style": "flex", "connectionType": "umbilical_dynamic", "width": 4},
            {"from": "template", "to": "riserbase", "fromPort": "U-left", "toPort": "U-in-1", "lane": "U",
             "connectionType": "umbilical_static", "waypoints": [{"x": 180, "y": 200}]},
        ],
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1700, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000)
        page.get_by_role("tab", name="Spec JSON", exact=True).click()
        page.get_by_label("Spec", exact=True).fill(json.dumps(spec))
        page.get_by_role("button", name="Apply JSON", exact=True).click()
        drawing = page.frame_locator('iframe[title="subsea.viewer.subsea_editor"]').frame_locator("#editor")
        expect(drawing.locator(".connection")).to_have_count(2, timeout=20000)
        frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        page.wait_for_timeout(1200)
        for theme in ("mono", "blueprint", "classic", "consulting"):
            theme_select = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Theme"))
            theme_select.get_by_role("combobox").click()
            names = {"mono": "Engineering – monochrome (sheet)", "blueprint": "Blueprint (sheet)",
                     "classic": "Classic colour (sheet)", "consulting": "Consulting – deep navy (slide)"}
            page.get_by_role("option", name=names[theme], exact=True).click()
            frame.wait_for_function("(theme) => window.__subsea.spec.themeName === theme", arg=theme, timeout=15000)
            expect(drawing.locator(".connection")).to_have_count(2)
            assert frame.evaluate("window.__subsea.spec.lanes.U") is False
            assert drawing.locator('[data-id="template"] [data-port="U-right"]').count() == 1
            page.wait_for_timeout(600)
        print("PASS: direct template-to-host and template-to-riser-base umbilicals survive all four live theme switches")

        inventory = page.locator('[data-testid="stExpander"]').filter(has_text="All drawn equipment settings")
        drawing.locator('[data-id="template"] .hit').click(force=True, position={"x": 3, "y": 3})
        page.get_by_label("Element label", exact=True).fill("Inventory-synchronized template")
        page.get_by_label("Element label", exact=True).press("Tab")
        frame.wait_for_function("() => window.__subsea.spec.overrides?.template?.label === 'Inventory-synchronized template'")
        expect(drawing.locator(".connection")).to_have_count(2)
        grid = inventory.locator('[data-testid="data-grid-canvas"]')
        grid.focus()
        expect(grid.get_by_test_id("glide-cell-4-0")).to_have_text("Inventory-synchronized template")
        assert {grid.get_by_test_id(f"glide-cell-0-{row}").text_content() for row in range(3)} == {"template", "host", "riserbase"}
        assert grid.get_by_test_id("glide-cell-2-1").text_content() == "Host"
        print("PASS: live inventory includes every placed symbol/host and stays synchronized with equipment edits")
        grid.evaluate("e => e.scrollIntoView({block:'center'})")
        page.wait_for_timeout(300)
        box = grid.bounding_box()
        page.mouse.dblclick(box["x"] + 500, box["y"] + 54, delay=100)
        page.locator("textarea.gdg-input, input.gdg-input").fill("Table-adjusted template")
        page.keyboard.press("Enter")
        grid.focus()
        expect(grid.get_by_test_id("glide-cell-4-0")).to_have_text("Table-adjusted template")
        page.get_by_role("button", name="Apply all equipment settings", exact=True).click()
        frame.wait_for_function("() => window.__subsea.spec.overrides?.template?.label === 'Table-adjusted template'")
        expect(drawing.locator(".connection")).to_have_count(2)
        print("PASS: real browser inventory cell editing updates SVG settings without resetting connections")

        page.get_by_role("tab", name="Saved cases", exact=True).click()
        page.get_by_label("Case name", exact=True).fill(case_name)
        page.get_by_label("Version note", exact=True).fill("Base version")
        page.get_by_role("button", name="Save case version", exact=True).click()
        expect(page.get_by_text(f"Saved {case_name}: version 1.", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Title (action title)", exact=True).fill("Version two")
        page.get_by_label("Title (action title)", exact=True).press("Tab")
        frame.wait_for_function("() => window.__subsea.spec.title === 'Version two'")
        page.get_by_label("Version note", exact=True).fill("Updated version")
        page.get_by_role("button", name="Save case version", exact=True).click()
        expect(page.get_by_text(f"Saved {case_name}: version 2.", exact=True)).to_be_visible(timeout=15000)
        print("PASS: saving a new case and immutable next version from the live drawing")

        saved = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Saved case"))
        saved.get_by_role("combobox").click()
        page.get_by_role("option", name=case_name, exact=True).click()
        page.wait_for_timeout(800)
        version = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Saved version"))
        version.get_by_role("combobox").click()
        page.get_by_role("option").filter(has_text="v1 ·").click()
        page.get_by_role("button", name="Load saved version", exact=True).click()
        expect(page.get_by_label("Title (action title)", exact=True)).to_have_value("Version one", timeout=15000)
        expect(drawing.locator(".connection")).to_have_count(2, timeout=15000)
        page.get_by_label("Duplicate case name", exact=True).fill(copy_name)
        page.get_by_role("button", name="Duplicate saved case", exact=True).click()
        expect(page.get_by_text(f"Created {copy_name} as an independent case (v1).", exact=True)).to_be_visible(timeout=15000)
        page.get_by_role("tab", name="Compare designs", exact=True).click()
        right = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Right design"))
        right.get_by_role("combobox").click()
        page.get_by_role("option").filter(has_text=f"{case_name} · v2").click()
        page.get_by_role("button", name="Compare designs", exact=True).click()
        expect(page.get_by_text("differences (equipment matched by ID;", exact=False)).to_be_visible(timeout=15000)
        assert page.locator('[data-testid="stDownloadButton"]').filter(has_text="Download comparison CSV").count() == 1
        previews = [f for f in page.frames if f.evaluate("() => !!window.__subsea")]
        assert len(previews) == 3
        titles = [f.evaluate("window.__subsea.spec.title") for f in previews]
        assert "Version one" in titles and "Version two" in titles
        print("PASS: loading restores saved geometry and settings; independent duplication; side-by-side previews and differences")
        page.get_by_role("tab", name="Saved cases", exact=True).click()
        page.get_by_role("button", name="Delete saved data", exact=True).click()
        expect(page.get_by_text("Confirm deletion before deleting saved data.", exact=True)).to_be_visible()
        page.get_by_text("Confirm permanent deletion", exact=True).click()
        page.get_by_role("button", name="Delete saved data", exact=True).click()
        expect(page.get_by_text("Saved data deleted. The working drawing was not changed.", exact=True)).to_be_visible(timeout=15000)
        assert not errors, errors
        assert page.locator('[data-testid="stException"]').count() == 0
        browser.close()
        print("PASS: explicit delete confirmation and version deletion without changing the working drawing")


if __name__ == "__main__":
    run()
