"""Offline 3D rendering, shared geometry and interaction regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright, expect

from subsea.cases import CaseStore
from subsea.catalog import CATALOG
from subsea.html import build_html
from subsea.installation import installation_list
from subsea.presets import get_preset
from subsea.riser_detail import illustrated_riser_configuration
from subsea.spec import validate
from test_connections import browser_executable


def design():
    detail = illustrated_riser_configuration()
    detail["riserDetail"]["shapes"] = [
        {"id": "housing", "kind": "rect", "x": 20, "y": 20, "width": 80, "height": 45, "fill": "#778899"},
        {"id": "vessel", "kind": "ellipse", "x": 110, "y": 20, "width": 70, "height": 40},
    ]
    return {"freeform": True, "animate": True, "showLegend": False,
            "chain": [{"id": "host", "type": "jacket", "x": 80, "y": 100},
                      {"id": "custom", "type": "custom_element", "x": 440, "y": 280, "tag": "RB-1", **detail},
                      {"id": "tree", "type": "template", "x": 1000, "y": 180, "wells": 3, "treeType": "vxt"}],
            "connections": [
                {"from": "host", "fromPort": "J-0", "to": "custom", "toPort": "P-left",
                 "lane": "P", "connectionType": "gas", "kind": "riser", "psv": True},
                {"from": "custom", "fromPort": "P-right", "to": "tree", "toPort": "P-left", "lane": "P",
                 "connectionType": "gas", "flow": "reverse", "waypoints": [{"x": 750, "y": 400}]}]}


class ThreeDTests(unittest.TestCase):
    def test_anchor_editor_inserts_edits_drags_removes_and_reloads_all_lanes(self):
        spec = {"freeform": True, "showLegend": False, "animate": False,
                "chain": [{"id": "line", "type": "pipeline_rigid", "x": 80, "y": 120, "w": 240},
                          {"id": "m1", "type": "manifold", "x": 650, "y": 250, "slots": 4}],
                "connections": [{"from": "line", "fromPort": f"{lane}-right", "to": "m1", "toPort": f"{lane}-left",
                                 "lane": lane, "style": "flex", "label": f"Retain {lane}", "provider": "Example",
                                 "waypoints": [{"x": 390, "y": 280}, {"x": 570, "y": 350}]}
                                for lane in ("P", "S", "U")]}
        with tempfile.TemporaryDirectory(prefix="subsea-anchor-editor-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "anchors.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                page.click("#scene3d-top")
                page.click("#scene3d-anchor-mode")
                for index, lane in enumerate(("P", "S", "U")):
                    key = json.dumps(["connection", index], separators=(",", ":"))
                    page.locator("#scene3d-route").select_option(key)
                    page.locator("#scene3d-anchor").select_option("0")
                    page.click("#scene3d-anchor-add")
                    anchors = page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index)
                    self.assertEqual(len(anchors), 3)
                    self.assertEqual([anchors[0], anchors[2]], spec["connections"][index]["waypoints"])
                    for field, value in (("x", 460 + index * 10), ("y", 430 + index * 50), ("height", 2 + index)):
                        page.locator("#scene3d-anchor-" + field).fill(str(value))
                        page.locator("#scene3d-anchor-" + field).press("Tab")
                    anchors = page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index)
                    self.assertEqual(anchors[1], {"x": 460 + index * 10, "y": 430 + index * 50, "elevation3D": 2 + index})
                    before = page.evaluate("structuredClone(window.__subsea.spec)")
                    page.locator("#scene3d-anchor-x").fill("")
                    page.locator("#scene3d-anchor-x").press("Tab")
                    self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                    self.assertIn("finite numbers", page.locator("#scene3d-error").text_content())
                    page.locator("#scene3d-anchor-x").fill(str(anchors[1]["x"]))
                    page.locator("#scene3d-anchor-x").press("Tab")

                    handle = page.evaluate("""key=>window.__subsea.scene3D.diagnostics().connectionHandles.find(
                        h=>h.routeKey===key&&h.kind==='bend'&&h.waypointIndex===1)""", key)
                    canvas = page.locator("#scene3d canvas").bounding_box()
                    x, y = canvas["x"] + handle["screen"]["x"], canvas["y"] + handle["screen"]["y"]
                    before = page.evaluate("structuredClone(window.__subsea.spec)")
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x + 45, y + 35, steps=6)
                    self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                    page.keyboard.press("Escape")
                    page.mouse.up()
                    self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x + 45, y + 35, steps=6)
                    page.mouse.up()
                    moved = page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index)
                    self.assertNotEqual(moved[1], anchors[1])
                    self.assertEqual(moved[1]["elevation3D"], anchors[1]["elevation3D"])
                    self.assertEqual([moved[0], moved[2]], [anchors[0], anchors[2]])

                    ring = page.evaluate("""key=>window.__subsea.scene3D.diagnostics().connectionHandles.find(
                        h=>h.routeKey===key&&h.kind==='insert'&&h.waypointIndex===1)""", key)
                    page.mouse.click(canvas["x"] + ring["screen"]["x"], canvas["y"] + ring["screen"]["y"])
                    inserted = page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index)
                    self.assertEqual(len(inserted), 4)
                    self.assertEqual(inserted[:1] + inserted[2:], moved)
                    page.click("#scene3d-anchor-remove")
                    self.assertEqual(page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index), moved)
                    for _ in range(len(moved)):
                        page.click("#scene3d-anchor-remove")
                    self.assertEqual(page.evaluate("i=>window.__subsea.spec.connections[i].waypoints", index), [])
                    self.assertTrue(page.locator("#scene3d-anchor-remove").is_disabled())
                    page.click("#scene3d-anchor-add")
                    current = page.evaluate("i=>window.__subsea.spec.connections[i]", index)
                    self.assertEqual({k: v for k, v in current.items() if k != "waypoints"},
                                     {k: v for k, v in spec["connections"][index].items() if k != "waypoints"})
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertTrue(installation_list(saved).equals(installation_list(spec)))
                self.assertFalse(validate(saved), validate(saved))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case_id, version = store.save("Anchor editing", saved)
                self.assertEqual(store.load(case_id, version), saved)
                with page.expect_download() as download:
                    page.click("#b_html")
                exported = Path(directory) / "exported.html"
                download.value.save_as(exported)
                page.goto(exported.as_uri())
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                self.assertEqual(page.evaluate("window.__subsea.spec.connections"), saved["connections"])
                self.assertTrue(page.evaluate("""()=>{const s=window.__subsea.scene3D.diagnostics();
                    return s.routes.filter(r=>Number.isInteger(r.index)).every(r=>['from','to'].every(end=>
                        JSON.stringify(r[end])===JSON.stringify(s.models.find(m=>m.id===r[end+'Id']).ports.find(p=>p.id===r[end+'Port']).point)));
                }"""))
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_anchor_editor_covers_pipeline_symbols_preset_risers_and_implicit_links(self):
        spec = {"showLegend": False, "animate": False,
                "host": {"id": "host", "type": "jacket", "slots": ["P", "S", "U"],
                         "risers": [{"lane": lane, "slot": i, "style": "rigid"} for i, lane in enumerate(("P", "S", "U"))]},
                "chain": [{"id": "line", "type": "pipeline_pip", "w": 300},
                          {"id": "plet", "type": "plet"}, {"id": "valve", "type": "valve_gate"},
                          {"id": "m1", "type": "manifold", "slots": 4}]}
        with tempfile.TemporaryDirectory(prefix="subsea-anchor-preset-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                path = Path(directory) / "preset.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                page.evaluate("window.__subsea.move3DEquipment('m1',160,70)")
                page.click("#scene3d-anchor-mode")
                source = page.evaluate("window.__subsea.getScene3D()")
                equipment = page.evaluate("window.__subsea.scene3D.diagnostics().equipmentRoutes")
                self.assertEqual({r["lane"] for r in equipment}, {"P", "S", "U"})
                keys = [r["routeKey"] for r in source["routes"]] + [r["routeKey"] for r in equipment]
                self.assertEqual(len(set(keys)), len(keys))
                self.assertTrue(any(json.loads(k)[0] == "riser" for k in keys))
                self.assertTrue(any(json.loads(k)[0] == "implicit" for k in keys))
                self.assertTrue(any(json.loads(k)[0] == "bridge" for k in keys))
                for i, key in enumerate(keys):
                    page.locator("#scene3d-route").select_option(key)
                    page.click("#scene3d-anchor-add")
                    page.locator("#scene3d-anchor-y").fill(str(400 + i * 15))
                    page.locator("#scene3d-anchor-y").press("Tab")
                    self.assertEqual(len(page.evaluate("k=>window.__subsea.spec.routeAnchors3D[k]", key)), 1)
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertFalse(saved.get("connections"), "Editing preset/inline routes must not invent costing connections")
                self.assertTrue(installation_list(saved).equals(installation_list(spec)))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case_id, version = store.save("Preset anchors", saved)
                self.assertEqual(store.load(case_id, version), saved)
                before = page.evaluate("window.__subsea.scene3D.diagnostics().equipmentRoutes")
                page.evaluate("window.__subsea.move3DEquipment('line',100,50)")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='line').position[0]===window.__subsea.getScene3D().nodes.find(n=>n.id==='line').box.cx*.08")
                after = page.evaluate("window.__subsea.scene3D.diagnostics().equipmentRoutes")
                for old, new in zip(before, after):
                    self.assertEqual(old["anchors"], new["anchors"])
                    for end in ("from", "to"):
                        self.assertAlmostEqual(new[end][0] - old[end][0], 8)
                        self.assertAlmostEqual(new[end][2] - old[end][2], 4)
                current = page.evaluate("structuredClone(window.__subsea.spec)")
                loaded = Path(directory) / "loaded.html"
                loaded.write_text(build_html(current), encoding="utf-8")
                page.goto(loaded.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                self.assertEqual(page.evaluate("window.__subsea.spec.routeAnchors3D"), saved["routeAnchors3D"])
                self.assertEqual(page.evaluate("window.__subsea.scene3D.diagnostics().equipmentRoutes"), after)
                page.evaluate("""()=>{
                    const s=structuredClone(window.__subsea.spec);s.host.risers.reverse();
                    s.overrides.line.scale3D=.5;window.__subsea.replaceSpec(s);
                }""")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='line').scale3D===.5")
                self.assertEqual(set(page.evaluate("window.__subsea.getScene3D().routes.map(r=>r.routeKey)")),
                                 {r["routeKey"] for r in source["routes"]})
                scaled = page.evaluate("window.__subsea.scene3D.diagnostics().equipmentRoutes")
                center = page.evaluate("window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='line').position")
                for old, new in zip(after, scaled):
                    self.assertEqual(old["anchors"], new["anchors"])
                    for end in ("from", "to"):
                        for axis in range(3):
                            self.assertAlmostEqual(new[end][axis], center[axis] + (old[end][axis] - center[axis]) * .5)
                page.click("#scene3d-anchor-mode")
                key = equipment[0]["routeKey"]
                page.locator("#scene3d-route").select_option(key)
                page.click("#scene3d-anchor-remove")
                remaining = page.evaluate("window.__subsea.spec.routeAnchors3D")
                self.assertNotIn(key, remaining)
                self.assertEqual(len(remaining), len(keys) - 1)
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
            finally:
                browser.close()

    def test_drag_connect_route_and_reconnect_all_three_lanes(self):
        spec = {"freeform": True, "showLegend": False, "animate": False,
                "chain": [{"id": "line", "type": "pipeline_rigid", "x": 80, "y": 120, "w": 240},
                          {"id": "m1", "type": "manifold", "x": 600, "y": 180, "slots": 4},
                          {"id": "m2", "type": "manifold", "x": 1000, "y": 450, "slots": 4}],
                "overrides": {"m1": {"scale3D": .5}, "m2": {"scale3D": .75}}}
        with tempfile.TemporaryDirectory(prefix="subsea-3d-connect-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "connect.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                page.click("#scene3d-top")
                page.click("#scene3d-connect")

                def handle(**selector):
                    handles = page.evaluate("window.__subsea.scene3D.diagnostics().connectionHandles")
                    return next(h for h in handles if all(h.get(k) == v for k, v in selector.items()))

                def location(h):
                    canvas = page.locator("#scene3d canvas").bounding_box()
                    return canvas["x"] + h["screen"]["x"], canvas["y"] + h["screen"]["y"]

                def drag(start, end):
                    page.mouse.move(*location(start))
                    page.mouse.down()
                    page.mouse.move(*location(end), steps=8)

                def check_attachments():
                    page.wait_for_function("""()=>{
                        const scene=window.__subsea.scene3D.diagnostics();
                        return scene.routes.filter(r=>Number.isInteger(r.index)).every(r=>
                            ['from','to'].every(end=>{
                                const m=scene.models.find(m=>m.id===r[end+'Id']);
                                return JSON.stringify(r[end])===JSON.stringify(m.ports.find(p=>p.id===r[end+'Port']).point);
                            }));
                    }""")
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")

                for index, lane in enumerate(("P", "S", "U")):
                    before = page.evaluate("structuredClone(window.__subsea.spec)")
                    drag(handle(kind="port", id="line", port=f"{lane}-right"),
                         handle(kind="port", id="m1", port=f"{lane}-left"))
                    self.assertEqual(page.evaluate("window.__subsea.spec"), before, "Preview must not change the design")
                    page.mouse.up()
                    connections = page.evaluate("window.__subsea.spec.connections || []")
                    self.assertEqual(len(connections), index + 1)
                    self.assertEqual(connections[index], {"from": "line", "fromPort": f"{lane}-right", "to": "m1",
                                                         "toPort": f"{lane}-left", "lane": lane,
                                                         "style": "flex", "installationStatus": "New"})
                    check_attachments()

                before = page.evaluate("structuredClone(window.__subsea.spec)")
                bend = handle(kind="bend", index=2)
                x, y = location(bend)
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + 65, y + 100, steps=8)
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                page.mouse.up()
                waypoints = page.evaluate("window.__subsea.spec.connections[2].waypoints")
                self.assertEqual(len(waypoints), 1)
                self.assertNotEqual(waypoints[0], {"x": bend["point"][0] / .08, "y": bend["point"][2] / .08})
                check_attachments()

                drag(handle(kind="endpoint", index=2, end="to"), handle(kind="port", id="m2", port="U-left"))
                page.mouse.up()
                connection = page.evaluate("window.__subsea.spec.connections[2]")
                self.assertEqual((connection["to"], connection["toPort"], connection["lane"]), ("m2", "U-left", "U"))
                self.assertEqual(connection["waypoints"], waypoints)
                check_attachments()
                page.evaluate("window.__subsea.move3DEquipment('m2',120,70)")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='m2').position[0]===window.__subsea.getScene3D().nodes.find(n=>n.id==='m2').box.cx*.08")
                check_attachments()

                def export_hashes():
                    return page.evaluate("""async()=>{
                        const viewer=window.__subsea.scene3D;
                        const hash=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)));
                        return {png:await hash(await (await viewer.snapshot()).arrayBuffer()),
                            svg:await hash(new TextEncoder().encode(viewer.svgSnapshot('Routing')))};
                    }""")

                with_handles = export_hashes()
                page.click("#scene3d-orbit")
                self.assertEqual(export_hashes(), with_handles, "Editing handles must not appear in PNG or SVG exports")
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertFalse(validate(saved), validate(saved))
                reloaded = Path(directory) / "reloaded.html"
                reloaded.write_text(build_html(saved), encoding="utf-8")
                page.goto(reloaded.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                self.assertEqual(page.evaluate("window.__subsea.spec.connections"), saved["connections"])
                check_attachments()
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_drag_connection_rejects_mismatch_and_cancels_without_changes(self):
        spec = {"freeform": True, "showLegend": False, "animate": False,
                "chain": [{"id": "line", "type": "pipeline_rigid", "x": 80, "y": 120, "w": 240},
                          {"id": "m1", "type": "manifold", "x": 600, "y": 250, "slots": 4}]}
        with tempfile.TemporaryDirectory(prefix="subsea-3d-connect-cancel-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 950})
                path = Path(directory) / "cancel.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0")
                page.click("#scene3d-top")
                page.click("#scene3d-connect")
                before = page.evaluate("structuredClone(window.__subsea.spec)")

                def drag_to(port, cancel=False, lane="P"):
                    handles = page.evaluate("window.__subsea.scene3D.diagnostics().connectionHandles")
                    canvas = page.locator("#scene3d canvas").bounding_box()
                    start = next(h for h in handles if h.get("id") == "line" and h.get("port") == f"{lane}-right")
                    target = next(h for h in handles if h.get("id") == "m1" and h.get("port") == port)
                    page.mouse.move(canvas["x"] + start["screen"]["x"], canvas["y"] + start["screen"]["y"])
                    page.mouse.down()
                    page.mouse.move(canvas["x"] + target["screen"]["x"], canvas["y"] + target["screen"]["y"], steps=8)
                    if cancel == "pointer":
                        page.locator("#scene3d canvas").dispatch_event("pointercancel", {"pointerId": 1})
                    elif cancel:
                        page.keyboard.press("Escape")
                    page.mouse.up()

                drag_to("U-left")
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                self.assertIn("No connection made", page.locator("#scene3d-info").text_content())
                drag_to("P-left", cancel=True)
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                drag_to("P-left", cancel="pointer")
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                drag_to("P-left")
                connected = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertEqual(len(connected["connections"]), 1)
                drag_to("S-left", lane="S")
                connected = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertEqual(len(connected["connections"]), 2)
                drag_to("P-left")
                self.assertEqual(page.evaluate("window.__subsea.spec"), connected)
                self.assertIn("already connected", page.locator("#scene3d-error").text_content())

                bend = next(h for h in page.evaluate("window.__subsea.scene3D.diagnostics().connectionHandles") if h["kind"] == "bend")
                canvas = page.locator("#scene3d canvas").bounding_box()
                x, y = canvas["x"] + bend["screen"]["x"], canvas["y"] + bend["screen"]["y"]
                routes = page.evaluate("window.__subsea.scene3D.diagnostics().routes")
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + 40, y + 60, steps=5)
                page.keyboard.press("Escape")
                page.mouse.up()
                self.assertEqual(page.evaluate("window.__subsea.spec"), connected)
                self.assertEqual(page.evaluate("window.__subsea.scene3D.diagnostics().routes"), routes)
            finally:
                browser.close()

    def test_per_element_3d_size_controls_geometry_connections_and_persistence(self):
        spec = design()
        spec["animate"] = False
        with tempfile.TemporaryDirectory(prefix="subsea-3d-size-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "size.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)

                def check_attachments():
                    source = page.evaluate("window.__subsea.getScene3D()")
                    scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                    for binding in source["routes"]:
                        route = next(r for r in scene["routes"] if r["index"] == binding["index"])
                        for end in ("from", "to"):
                            model = next(m for m in scene["models"] if m["id"] == binding[end])
                            port_id = binding[end + "Port"]
                            attached = next((p["deck"] for p in model["attachments"] if p["id"] == port_id), None)
                            if attached is None:
                                attached = next(p["point"] for p in model["ports"] if p["id"] == port_id)
                            self.assertEqual(route[end], attached)
                    host = next(m for m in scene["models"] if m["id"] == "host")
                    self.assertEqual(scene["psvs"], [next(p["deck"] for p in host["attachments"] if p["id"] == "J-0")])
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")

                for item_id, percent in (("host", 50), ("custom", 150), ("tree", 10)):
                    page.click("#b_2d")
                    page.locator("#svg").click(position={"x": 5, "y": 5})
                    page.locator(f'#content .el[data-id="{item_id}"] .hit').click(force=True)
                    page.click("#b_3d")
                    self.assertEqual(page.evaluate("window.__subsea.sel"), item_id)
                    before = next(m for m in page.evaluate("window.__subsea.scene3D.diagnostics().models") if m["id"] == item_id)
                    geometry = page.evaluate("window.__subsea.getScene3D().nodes.map(n=>({id:n.id,box:n.box,ports:n.ports,pipes:n.pipes}))")
                    page.locator("#i_scale3d").fill(str(percent))
                    page.locator("#i_scale3d").press("Tab")
                    page.wait_for_function("p=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id===p.id).scale3D===p.factor || document.querySelector('#scene3d-error').textContent",
                                           arg={"id": item_id, "factor": percent / 100})
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                    current = next(m for m in page.evaluate("window.__subsea.scene3D.diagnostics().models") if m["id"] == item_id)
                    self.assertEqual(current["position"], before["position"])
                    for axis in range(3):
                        for edge in ("min", "max"):
                            expected = before["position"][axis] + (before["bounds"][edge][axis] - before["position"][axis]) * percent / 100
                            self.assertAlmostEqual(current["bounds"][edge][axis], expected, places=5)
                    check_attachments()
                    self.assertEqual(page.evaluate("window.__subsea.getScene3D().nodes.map(n=>({id:n.id,box:n.box,ports:n.ports,pipes:n.pipes}))"), geometry)
                self.assertEqual(page.evaluate("window.__subsea.spec.chain"), spec["chain"])
                self.assertEqual(page.evaluate("window.__subsea.spec.connections"), spec["connections"])
                page.locator("#i_scale3d").fill("0")
                page.locator("#i_scale3d").press("Tab")
                self.assertEqual(page.evaluate("window.__subsea.spec.overrides.tree.scale3D"), .1)
                page.locator("#i_scale3d").fill("1")
                page.locator("#i_scale3d").press("Tab")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='tree').scale3D===.01")
                check_attachments()
                page.click("#i_3d_larger")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='tree').scale3D===.11")
                page.click("#i_3d_smaller")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='tree').scale3D===.01")
                page.click("#i_3d_reset")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='tree').scale3D===1")
                page.evaluate("window.__subsea.move3DEquipment('custom',45,30)")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(m=>m.id==='custom').position[0]===window.__subsea.getScene3D().nodes.find(n=>n.id==='custom').box.cx*.08")
                check_attachments()
                saved = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertTrue(installation_list(saved).equals(installation_list(spec)))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case_id, version = store.save("Independent 3D size", saved)
                self.assertEqual(store.load(case_id, version), saved)
                with page.expect_download() as download:
                    page.click("#b_html")
                exported = Path(directory) / "resized.html"
                download.value.save_as(exported)
                page.goto(exported.as_uri())
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                self.assertEqual(page.evaluate("window.__subsea.spec"), saved)
                sizes = {m["id"]: m["scale3D"] for m in page.evaluate("window.__subsea.scene3D.diagnostics().models")}
                self.assertEqual(sizes, {"host": .5, "custom": 1.5, "tree": 1})
                check_attachments()
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_3d_size_preserves_inline_schematic_piping(self):
        spec = {"animate": False, "showLegend": False, "chain": [
            {"id": "line", "type": "pipeline_pip", "w": 240},
            {"id": "template", "type": "template", "wells": 4}],
            "overrides": {"template": {"scale3D": .25}}}
        with tempfile.TemporaryDirectory(prefix="subsea-3d-inline-size-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page()
                path = Path(directory) / "inline.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                bridges = [r for r in scene["routes"] if r["autoBridge"]]
                self.assertEqual({r["lane"] for r in bridges}, {"P", "S", "U"})
                for route in bridges:
                    for end in ("from", "to"):
                        model = next(m for m in scene["models"] if m["id"] == route[end + "Id"])
                        self.assertEqual(route[end], next(p["point"] for p in model["ports"] if p["id"] == route[end + "Port"]))
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
            finally:
                browser.close()

    def test_ship_shaped_fpso_and_turret_attachments(self):
        spec = get_preset("Single template to FPSO")
        spec["animate"] = False
        spec["host"].update({"id": "host", "slots": ["Production", "Control"]})
        spec["host"]["risers"][0]["psv"] = True
        spec["host"]["risers"][1]["slot"] = 1
        with tempfile.TemporaryDirectory(prefix="subsea-fpso-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "fpso.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                for part in ("hull", "accommodation", "crane", "helideck", "turret"):
                    self.assertEqual(page.locator(f'#content .fpso-{part}').count(), 1)
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)

                def check_turret():
                    source = page.evaluate("window.__subsea.getScene3D()")
                    page.wait_for_function("""source=>{
                        const model=window.__subsea.scene3D.diagnostics().models.find(n=>n.id==='host');
                        const host=source.nodes.find(n=>n.id==='host');
                        return Math.abs(model.position[0]-host.box.cx*.08)<1e-6
                            && Math.abs(model.position[2]-host.box.cy*.08)<1e-6;
                    }""", arg=source)
                    scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                    host = next(n for n in scene["models"] if n["id"] == "host")
                    ship = host["vessel"]
                    self.assertEqual(ship["processModules"], 4)
                    self.assertEqual(ship["helidecks"], 1)
                    self.assertEqual(ship["moorings"], 6)
                    self.assertGreater(ship["windows"], 20)
                    self.assertGreater(ship["craneMembers"], 20)
                    self.assertGreater(ship["hullColor"][0], ship["hullColor"][1] * 2)
                    rings = [ship["hullVertices"][start:start + 24] for start in range(0, len(ship["hullVertices"]), 24)]
                    widths = [max(r[2::3]) - min(r[2::3]) for r in rings]
                    self.assertLess(widths[-1], max(widths) * .1)
                    self.assertLess(widths[0], max(widths) * .8)
                    self.assertGreater(max(rings[2][1::3]) - min(rings[2][1::3]), 1)
                    self.assertEqual(scene["psvs"], [next(a["deck"] for a in host["attachments"] if a["id"] == "J-0")])
                    self.assertGreater(scene["psvs"][0][1], host["position"][1] + max(rings[2][1::3]))
                    bindings = [r for r in source["routes"] if r.get("from") == "host"]
                    self.assertEqual(len(bindings), 2)
                    for binding in bindings:
                        route = next(r for r in scene["routes"] if r["fromId"] == "host" and r["fromPort"] == binding["fromPort"])
                        deck = next(a["deck"] for a in host["attachments"] if a["id"] == binding["fromPort"])
                        self.assertEqual(route["from"], deck)
                        self.assertAlmostEqual(deck[0], ship["turret"][0])
                        self.assertAlmostEqual(deck[1], ship["turret"][1])
                        self.assertLess(abs(deck[2] - ship["turret"][2]), ship["turretRadius"])
                    return host

                initial = check_turret()
                page.evaluate("window.__subsea.move3DEquipment('host',90,35)")
                moved = check_turret()
                self.assertAlmostEqual(moved["position"][0] - initial["position"][0], 90 * .08)
                changed = page.evaluate("structuredClone(window.__subsea.spec)")
                changed["overrides"]["host"]["scale"] = 1.3
                changed["branches"] = [{"id": "mirrored", "mirror": True, "host": changed["host"],
                                        "chain": changed["chain"], "lanes": changed["lanes"]}]
                changed.update({"host": None, "chain": [], "zones": []})
                page.evaluate("s=>window.__subsea.replaceSpec(s)", changed)
                mirrored = check_turret()
                self.assertTrue(page.evaluate("window.__subsea.getScene3D().nodes.find(n=>n.id==='host').mirrored"))
                self.assertGreater(mirrored["deckWidth"], initial["deckWidth"] * 1.25)
                self.assertLess(mirrored["vessel"]["turret"][0], mirrored["position"][0])
                vector = page.evaluate("window.__subsea.scene3D.svgSnapshot('Mirrored FPSO')")
                self.assertGreater(len(ET.fromstring(vector).findall("{http://www.w3.org/2000/svg}path")), 100)
                self.assertNotIn("NaN", vector)
                with page.expect_download() as download:
                    page.click("#b_html")
                exported = Path(directory) / "export.html"
                download.value.save_as(exported)
                page.goto(exported.as_uri())
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                self.assertEqual(page.evaluate("window.__subsea.spec"), changed)
                check_turret()
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_four_slot_jackup_preset_guided_risers(self):
        spec = get_preset("Single 4-slot template to jackup")
        with tempfile.TemporaryDirectory(prefix="subsea-jackup-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "jackup.html"
                path.write_text(build_html(spec), encoding="utf-8")
                page.goto(path.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                self.assertEqual(page.locator('#content .jackup-leg').count(), 3)
                self.assertEqual(page.locator('#content .jackup-spudcan').count(), 3)
                self.assertEqual(page.locator('#content .el[data-type="template"]').count(), 1)
                from test_hosts import assert_risers_attached
                assert_risers_attached(page)
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                host = next(n for n in scene["models"] if n["id"] == "jackup")
                self.assertEqual(host["spudcans"], 3)
                self.assertEqual(len(host["legCenters"]), 3)
                self.assertEqual(host["guides"], 3)
                self.assertEqual(host["brackets"], 9)
                self.assertEqual(len([s for s in host["structure"] if s["name"] == "Jackup leg chord"]), 9)
                for leg in host["structure"]:
                    if leg["name"] == "Jackup leg chord":
                        self.assertAlmostEqual(leg["ends"][0][0], leg["ends"][1][0])
                        self.assertAlmostEqual(leg["ends"][0][2], leg["ends"][1][2])
                routes = [r for r in scene["routes"] if r["fromId"] == "jackup"]
                self.assertEqual({r["lane"] for r in routes}, {"P", "S", "U"})
                changed = json.loads(json.dumps(spec))
                changed["host"]["showJTubes"] = False
                for riser in changed["host"]["risers"]:
                    riser["style"] = "flex"
                page.evaluate("s=>window.__subsea.replaceSpec(s)", changed)
                current = page.evaluate("window.__subsea.scene3D.diagnostics()")
                for old in routes:
                    new = next(r for r in current["routes"] if r["fromId"] == "jackup" and r["fromPort"] == old["fromPort"])
                    self.assertEqual(old["points"], new["points"], "Fixed jackup must not develop floating catenaries")
                changed["branches"] = [{"id": "mirrored", "mirror": True, "host": changed["host"],
                                        "chain": changed["chain"], "lanes": changed["lanes"]}]
                changed.update({"host": None, "chain": []})
                changed["overrides"] = {"jackup": {"scale": 1.2, "dx": 60, "dy": 25}}
                page.evaluate("s=>window.__subsea.replaceSpec(s)", changed)
                current = page.evaluate("window.__subsea.scene3D.diagnostics()")
                host = next(n for n in current["models"] if n["id"] == "jackup")
                source = page.evaluate("window.__subsea.getScene3D()")
                for binding in (r for r in source["routes"] if r.get("from") == "jackup"):
                    route = next(r for r in current["routes"] if r["fromId"] == "jackup" and r["fromPort"] == binding["fromPort"])
                    self.assertEqual(route["from"], next(a["deck"] for a in host["attachments"] if a["id"] == binding["fromPort"]))
                self.assertTrue(next(n for n in source["nodes"] if n["id"] == "jackup")["mirrored"])
                self.assertEqual(page.evaluate("window.__subsea.spec.branches[0].chain"), spec["chain"])
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_inline_piping_follows_drag_preview_commit_and_reload(self):
        self._check_inline_piping_follows_drag("template")

    def test_manifold_service_and_umbilical_follow_scaled_drag(self):
        self._check_inline_piping_follows_drag("manifold", .3)

    def _check_inline_piping_follows_drag(self, equipment_type, factor=1):
        spec = {"showLegend": False, "flow": "none", "animate": False,
                "host": {"id": "host", "type": "jacket", "slots": ["Production"],
                         "risers": [{"lane": "P", "slot": 0, "style": "rigid", "psv": True}]},
                "chain": [{"id": "line", "type": "pipeline_pip", "w": 240},
                          {"id": "template", "type": equipment_type, "wells": 2, "slots": 6}],
                "overrides": {"template": {"scale": .9, "scale3D": factor}}}
        with tempfile.TemporaryDirectory(prefix="subsea-3d-follow-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 950})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                html = Path(directory) / "follow.html"
                html.write_text(build_html(spec), encoding="utf-8")
                page.goto(html.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                before = page.evaluate("structuredClone(window.__subsea.spec)")
                page.evaluate("window.__subsea.move3DEquipment('template',160,70)")

                def check_attachments(preview=False):
                    source = page.evaluate("window.__subsea.getScene3D()")
                    if not preview:
                        page.wait_for_function("""source=>{
                            const models=window.__subsea.scene3D.diagnostics().models;
                            return source.nodes.filter(n=>!n.topside).every(n=>{
                                const model=models.find(m=>m.id===n.id);
                                return model && n.ports.every(p=>{
                                    const actual=model.ports.find(q=>q.id===p.id)?.point;
                                    return actual && [0,2].every((axis,i)=>Math.abs(actual[axis]-
                                        (model.position[axis]+(([p.x,p.y][i]*.08)-model.position[axis])*model.scale3D))<1e-7);
                                });
                            }) || document.querySelector('#scene3d-error').textContent;
                        }""", arg=source)
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                    scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                    bridges = [r for r in source["routes"] if r.get("autoBridge")]
                    self.assertEqual({r["lane"] for r in bridges}, {"P", "S", "U"})
                    for bridge in bridges:
                        route = next(r for r in scene["routes"] if r.get("autoBridge") and r["lane"] == bridge["lane"])
                        for end in ("from", "to"):
                            node = next(n for n in scene["models"] if n["id"] == bridge[end])
                            port = next(p for p in node["ports"] if p["id"] == bridge[end + "Port"])
                            self.assertEqual(route[end], port["point"])
                    riser = next(r for r in scene["routes"] if r.get("fromId") == "host")
                    host = next(n for n in scene["models"] if n["id"] == "host")
                    deck = next(p["deck"] for p in host["attachments"] if p["id"] == "J-0")
                    self.assertEqual(riser["from"], deck)
                    self.assertEqual(scene["psvs"], [deck])
                    line = next(n for n in scene["models"] if n["id"] == "line")
                    self.assertEqual(riser["to"], next(p["point"] for p in line["ports"] if p["id"] == "P-left"))
                    return scene

                check_attachments()
                page.evaluate("window.__subsea.move3DEquipment('line',-60,45)")
                check_attachments()
                committed = page.evaluate("structuredClone(window.__subsea.spec)")
                page.click("#scene3d-move")
                page.click("#scene3d-top")
                canvas = page.locator("#scene3d canvas").bounding_box()
                for item_id, cancel in (("template", True), ("host", True), ("template", False), ("host", False)):
                    model = page.evaluate("id=>window.__subsea.scene3D.diagnostics().models.find(n=>n.id===id)", item_id)
                    location = model["screen"]
                    page.mouse.move(canvas["x"] + location["x"], canvas["y"] + location["y"])
                    page.mouse.down()
                    page.mouse.move(canvas["x"] + location["x"] + 45, canvas["y"] + location["y"] + 20, steps=6)
                    preview = check_attachments(preview=True)
                    self.assertNotEqual(next(n["position"] for n in preview["models"] if n["id"] == item_id), model["position"])
                    self.assertEqual(page.evaluate("window.__subsea.spec"), committed, "Drag preview must not commit offsets")
                    if cancel:
                        page.keyboard.press("Escape")
                    page.mouse.up()
                    check_attachments()
                    current = page.evaluate("structuredClone(window.__subsea.spec)")
                    if cancel:
                        self.assertEqual(current, committed)
                    else:
                        self.assertNotEqual(current["overrides"].get(item_id), committed["overrides"].get(item_id))
                        committed = current
                for mirror in (False, True):
                    loaded = json.loads(json.dumps(committed))
                    loaded["mirror"] = mirror
                    page.evaluate("s=>window.__subsea.replaceSpec(s)", loaded)
                    check_attachments()
                self.assertEqual(page.evaluate("window.__subsea.spec.chain"), before["chain"])
                self.assertEqual(page.evaluate("window.__subsea.spec.connections || []"), before.get("connections", []))
                page.evaluate("s=>window.__subsea.replaceSpec(s)", {
                    "freeform": True, "chain": [{"id": "line", "type": "pipeline_rigid", "x": 0, "y": 100, "w": 240},
                                              {"id": "template", "type": "template", "x": 240, "y": 100}]})
                page.evaluate("window.__subsea.move3DEquipment('template',100,40)")
                self.assertFalse(page.evaluate("window.__subsea.getScene3D().routes.some(r=>r.autoBridge)"),
                                 "Freeform proximity must not invent an attachment")
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_bathymetry_and_interactive_3d_exports(self):
        spec = {"freeform": True, "showLegend": False, "flow": "forward",
                "title": "Terrain & export <test>",
                "chain": [{"id": "host", "type": "jacket", "x": 0, "y": 100},
                          {"id": "valve", "type": "valve_gate", "x": 300, "y": 160},
                          {"id": "control", "type": "sdu", "x": 500, "y": 300},
                          {"id": "line", "type": "pipeline_rigid", "x": 750, "y": 300, "w": 360, "pColor": "#2266ff"}]}
        with tempfile.TemporaryDirectory(prefix="subsea-3d-export-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 950}, accept_downloads=True)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                html = Path(directory) / "source.html"
                html.write_text(build_html(spec), encoding="utf-8")
                page.goto(html.as_uri())
                self.assertEqual(page.locator("#b_3d").text_content(), "3D view")
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0", timeout=30000)
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                self.assertGreater(scene["terrainRange"][1] - scene["terrainRange"][0], 2)
                self.assertLessEqual(scene["terrainRange"][1], -.19)
                self.assertEqual(scene["contours"], 0)
                self.assertFalse(scene["seabedGrid"])
                r, g, b = scene["seabedColor"]
                self.assertLess(max(r, g, b), .1)
                self.assertLess(max(r, g, b) - min(r, g, b), .02)
                self.assertFalse(page.evaluate("window.__subsea.scene3D.viewState().labels"))
                self.assertEqual(page.locator("#scene3d-labels").get_attribute("aria-pressed"), "false")
                self.assertFalse(page.evaluate("window.__subsea.spec.animate"))
                self.assertEqual(page.locator("#b_flow").get_attribute("aria-pressed"), "false")
                self.assertTrue(scene["flows"])
                self.assertTrue(all(not flow["visible"] for flow in scene["flows"]))
                page.click("#b_flow")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().flows.some(f=>f.visible)")
                page.click("#b_flow")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().flows.every(f=>!f.visible)")
                for node in scene["models"]:
                    if node["id"] in ("valve", "control"):
                        self.assertGreater(node["roofPanels"], 0)
                    elif node["id"] == "line":
                        self.assertEqual(node["roofPanels"], 0)
                before = page.evaluate("structuredClone(window.__subsea.spec)")
                page.click("#scene3d-labels")
                self.assertTrue(page.evaluate("window.__subsea.scene3D.viewState().labels"))
                page.evaluate("window.__subsea.scene3D.zoom(.8)")
                camera = page.evaluate("window.__subsea.scene3D.viewState()")
                with page.expect_download() as download:
                    page.click("#b_svg")
                vector = Path(directory) / "projection.svg"
                download.value.save_as(vector)
                drawing = ET.fromstring(vector.read_text(encoding="utf-8"))
                namespace = {"svg": "http://www.w3.org/2000/svg"}
                self.assertGreater(len(drawing.findall("svg:path", namespace)), 100)
                self.assertTrue(drawing.findall("svg:text", namespace), "Enabled labels must appear in the SVG")
                self.assertFalse(drawing.findall(".//svg:image", namespace), "SVG must contain vectors, not an embedded PNG")
                self.assertEqual(drawing.find("svg:title", namespace).text, spec["title"] + " - static 3D projection")
                self.assertNotIn("NaN", vector.read_text(encoding="utf-8"))
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                line = next(n for n in scene["models"] if n["id"] == "line")
                visible = page.evaluate("""async ({svg, view, samples}) => {
                    const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
                    const normalize = a => {const length=Math.hypot(...a);return a.map(x=>x/length)};
                    const forward=normalize(view.target.map((x,i)=>x-view.camera[i]));
                    const right=normalize(cross(forward,[0,1,0])), up=cross(right,forward);
                    const image=new Image(), url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));
                    try {
                        image.src=url;await image.decode();
                        const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
                        const context=canvas.getContext('2d');context.drawImage(image,0,0);
                        const tangent=Math.tan(view.fov*Math.PI/360), aspect=canvas.width/canvas.height;
                        return samples.map(p=>{
                            const relative=p.map((x,i)=>x-view.camera[i]), dot=a=>a.reduce((sum,x,i)=>sum+x*relative[i],0);
                            const x=Math.round((dot(right)/(dot(forward)*tangent*aspect)+1)*canvas.width/2);
                            const y=Math.round((1-dot(up)/(dot(forward)*tangent))*canvas.height/2);
                            const pixels=context.getImageData(x-2,y-2,5,5).data;
                            return Array.from({length:25},(_,i)=>pixels[i*4+2]>pixels[i*4+1]+12).some(Boolean);
                        });
                    } finally {URL.revokeObjectURL(url)}
                }""", {"svg": vector.read_text(encoding="utf-8"), "view": scene,
                        "samples": [[a + (b - a) * t for a, b in zip(line["pipePaths"][0]["points"][0],
                                                                   line["pipePaths"][0]["points"][-1])]
                                    for t in (.2, .35, .5, .65, .8)]})
                self.assertTrue(all(visible), "Terrain must not paint over a continuous, above-ground flowline in SVG")
                with page.expect_download() as download:
                    page.click("#b_html")
                archive = Path(directory) / "offline.html"
                download.value.save_as(archive)
                exported = browser.new_page(viewport={"width": 1500, "height": 950})
                exported.context.set_offline(True)
                exported.on("pageerror", lambda e: errors.append(str(e)))
                requests = []
                exported.on("request", lambda r: requests.append(r.url))
                exported.goto(archive.as_uri())
                exported.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().active && window.__subsea.scene3D.diagnostics().drawCalls>0", timeout=30000)
                self.assertEqual(exported.locator("#scene3d-error").text_content(), "")
                self.assertEqual(exported.evaluate("window.__subsea.spec"), before)
                self.assertEqual(exported.evaluate("window.__subsea.scene3D.viewState()"), camera)
                self.assertFalse([url for url in requests if url.startswith(("http:", "https:"))])
                canvas = exported.locator("#scene3d canvas").bounding_box()
                x, y = canvas["x"] + 150, canvas["y"] + 150
                exported.mouse.move(x, y)
                exported.mouse.down()
                exported.mouse.move(x + 100, y + 40, steps=6)
                exported.mouse.up()
                self.assertNotEqual(exported.evaluate("window.__subsea.scene3D.viewState().theta"), camera["theta"])
                prior_target = exported.evaluate("window.__subsea.scene3D.viewState().target")
                exported.mouse.down(button="right")
                exported.mouse.move(x + 150, y + 60, steps=6)
                exported.mouse.up(button="right")
                self.assertNotEqual(exported.evaluate("window.__subsea.scene3D.viewState().target"), prior_target)
                prior_radius = exported.evaluate("window.__subsea.scene3D.viewState().radius")
                exported.mouse.wheel(0, 300)
                exported.wait_for_function("r=>window.__subsea.scene3D.viewState().radius!==r", arg=prior_radius)
                self.assertEqual(exported.evaluate("window.__subsea.spec"), before)
                exported.click("#b_2d")
                expect(exported.locator("#svg")).to_be_visible()
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_reference_models_and_piping_without_flow_overlays(self):
        spec = {
            "showLegend": False, "animate": False,
            "flow": "none",
            "host": {"id": "host", "type": "jacket", "showJTubes": False,
                     "slots": ["Production"], "risers": [{"slot": 0, "lane": "P", "style": "flex"}]},
            "chain": [{"id": "base", "type": "riser_base", "servicePorts": True, "umbilicalPorts": True,
                       "portConfig": {"mode": "additional", "lane": "P", "inlets": 2, "outlets": 2}},
                      {"id": "line", "type": "pipeline_rigid", "w": 200},
                      {"id": "plem", "type": "plem"},
                      {"id": "spool", "type": "spool"}],
        }
        with tempfile.TemporaryDirectory(prefix="subsea-3d-continuity-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                html = Path(directory) / "continuity.html"
                html.write_text(build_html(spec), encoding="utf-8")
                page.goto(html.as_uri())
                before = page.evaluate("structuredClone(window.__subsea.spec)")
                source = page.evaluate("window.__subsea.getScene3D()")
                line = next(n for n in source["nodes"] if n["id"] == "line")
                self.assertTrue(line["pipes"], "A physical flowline must not disappear when its flow overlay is disabled")
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0 || document.querySelector('#scene3d-error').textContent", timeout=30000)
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                host = next(n for n in scene["models"] if n["id"] == "host")
                self.assertGreater(host["topsideModules"], 1)
                self.assertGreater(host["craneMembers"], 3)
                legs = [p for p in host["structure"] if p["name"] == "Jacket leg / pile"]
                self.assertEqual(len(legs), 4)
                for part in host["structure"]:
                    self.assertGreater(part["color"][0], part["color"][2])
                    self.assertGreater(part["color"][1], part["color"][2])
                    if part["name"] == "Jacket leg / pile":
                        continue
                    for end in part["ends"]:
                        def distance_to_leg(leg):
                            a, b = leg["ends"]
                            fraction = (end[1] - a[1]) / (b[1] - a[1])
                            return sum((end[i] - (a[i] + (b[i] - a[i]) * fraction)) ** 2 for i in (0, 2))
                        self.assertLess(min(distance_to_leg(leg) for leg in legs), 1e-8)
                riser = scene["routes"][0]
                for point in riser["points"]:
                    if point[1] > 2:
                        self.assertAlmostEqual(point[0], riser["from"][0])
                        self.assertAlmostEqual(point[2], riser["from"][2])
                visible_guides = json.loads(json.dumps(before))
                visible_guides["host"]["showJTubes"] = True
                page.evaluate("s=>window.__subsea.replaceSpec(s)", visible_guides)
                self.assertEqual(page.evaluate("window.__subsea.scene3D.diagnostics().routes[0].points"), riser["points"])
                page.evaluate("s=>window.__subsea.replaceSpec(s)", before)
                self.assertFalse(scene["flows"])
                for node in scene["models"]:
                    if node["id"] == "host":
                        continue
                    for port in node["ports"]:
                        ends = [point for pipe in node["pipePaths"] for point in (pipe["points"][0], pipe["points"][-1])]
                        self.assertTrue(any(sum((a - b) ** 2 for a, b in zip(port["point"], p)) < 1e-8 for p in ends),
                                        (node["id"], port, ends))
                plem = next(n for n in scene["models"] if n["id"] == "plem")
                self.assertGreater(plem["clamps"], 0)
                bore = plem["pipePaths"][0]
                self.assertGreater(max(p[1] for p in bore["points"]), bore["points"][0][1] + .4)
                self.assertLess(max(bore["color"]) - min(bore["color"]), .05)
                self.assertGreater(min(bore["color"]), .6)
                flowing = json.loads(json.dumps(before))
                flowing["flow"] = "forward"
                page.evaluate("s=>window.__subsea.replaceSpec(s)", flowing)
                after = page.evaluate("window.__subsea.getScene3D()")
                for node in source["nodes"]:
                    next_node = next(n for n in after["nodes"] if n["id"] == node["id"])
                    self.assertEqual([p["points"] for p in node["pipes"]], [p["points"] for p in next_node["pipes"]])
                page.evaluate("s=>window.__subsea.replaceSpec(s)", before)
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_rendering_flow_switch_and_edit(self):
        with tempfile.TemporaryDirectory(prefix="subsea-3d-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(),
                                         args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
                errors, requests = [], []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: requests.append(r.url))
                html = Path(directory) / "scene.html"
                html.write_text(build_html(design()), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                before = page.evaluate("structuredClone(window.__subsea.spec)")
                page.click("#b_palette")
                page.click('.palette-item[data-type="plet"]')
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0 || document.querySelector('#scene3d-error').textContent", timeout=30000)
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                data = page.evaluate("window.__subsea.scene3D.diagnostics()")
                self.assertEqual(len(data["models"]), 3)
                self.assertTrue(all(n["parts"] > 10 for n in data["models"]))
                custom = next(n for n in data["models"] if n["id"] == "custom")
                self.assertEqual(custom["customShapes"], 2)
                self.assertEqual(custom["valves"], len(before["chain"][1]["internalValves"]))
                self.assertGreater(custom["pipes"], 10)
                host = next(n for n in data["models"] if n["id"] == "host")
                self.assertEqual(len(data["psvs"]), 1)
                self.assertEqual(data["psvs"][0][1], host["pipeHeight"])
                self.assertEqual(data["psvs"][0], next(p["deck"] for p in host["attachments"] if p["id"] == "J-0"))
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                self.assertFalse([url for url in requests if url.startswith(("http:", "https:"))])
                flows = data["flows"]
                self.assertTrue(flows)
                page.wait_for_function("previous=>JSON.stringify(window.__subsea.scene3D.diagnostics().flows[0].points)!==previous",
                                       arg=json.dumps(flows[0]["points"]))
                page.click("#b_flow")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().flows.every(f=>!f.visible)")
                page.click("#b_flow")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().flows.some(f=>f.visible)")
                page.locator("#b_spd").evaluate("(e)=>{e.value='3';e.dispatchEvent(new Event('input',{bubbles:true}))}")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().speed===3")
                self.assertTrue(any(f["reverse"] for f in page.evaluate("window.__subsea.scene3D.diagnostics().flows")))
                page.click("#scene3d-move")
                page.click("#scene3d-top")
                location = page.evaluate("window.__subsea.scene3D.diagnostics().models.find(n=>n.id==='custom').screen")
                canvas = page.locator("#scene3d canvas").bounding_box()
                bindings = page.evaluate("window.__subsea.getScene3D().routes")

                def check_custom_endpoints():
                    scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                    moved = next(n for n in scene["models"] if n["id"] == "custom")
                    self.assertNotEqual(moved["position"], custom["position"])
                    for binding in bindings:
                        for end in ("from", "to"):
                            if binding.get(end) == "custom":
                                route = next(r for r in scene["routes"] if r["index"] == binding["index"])
                                port = next(p for p in moved["ports"] if p["id"] == binding[end + "Port"])
                                self.assertEqual(route[end], port["point"])

                page.mouse.move(canvas["x"] + location["x"], canvas["y"] + location["y"])
                page.mouse.down()
                page.mouse.move(canvas["x"] + location["x"] + 45, canvas["y"] + location["y"] + 25, steps=8)
                check_custom_endpoints()
                page.mouse.up()
                check_custom_endpoints()
                page.wait_for_function("()=>!!window.__subsea.spec.overrides.custom?.dx")
                edited = page.evaluate("structuredClone(window.__subsea.spec)")
                self.assertEqual(edited["chain"], before["chain"])
                self.assertEqual(edited["connections"], before["connections"])
                self.assertFalse(validate(edited))
                store = CaseStore(Path(directory) / "cases.sqlite3")
                case, version = store.save("3D position edits", edited)
                self.assertEqual(store.load(case, version), edited)
                page.click("#b_2d")
                expect(page.locator("#scene3d")).to_be_hidden()
                self.assertFalse(page.locator("#svg").evaluate("(svg)=>svg.classList.contains('placement')"))
                self.assertFalse(page.evaluate("window.__subsea.scene3D.diagnostics().active"))
                self.assertEqual(page.evaluate("window.__subsea.spec"), edited)
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().active")
                page.evaluate("()=>{const spec=structuredClone(window.__subsea.spec);spec.connections[1].flow='none';spec.mirror=true;window.__subsea.replaceSpec(spec)}")
                page.wait_for_function("()=>!window.__subsea.scene3D.diagnostics().flows.some(f=>f.connectionIndex===1)")
                self.assertEqual(page.evaluate("window.__subsea.scene3D.diagnostics().models.find(n=>n.id==='custom').customShapes"), 2)
                self.assertTrue(page.evaluate("window.__subsea.scene3D.diagnostics().models.every(n=>n.position.every(Number.isFinite))"))
                with page.expect_download() as download:
                    page.click("#b_png")
                image = Path(directory) / "scene.png"
                download.value.save_as(image)
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                page.evaluate("s=>window.__subsea.replaceSpec(s)", {
                    "showLegend": False, "animate": False,
                    "host": {"id": "legacy-host", "type": "jacket", "slots": ["J1"],
                             "risers": [{"slot": 0, "lane": "P", "style": "rigid", "psv": True}]},
                    "chain": [{"id": "plet", "type": "plet"}]})
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.some(n=>n.id==='legacy-host')")
                legacy = page.evaluate("window.__subsea.scene3D.diagnostics()")
                legacy_host = next(n for n in legacy["models"] if n["id"] == "legacy-host")
                self.assertEqual(len(legacy["psvs"]), 1)
                self.assertEqual(legacy["psvs"][0][1], legacy_host["pipeHeight"])
                self.assertEqual(legacy["psvs"][0], next(p["deck"] for p in legacy_host["attachments"] if p["id"] == "J-0"))
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_zoom_gray_hoods_and_host_risers(self):
        with tempfile.TemporaryDirectory(prefix="subsea-3d-routing-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                spec = design()
                spec["chain"][0]["showJTubes"] = True
                spec["chain"][1] = {"id": "custom", "type": "plet", "x": 450, "y": 330}
                html = Path(directory) / "routing.html"
                html.write_text(build_html(spec), encoding="utf-8")
                page.goto(html.as_uri())
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0 || document.querySelector('#scene3d-error').textContent", timeout=30000)
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                scene = page.evaluate("window.__subsea.scene3D.diagnostics()")
                self.assertFalse(scene["seabedGrid"])
                r, g, b = scene["seabedColor"]
                self.assertLess(max(r, g, b), .1)
                self.assertLess(max(r, g, b) - min(r, g, b), .02)
                for node in scene["models"]:
                    if node["type"] in ("template", "plet"):
                        self.assertGreaterEqual(node["roofPanels"], 2)
                        self.assertEqual(node["gussets"], 4)
                host = next(n for n in scene["models"] if n["id"] == "host")
                self.assertGreater(host["guides"], 0)
                self.assertEqual(host["brackets"], host["guides"] * 3)
                for port in host["attachments"]:
                    self.assertLess(abs(port["deck"][0] - host["position"][0]), host["deckWidth"] / 2)
                    self.assertLess(abs(port["deck"][2] - host["position"][2]), host["deckDepth"] / 2)
                riser = next(r for r in scene["routes"] if r["index"] == 0)
                self.assertEqual(riser["points"][0], riser["from"])
                for point in riser["points"]:
                    if point[1] > 2:
                        self.assertAlmostEqual(point[0], riser["from"][0])
                        self.assertAlmostEqual(point[2], riser["from"][2])
                flowline = next(r for r in scene["routes"] if r["index"] == 1)
                self.assertLessEqual(max(p[1] for p in flowline["points"]), 1.2 + 1e-6)
                before = page.evaluate("structuredClone(window.__subsea.spec)")
                page.click("#scene3d-top")
                location = next(n for n in page.evaluate("window.__subsea.scene3D.diagnostics().models") if n["id"] == "custom")["screen"]
                canvas = page.locator("#scene3d canvas").bounding_box()
                page.mouse.click(canvas["x"] + location["x"], canvas["y"] + location["y"])
                page.click("#scene3d-focus")
                focused = page.evaluate("window.__subsea.scene3D.diagnostics().radius")
                page.evaluate("window.__subsea.scene3D.zoom(.001)")
                self.assertLess(page.evaluate("window.__subsea.scene3D.diagnostics().radius"), .1)
                page.evaluate("window.__subsea.scene3D.zoom(10000000)")
                self.assertGreater(page.evaluate("window.__subsea.scene3D.diagnostics().radius"), 20000)
                page.click("#scene3d-focus")
                self.assertAlmostEqual(page.evaluate("window.__subsea.scene3D.diagnostics().radius"), focused)
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                # Reversing an attached riser must reverse the same physical path.
                reversed_spec = json.loads(json.dumps(spec))
                reversed_spec["connections"][0].update({"from": "custom", "fromPort": "P-left", "to": "host", "toPort": "J-0"})
                page.evaluate("s=>window.__subsea.replaceSpec(s)", reversed_spec)
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().routes[0].to[1]>10")
                reverse = page.evaluate("window.__subsea.scene3D.diagnostics().routes[0]")
                self.assertEqual(reverse["from"], riser["to"])
                self.assertEqual(reverse["to"], riser["from"])
                profiles = []
                for style in ("flex", "lazywave", "s_shape"):
                    flexible = json.loads(json.dumps(spec))
                    flexible["chain"][0]["type"] = "semisub"
                    flexible["chain"][0]["showJTubes"] = False
                    flexible["connections"][0]["style"] = style
                    page.evaluate("s=>window.__subsea.replaceSpec(s)", flexible)
                    page.wait_for_function("style=>window.__subsea.scene3D.diagnostics().routes[0].style===style", arg=style)
                    profile = page.evaluate("window.__subsea.scene3D.diagnostics().routes[0]")
                    self.assertEqual(profile["points"][0], profile["from"])
                    self.assertEqual(profile["points"][-1], profile["to"])
                    self.assertGreaterEqual(min(p[1] for p in profile["points"]), .65 - 1e-6)
                    profiles.append(profile["points"])
                self.assertNotEqual(profiles[0], profiles[1])
                self.assertNotEqual(profiles[1], profiles[2])
                single = json.loads(json.dumps(spec))
                single["chain"][0]["slots"] = ["Only J-tube"]
                page.evaluate("s=>window.__subsea.replaceSpec(s)", single)
                page.wait_for_function("()=>window.__subsea.scene3D.diagnostics().models.find(n=>n.id==='host').guides===1")
                one = page.evaluate("window.__subsea.scene3D.diagnostics().models.find(n=>n.id==='host')")
                self.assertEqual(len({tuple(p["deck"]) for p in one["attachments"]}), 1)
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_every_catalogue_equipment_has_3d_details(self):
        with tempfile.TemporaryDirectory(prefix="subsea-3d-catalog-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                path = Path(directory) / "models.html"
                path.write_text(build_html({"freeform": True, "animate": False, "showLegend": False, "chain": []}), encoding="utf-8")
                page.goto(path.as_uri())
                page.wait_for_function("()=>!!window.__subsea")
                missing = page.evaluate("ids=>ids.filter(id=>!window.Subsea3D.families[id])", [e["id"] for e in CATALOG])
                self.assertFalse(missing, missing)
                page.click("#b_3d")
                page.wait_for_function("()=>window.__subsea.scene3D?.diagnostics().drawCalls>0 || document.querySelector('#scene3d-error').textContent", timeout=30000)
                self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                for start in range(0, len(CATALOG), 8):
                    entries = CATALOG[start:start + 8]
                    spec = {"freeform": True, "showLegend": False, "animate": False, "chain": [
                        {"id": e["id"], "type": e["id"], "x": i % 4 * 350, "y": i // 4 * 350}
                        for i, e in enumerate(entries)]}
                    page.evaluate("s=>window.__subsea.replaceSpec(s)", spec)
                    page.wait_for_function("ids=>JSON.stringify(window.__subsea.scene3D.diagnostics().models.map(n=>n.id).sort())===JSON.stringify(ids.sort())", arg=[e["id"] for e in entries])
                    self.assertEqual(page.locator("#scene3d-error").text_content(), "")
                    self.assertTrue(all(n["parts"] > 1 for n in page.evaluate("window.__subsea.scene3D.diagnostics().models")))
                    for model in page.evaluate("window.__subsea.scene3D.diagnostics().models"):
                        if model["family"] in ("tree", "valve", "pump", "vessel", "cooler", "control", "pig", "instrument") or model["family"] == "frame" and model["type"] != "plem":
                            self.assertGreater(model["roofPanels"], 0, model["type"])
                            self.assertTrue(all(r > b and g > b for r, g, b in model["roofColors"]), model["type"])
                        elif model["family"] == "pipe":
                            self.assertEqual(model["roofPanels"], 0, model["type"])
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_unsupported_graphics_and_cancelled_switch(self):
        with tempfile.TemporaryDirectory(prefix="subsea-3d-errors-") as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_executable(), args=["--enable-unsafe-swiftshader"])
            try:
                path = Path(directory) / "errors.html"
                path.write_text(build_html(design()), encoding="utf-8")
                page = browser.new_page()
                page.add_init_script("""const original = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
                        return kind === 'webgl2' ? null : original.call(this, kind, ...args);
                    };""")
                page.goto(path.as_uri())
                before = page.evaluate("window.__subsea.spec")
                page.click("#b_3d")
                expect(page.locator("#scene3d-error")).to_contain_text("3D unavailable", timeout=30000)
                self.assertEqual(page.evaluate("window.__subsea.spec"), before)
                page.click("#b_2d")
                expect(page.locator("#svg")).to_be_visible()
                page.close()
                page = browser.new_page()
                page.goto(path.as_uri())
                page.evaluate("()=>{document.querySelector('#b_3d').click();document.querySelector('#b_2d').click()}")
                page.wait_for_function("()=>!!window.__subsea.scene3D", timeout=30000)
                self.assertFalse(page.evaluate("window.__subsea.scene3D.diagnostics().active"))
                expect(page.locator("#scene3d")).to_be_hidden()
                expect(page.locator("#svg")).to_be_visible()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
