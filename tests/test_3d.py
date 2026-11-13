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
    def test_inline_piping_follows_drag_preview_commit_and_reload(self):
        spec = {"showLegend": False, "flow": "none", "animate": False,
                "host": {"id": "host", "type": "jacket", "slots": ["Production"],
                         "risers": [{"lane": "P", "slot": 0, "style": "rigid", "psv": True}]},
                "chain": [{"id": "line", "type": "pipeline_pip", "w": 240},
                          {"id": "template", "type": "template", "wells": 2}]}
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
                            return source.nodes.filter(n=>!n.topside).every(n=>n.ports.every(p=>{
                                const actual=models.find(m=>m.id===n.id)?.ports.find(q=>q.id===p.id)?.point;
                                return actual && Math.abs(actual[0]-p.x*.08)<1e-7 && Math.abs(actual[2]-p.y*.08)<1e-7;
                            })) || document.querySelector('#scene3d-error').textContent;
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
