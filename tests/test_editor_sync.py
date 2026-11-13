"""Live Streamlit regression: python tests\\test_editor_sync.py [URL]."""
import sys

from playwright.sync_api import expect, sync_playwright

from test_connections import browser_executable


def run():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8517"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_selector('iframe[title="subsea.viewer.subsea_editor"]', timeout=30000)
        for section in ("Drawing appearance", "Drawing title & notes", "View & flow animation"):
            page.get_by_test_id("stSidebar").get_by_text(section, exact=True).click()
        outer = page.frame_locator('iframe[title="subsea.viewer.subsea_editor"]')
        drawing = outer.frame_locator("#editor")
        drawing.locator("#b_palette").wait_for()
        frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        frame.evaluate("window.syncTestToken = 'preserve-this-editor'")
        drawing.locator("#b_palette").click()
        drawing.locator('.palette-item[data-type="plet"]').click()
        item_id = frame.evaluate("window.__subsea.sel")
        page.get_by_label("Element label", exact=True).wait_for(timeout=15000)
        assert page.get_by_text(item_id, exact=False).count() > 0
        drawing.locator("#palette-close").click()
        drawing.locator("#insp").evaluate("element => element.style.display='none'")
        hit = drawing.locator(f'.el[data-id="{item_id}"] .hit')
        hit.scroll_into_view_if_needed()
        start = hit.bounding_box()
        page.mouse.move(start["x"] + 4, start["y"] + 4)
        page.mouse.down()
        page.mouse.move(start["x"] + 25, start["y"] + 30, steps=8)
        page.mouse.up()
        page.wait_for_timeout(1200)
        expected = frame.evaluate("(id) => window.__subsea.spec.overrides[id]", item_id)
        assert expected["dx"] != 0 or expected["dy"] != 0
        view_box = drawing.locator("#svg").get_attribute("viewBox")
        page.get_by_label("Element label", exact=True).fill("Adjusted PLET")
        page.get_by_label("Element size (%)", exact=True).fill("140")
        page.get_by_label("Element size (%)", exact=True).press("Tab")
        frame.wait_for_function(
            "(id) => window.__subsea.spec.overrides[id].label === 'Adjusted PLET' && window.__subsea.spec.overrides[id].scale === 1.4",
            arg=item_id, timeout=15000,
        )
        current = frame.evaluate("(id) => window.__subsea.spec.overrides[id]", item_id)
        assert current["dx"] == expected["dx"] and current["dy"] == expected["dy"]
        assert frame.evaluate("window.syncTestToken") == "preserve-this-editor"
        assert drawing.locator("#svg").get_attribute("viewBox") == view_box
        print("PASS: drawing selection populates settings below; applying settings preserves positions and viewport")
        page.get_by_label("Title (action title)", exact=True).fill("Synchronized drawing")
        page.get_by_label("Title (action title)", exact=True).press("Tab")
        frame.wait_for_function("() => window.__subsea.spec.title === 'Synchronized drawing'", timeout=15000)
        assert frame.evaluate("(id) => window.__subsea.spec.overrides[id].label", item_id) == "Adjusted PLET"
        assert frame.evaluate("window.syncTestToken") == "preserve-this-editor"
        page.get_by_role("tab", name="Host & risers", exact=True).click()
        slots = page.get_by_label("Slot / riser labels (comma separated)", exact=True)
        slots.fill("Tube A, Tube B, Tube C")
        slots.press("Tab")
        frame.wait_for_function("() => window.__subsea.spec.host.slots[0] === 'Tube A'", timeout=15000)
        assert frame.evaluate("(id) => window.__subsea.spec.overrides[id].scale", item_id) == 1.4
        print("PASS: sidebar and existing settings tabs update drawing without losing viewer edits")
        page.get_by_role("tab", name="Network", exact=True).click()
        drawing.locator(".host.el .hit").click(position={"x": 2, "y": 2}, force=True)
        page.get_by_role("tab", name="Selected item", exact=True).click()
        page.get_by_label("J-tube labels", exact=True).wait_for(timeout=15000)
        page.get_by_label("J-tube labels", exact=True).fill("J1, J2, J3, J4")
        page.get_by_label("J-tube labels", exact=True).press("Tab")
        frame.wait_for_function("() => window.__subsea.spec.host.slots.length === 4", timeout=15000)
        assert frame.evaluate("(id) => window.__subsea.spec.overrides[id].label", item_id) == "Adjusted PLET"
        assert frame.evaluate("window.syncTestToken") == "preserve-this-editor"
        print("PASS: selecting existing host exposes editable J-tube settings below")
        previous_grid = frame.evaluate("!!window.__subsea.spec.showGrid")
        drawing.locator("#b_grid").click()
        page.wait_for_timeout(800)
        assert page.get_by_label("Grid", exact=True).is_checked() != previous_grid
        drawing.locator("#b_spd").evaluate(
            "input => { input.value = '0.75'; input.dispatchEvent(new Event('input', {bubbles:true})); }"
        )
        page.wait_for_timeout(800)
        assert frame.evaluate("window.__subsea.spec.animSpeed") == 0.75
        assert page.locator('[data-testid="stException"]').count() == 0
        print("PASS: viewer grid and fractional animation speed synchronize with sidebar")
        drawing.locator("#b_fit").click()
        drawing.locator("#insp").evaluate("element => element.style.display='none'")
        drawing.locator("#b_connect").click()
        start = drawing.locator(f'[data-id="{item_id}"] [data-port="P-right"] circle:not(.port-hit)').bounding_box()
        end = drawing.locator('.host.el [data-port="J-0"] circle:not(.port-hit)').bounding_box()
        page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
        page.mouse.down()
        page.mouse.move(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2, steps=12)
        page.mouse.up()
        assert frame.evaluate("window.__subsea.spec.connections.length") == 1, drawing.locator("#connect-status").text_content()
        page.wait_for_timeout(1200)
        connection_select = page.locator('[data-testid="stSelectbox"]').filter(
            has=page.locator("label", has_text="Connection type")
        )
        connection_select.wait_for(timeout=15000)
        connection_select.get_by_role("combobox").click()
        page.get_by_role("option", name="Gas", exact=True).click()
        page.get_by_label("Connection label", exact=True).fill("Gas tieback")
        page.get_by_text("Use default connection thickness", exact=True).click()
        page.get_by_label("Connection thickness", exact=True).fill("6")
        page.get_by_label("Connection thickness", exact=True).press("Tab")
        frame.wait_for_function(
            "() => window.__subsea.spec.connections[0].connectionType === 'gas' && window.__subsea.spec.connections[0].label === 'Gas tieback'",
            timeout=15000,
        )
        drawing.locator("#i_connection_type").select_option("umbilical_dynamic")
        expect(connection_select).to_contain_text("Dynamic umbilical", timeout=15000)
        assert drawing.locator("#connection-line-0").get_attribute("stroke-width") == "6"
        drawing.locator("#i_add_bend").click()
        frame.wait_for_function("() => window.__subsea.spec.connections[0].waypoints.length === 1")
        page.wait_for_timeout(800)
        drawing.locator("#i_connection_width").fill("8")
        drawing.locator("#i_connection_width").press("Tab")
        expect(page.get_by_label("Connection thickness", exact=True)).to_have_value("8.00", timeout=15000)
        assert frame.evaluate("window.syncTestToken") == "preserve-this-editor"
        assert frame.evaluate("(id) => window.__subsea.spec.overrides[id].label", item_id) == "Adjusted PLET"
        print("PASS: connection type and label synchronize both ways without resetting drawing")
        drawing.locator("#b_connect").click()
        drawing.locator('[data-id="t1"] .hit').click(force=True, position={"x": 2, "y": 2})
        page.get_by_text("Include HIPPS", exact=True).wait_for(timeout=15000)
        assert page.get_by_label("Include HIPPS", exact=True).is_checked()
        page.get_by_text("Include HIPPS", exact=True).click()
        page.get_by_label("Wells", exact=True).fill("6")
        tree_select = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Xmas tree type"))
        tree_select.get_by_role("combobox").click()
        page.get_by_role("option", name="Horizontal Xmas tree (HXT)", exact=True).click()
        page.get_by_text("Customize inlet/outlet hubs", exact=True).click()
        page.get_by_label("Inlet connections", exact=True).fill("2")
        page.get_by_label("Outlet connections", exact=True).fill("3")
        page.get_by_label("Element Design pressure (bar)", exact=True).fill("450")
        page.get_by_label("Element Design pressure (bar)", exact=True).press("Tab")
        frame.wait_for_function(
            "() => window.__subsea.spec.chain.find(item => item.id === 't1').treeType === 'hxt'", timeout=15000
        )
        assert drawing.locator('[data-id="t1"] .template-tree').count() == 6
        assert drawing.locator('[data-id="t1"] .template-hipps').count() == 0
        assert drawing.locator('[data-id="t1"] .custom-hub').count() == 5
        page.get_by_role("tab", name="Design specification", exact=True).click()
        page.get_by_label("Layout Design pressure (bar)", exact=True).fill("345")
        page.get_by_label("Layout Maximum temperature (deg C)", exact=True).fill("120")
        page.get_by_label("Layout Water depth (m)", exact=True).fill("1500")
        page.get_by_label("Layout Design flow rate (m3/day)", exact=True).fill("5000")
        page.get_by_role("button", name="Apply design specification", exact=True).click()
        frame.wait_for_function("() => window.__subsea.spec.designLimits && window.__subsea.spec.designLimits.pressureBar === 345", timeout=15000)
        assert frame.evaluate("window.__subsea.spec.chain.find(item => item.id === 't1').designLimits.pressureBar") == 450
        assert frame.evaluate("window.syncTestToken") == "preserve-this-editor"
        assert frame.evaluate("window.__subsea.spec.connections[0].connectionType") == "umbilical_dynamic"
        print("PASS: template options, custom hubs, layout defaults and per-element limits synchronize without resets")
        page.get_by_role("button", name="Load template", exact=True).click()
        page.wait_for_timeout(1500)
        reset_frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        assert reset_frame.evaluate("window.syncTestToken") is None
        assert not reset_frame.evaluate("(id) => window.__subsea.spec.chain.some(item => item.id === id)", item_id)
        print("PASS: explicit preset reload resets the design without restoring stale viewer state")
        # A deleted/absent main host must not be recreated by sidebar reruns.
        drawing.locator(".host.el .hit").click(force=True, position={"x": 2, "y": 2})
        drawing.locator("#b_delete").click()
        reset_frame.wait_for_function("() => !window.__subsea.spec.host")
        page.wait_for_timeout(1000)
        theme = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Theme"))
        theme.get_by_role("combobox").click()
        page.get_by_role("option", name="Engineering – monochrome (sheet)", exact=True).click()
        reset_frame.wait_for_function("() => window.__subsea.spec.themeName === 'mono'")
        assert drawing.locator('.el[data-type="jacket"]').count() == 0, reset_frame.evaluate(
            "({host:window.__subsea.spec.host, hosts:window.__subsea.spec.chain.filter(i=>['jacket','fpso'].includes(i.type)), selected:window.__subsea.sel})"
        )
        page.get_by_text("Legend", exact=True).click()
        page.wait_for_timeout(800)
        assert not reset_frame.evaluate("window.__subsea.spec.host")
        assert drawing.locator('.el[data-type="jacket"]').count() == 0
        page.get_by_role("tab", name="Host & risers", exact=True).click()
        page.get_by_text("Preset train source (separate from independently drawn hosts)", exact=True).click()
        page.get_by_text("Include a host / source", exact=True).click()
        reset_frame.wait_for_function("() => !!window.__subsea.spec.host")
        from subsea.presets import PRESETS
        blank = next(name for name in PRESETS if name.startswith("Blank canvas"))
        preset_select = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("label", has_text="Preset"))
        preset_select.get_by_role("combobox").click()
        preset_select.get_by_role("combobox").fill(blank)
        page.get_by_role("option", name=blank, exact=True).click()
        page.get_by_role("button", name="Load template", exact=True).click()
        page.wait_for_timeout(1500)
        blank_frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        assert not blank_frame.evaluate("window.__subsea.spec.host"), blank_frame.evaluate(
            "({title:window.__subsea.spec.title, host:window.__subsea.spec.host, freeform:window.__subsea.spec.freeform, chain:window.__subsea.spec.chain})"
        )
        drawing.locator("#b_palette").click()
        drawing.locator('.palette-item[data-type="fpso"]').click()
        drawing.locator("#palette-close").click()
        drawing.locator("#svg").click(position={"x": 400, "y": 180}, force=True)
        blank_frame.wait_for_function("() => window.__subsea.spec.chain.some(i => i.type === 'fpso')")
        page.wait_for_timeout(1200)
        page.get_by_text("Sea level", exact=True).click()
        page.get_by_text("Show sea level", exact=True).click()
        page.get_by_label("Sea-level offset", exact=True).fill("35")
        page.get_by_label("Sea-level offset", exact=True).press("Tab")
        blank_frame.wait_for_function("() => window.__subsea.spec.seaLevel.offset === 35")
        assert drawing.locator("#sea-level").count() == 1
        assert drawing.locator('.el[data-type="fpso"]').count() == 1
        assert drawing.locator('.el[data-type="jacket"]').count() == 0
        assert not blank_frame.evaluate("window.__subsea.spec.host")
        print("PASS: theme/sidebar/preset changes do not create phantom hosts; sea-level controls synchronize")
        drawing.locator('[data-type="fpso"] .hit').click(force=True, position={"x": 3, "y": 3})
        page.get_by_role("tab", name="Selected item", exact=True).click()
        page.get_by_label("Available J-tubes", exact=True).wait_for(timeout=15000)
        page.get_by_label("Available J-tubes", exact=True).fill("6")
        page.get_by_label("Available J-tubes", exact=True).press("Tab")
        blank_frame.wait_for_function("() => window.__subsea.spec.chain.find(i => i.type === 'fpso').slots?.length === 6")
        assert drawing.locator(".j-tube-port").count() == 6
        drawing.locator("#b_palette").click()
        drawing.locator('.palette-item[data-type="plet"]').click()
        drawing.locator("#palette-close").click()
        drawing.locator("#svg").click(position={"x": 600, "y": 400}, force=True)
        blank_frame.wait_for_function("() => window.__subsea.spec.chain.some(i => i.type === 'plet')")
        drawing.locator("#i_port_id").select_option("P-left")
        drawing.locator("#i_port_service").select_option("water_injection")
        drawing.locator("#insp").click(position={"x": 1, "y": 1})
        page.get_by_text("Individual inlet / outlet fluids", exact=True).wait_for(timeout=15000)
        page.get_by_label("Element label", exact=True).fill("Water PLET")
        page.get_by_label("Element label", exact=True).press("Tab")
        blank_frame.wait_for_function(
            "() => window.__subsea.spec.chain.find(i => i.type === 'plet').portOverrides['P-left'].connectionType === 'water_injection'"
        )
        page.get_by_role("button", name="New blank design", exact=True).click()
        page.wait_for_timeout(1500)
        clean_frame = next(frame for frame in page.frames if frame.evaluate("() => !!window.__subsea"))
        assert clean_frame.evaluate("window.__subsea.spec.freeform") is True
        assert clean_frame.evaluate("window.__subsea.spec.chain") == []
        assert not clean_frame.evaluate("window.__subsea.spec.host")
        assert drawing.locator(".el").count() == 0
        print("PASS: J-tube count and per-port service settings synchronize; New blank design clears previous drawing")
        assert not errors, errors
        assert page.locator('[data-testid="stException"]').count() == 0
        browser.close()


if __name__ == "__main__":
    run()
