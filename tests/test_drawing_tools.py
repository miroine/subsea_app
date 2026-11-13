"""Drawing tools browser regressions: python tests\\test_drawing_tools.py."""
import copy
import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, screen_port
from subsea.html import build_html
from subsea.presets import get_preset
from subsea.riser_detail import illustrated_riser_configuration
from subsea.spec import validate


def line_point(page, fraction=0.5):
    return page.locator("#connection-line-0").evaluate(
        """(line, fraction) => {
          const p = line.getPointAtLength(line.getTotalLength() * fraction).matrixTransform(line.getScreenCTM());
          return {x:p.x, y:p.y};
        }""", fraction
    )


def drag(page, start, dx, dy):
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(start["x"] + dx, start["y"] + dy, steps=10)
    page.mouse.up()


def test_layout_preserves_connected_geometry(page):
    drawing = {
        "freeform": True, "showLegend": False, "animate": False,
        "chain": [{"id": "left", "type": "plem", "x": 250, "y": 180},
                  {"id": "detail", "type": "custom_element", "x": 550, "y": 330,
                   "provider": "Custom provider", **illustrated_riser_configuration()},
                  {"id": "right", "type": "plet", "x": 1000, "y": 180},
                  {"id": "loose", "type": "mpfm", "x": 300, "y": 200}],
        "connections": [
            {"from": "left", "fromPort": "P-right", "to": "detail", "toPort": "P-left", "lane": "P"},
            {"from": "detail", "fromPort": "P-right", "to": "right", "toPort": "P-left", "lane": "P"},
        ],
        "zones": [{"placement": "anchored", "from": "left", "to": "right",
                   "yOffset": -20, "bottomOffset": 30, "label": "LC1"}],
    }
    page.evaluate("s=>window.__subsea.replaceSpec(s)", drawing)
    # Start with deliberately orthogonal routes, including a loop below the equipment.
    page.evaluate("""()=>{
      const s=structuredClone(window.__subsea.spec);
      const port=(id,p)=>{
        const el=document.querySelector(`.el[data-id="${id}"]`), marker=el.querySelector(`[data-port="${p}"]`);
        const q=el.ownerSVGElement.createSVGPoint();q.x=+marker.dataset.x;q.y=+marker.dataset.y;
        const at=q.matrixTransform(el.ownerSVGElement.getScreenCTM().inverse().multiply(el.getScreenCTM()));
        return {x:at.x,y:at.y};
      };
      s.connections.forEach((c,i)=>{
        const a=port(c.from,c.fromPort),b=port(c.to,c.toPort),x=(a.x+b.x)/2;
        c.waypoints=i===0?[{x,y:a.y},{x,y:b.y}]:
          [{x:a.x+35,y:a.y},{x:a.x+35,y:650},{x:b.x-35,y:650},{x:b.x-35,y:b.y}];
      });window.__subsea.replaceSpec(s);
    }""")
    geometry = lambda: page.locator(".connection").evaluate_all("""groups=>groups.map(g=>{
        const path=g.querySelector('[id^="connection-line-"]'), transform=path.ownerSVGElement.getScreenCTM().inverse().multiply(path.getScreenCTM());
        return Array.from({length:21},(_,i)=>{
          const p=path.getPointAtLength(path.getTotalLength()*i/20).matrixTransform(transform);
          return {x:p.x,y:p.y};
        });
    })""")
    before = geometry()
    zone_before = page.locator(".zone-span").evaluate("e=>({x:+e.getAttribute('x1'),y:+e.getAttribute('y1'),end:+e.getAttribute('x2')})")
    original = page.evaluate("structuredClone(window.__subsea.spec)")
    page.click("#b_layout")
    after = geometry()
    dx, dy = after[0][0]["x"] - before[0][0]["x"], after[0][0]["y"] - before[0][0]["y"]
    zone_after = page.locator(".zone-span").evaluate("e=>({x:+e.getAttribute('x1'),y:+e.getAttribute('y1'),end:+e.getAttribute('x2')})")
    assert abs(zone_after["x"] - zone_before["x"] - dx) < .02
    assert abs(zone_after["y"] - zone_before["y"] - dy) < .02
    assert abs(zone_after["end"] - zone_before["end"] - dx) < .02, "Anchored zone span was deformed"
    for old_route, new_route in zip(before, after):
        for old, new in zip(old_route, new_route):
            assert abs(new["x"] - old["x"] - dx) < .02 and abs(new["y"] - old["y"] - dy) < .02, "Best layout deformed connected piping"
    updated = page.evaluate("structuredClone(window.__subsea.spec)")
    assert validate(updated) == []
    assert updated["chain"] == original["chain"], "Equipment internals/metadata changed during layout"
    for old, new in zip(original["connections"], updated["connections"]):
        for a, b in zip(old["waypoints"], new["waypoints"]):
            assert abs(b["x"] - a["x"] - dx) < .02 and abs(b["y"] - a["y"] - dy) < .02
    page.click("#b_layout")
    assert page.evaluate("window.__subsea.spec") == updated, "Repeated layout drifted or reshaped the drawing"
    page.evaluate("s=>window.__subsea.replaceSpec(JSON.parse(JSON.stringify(s)))", updated)
    for saved_route, loaded_route in zip(after, geometry()):
        assert all(abs(a[axis] - b[axis]) < .02 for a, b in zip(saved_route, loaded_route)
                   for axis in ("x", "y")), "Saved layout geometry did not survive JSON reload"
    page.click("#b_undo_layout")
    assert page.evaluate("window.__subsea.spec") == original, "Layout undo failed after repeated layout"
    # A positioned annotation binds the composition: fit it without moving its contents.
    original["zones"] = [{"placement": "free", "leftOffset": 200, "rightOffset": 1200,
                          "yOffset": 50, "bottomOffset": 700, "label": "LC1", "distanceM": 2500}]
    page.evaluate("s=>window.__subsea.replaceSpec(s)", original)
    annotated = page.evaluate("structuredClone(window.__subsea.spec)")
    page.click("#b_layout")
    assert page.evaluate("window.__subsea.spec") == annotated, "Free annotation lost its alignment with equipment"
    hidden = copy.deepcopy(original)
    hidden.pop("zones")
    hidden.setdefault("overrides", {})["detail"] = {"hidden": True}
    page.evaluate("s=>window.__subsea.replaceSpec(s)", hidden)
    hidden = page.evaluate("structuredClone(window.__subsea.spec)")
    page.click("#b_layout")
    assert page.evaluate("window.__subsea.spec") == hidden, "Hidden connections were stretched by layout"
    assert "Automatic spacing skipped" in page.locator("#connect-status").text_content()
    print("PASS: best layout preserves connected piping, custom internals and free zones; repeat and undo are safe")


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-tools-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        spec = {
            "freeform": True, "host": None, "showLegend": False, "animate": True,
            "flow": "forward", "connectionWidth": 4,
            "chain": [
                {"id": "a", "type": "plem", "x": 100, "y": 120},
                {"id": "b", "type": "plet", "x": 500, "y": 260},
                {"id": "c", "type": "riser_skid", "x": 180, "y": 400},
                {"id": "h", "type": "fpso", "x": 50, "y": -80},
                {"id": "pipe", "type": "pipeline_rigid", "x": 550, "y": 400, "w": 180},
            ],
            "connections": [{"from": "a", "to": "b", "fromPort": "P-right", "toPort": "P-left", "lane": "P", "connectionType": "gas"}],
            "seaLevel": {"visible": True, "host": "h", "offset": 20},
        }
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        test_layout_preserves_connected_geometry(page)
        page.evaluate("s=>window.__subsea.replaceSpec(s)", spec)
        page.click("#b_fit")
        source, target = ("a", "P-right"), ("b", "P-left")
        assert page.locator("#connection-line-0").get_attribute("stroke-width") == "4"
        flow = page.locator(".connection-flow")
        assert flow.is_visible()
        before = flow.evaluate("e => getComputedStyle(e).strokeDashoffset")
        page.wait_for_function(
            "(previous) => getComputedStyle(document.querySelector('.connection-flow')).strokeDashoffset !== previous",
            arg=before, timeout=5000,
        )
        after = flow.evaluate("e => getComputedStyle(e).strokeDashoffset")
        assert before != after, (before, after)
        assert page.locator(".flow-arrow").count() == 1
        point = line_point(page)
        page.mouse.click(point["x"], point["y"])
        page.fill("#i_connection_width", "7")
        page.locator("#i_connection_width").press("Tab")
        assert page.locator("#connection-line-0").get_attribute("stroke-width") == "7"
        page.select_option("#i_connection_flow", "reverse")
        assert "rev" in flow.get_attribute("class")
        page.select_option("#i_connection_flow", "none")
        assert flow.count() == 0 and page.locator(".flow-arrow").count() == 0
        page.select_option("#i_connection_flow", "forward")
        page.click("#b_flow")
        assert not flow.is_visible()
        page.click("#b_flow")
        assert flow.is_visible()
        print("PASS: actual flow animation, reverse/none/toggle, arrows and connection thickness")

        page.click("#i_add_bend")
        bend = page.locator(".route-bend").bounding_box()
        drag(page, {"x": bend["x"] + bend["width"] / 2, "y": bend["y"] + bend["height"] / 2}, 45, -35)
        points = page.evaluate("window.__subsea.spec.connections[0].waypoints")
        assert len(points) == 1
        assert_attached(page, source, target)
        old = copy.deepcopy(points)
        point = line_point(page, 0.3)
        drag(page, point, 25, 30)
        points = page.evaluate("window.__subsea.spec.connections[0].waypoints")
        assert points != old, (points, old)
        assert_attached(page, source, target)
        point = line_point(page, 0.65)
        page.mouse.dblclick(point["x"], point["y"], delay=100)
        assert page.locator(".route-bend").count() == 2
        page.locator(".route-bend").last.dblclick(force=True)
        assert page.locator(".route-bend").count() == 1
        end = page.locator('.route-end[data-end="to"]').bounding_box()
        dest = screen_port(page, "c", "P-left")
        start = {"x": end["x"] + end["width"] / 2, "y": end["y"] + end["height"] / 2}
        drag(page, start, dest["x"] - start["x"], dest["y"] - start["y"])
        assert page.evaluate("window.__subsea.spec.connections[0].to") == "c"
        target = ("c", "P-left")
        assert_attached(page, source, target)
        saved = page.evaluate("window.__subsea.spec")
        points = saved["connections"][0]["waypoints"]
        assert validate(saved) == []
        html.write_text(build_html(saved), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert page.evaluate("window.__subsea.spec.connections[0].waypoints") == points
        assert_attached(page, source, target)
        print("PASS: drag bends and route, double-click add/remove, endpoint reassignment, route reload")

        # Multi-select and drag both endpoints as a rigid block.
        page.locator('[data-id="a"] .hit').click(force=True, position={"x": 3, "y": 3})
        page.locator('[data-id="c"] .hit').click(force=True, modifiers=["Shift"], position={"x": 3, "y": 3})
        assert page.evaluate("window.__subsea.getSelectedIds().sort()") == ["a", "c"]
        before = {item: screen_port(page, item, "P-left") for item in ("a", "b", "c")}
        waypoints = page.evaluate("window.__subsea.spec.connections[0].waypoints")
        hit = page.locator('[data-id="a"] .hit').bounding_box()
        drag(page, {"x": hit["x"] + 4, "y": hit["y"] + 4}, 40, 35)
        after = {item: screen_port(page, item, "P-left") for item in ("a", "b", "c")}
        for axis in ("x", "y"):
            assert abs((after["a"][axis] - before["a"][axis]) - (after["c"][axis] - before["c"][axis])) < .1
            assert abs(after["b"][axis] - before["b"][axis]) < .1
        assert page.evaluate("window.__subsea.spec.connections[0].waypoints") != waypoints
        assert_attached(page, source, target)
        print("PASS: multi-select rigid block movement, unselected neighbour fixed, manual route follows")

        page.locator('[data-id="h"] .hit').click(force=True, position={"x": 3, "y": 3})
        sea_before = float(page.locator("#sea-level line").get_attribute("y1"))
        hit = page.locator('[data-id="h"] .hit').bounding_box()
        drag(page, {"x": hit["x"] + 4, "y": hit["y"] + 4}, 0, 40)
        sea_after = float(page.locator("#sea-level line").get_attribute("y1"))
        assert sea_after > sea_before
        page.evaluate("""() => {
          const next = structuredClone(window.__subsea.spec);
          next.seaLevel.offset += 30;
          window.__subsea.replaceSpec(next);
        }""")
        assert abs(float(page.locator("#sea-level line").get_attribute("y1")) - sea_after - 30) < .1
        print("PASS: sea level follows host movement and configurable offset")

        page.locator('[data-id="pipe"] .hit').click(force=True, position={"x": 3, "y": 3})
        page.fill("#i_line_width", "6")
        page.locator("#i_line_width").press("Tab")
        assert page.evaluate("window.__subsea.spec.chain.find(i => i.id === 'pipe').lineWidth") == 6
        original = page.evaluate("window.__subsea.spec")
        page.click("#b_layout")
        boxes = page.locator("#content .el").evaluate_all(
            "items => items.map(e => {const r=e.getBoundingClientRect(); return {id:e.dataset.id,x:r.x,y:r.y,w:r.width,h:r.height};})"
        )
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]) > .1 and min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) > .1
                assert not overlap, (a, b)
        assert_attached(page, source, target)
        page.click("#b_undo_layout")
        assert page.evaluate("window.__subsea.spec") == original
        page.click("#b_layout")
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg = Path(directory) / "drawing.svg"
        downloaded.value.save_as(svg)
        text = svg.read_text(encoding="utf-8")
        assert 'class="route-handle' not in text and 'class="connection-hit"' not in text
        assert 'id="sea-level"' in text and 'stroke-width="7"' in text
        with page.expect_download() as downloaded:
            page.click("#b_json")
        saved_file = Path(directory) / "drawing.json"
        downloaded.value.save_as(saved_file)
        assert validate(json.loads(saved_file.read_text(encoding="utf-8"))) == []
        print("PASS: flowline width, non-overlapping best layout, safe undo and SVG/JSON export")

        # Missing or explicitly removed hosts must never be replaced with a jacket.
        for freeform in (False, True):
            for host_value in ("missing", None):
                hostless = {"freeform": freeform, "chain": [{"id": "a", "type": "plet"}]}
                if host_value is None:
                    hostless["host"] = None
                html.write_text(build_html(hostless), encoding="utf-8")
                page.goto(html.as_uri())
                page.wait_for_function("() => !!window.__subsea")
                assert page.locator('.el[data-type="jacket"]').count() == 0
        preset = get_preset("Two-template tieback to platform")
        html.write_text(build_html(preset), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        # A preset riser can be selected and upgraded to an editable attached route.
        riser = page.locator("[data-riser-host]").first
        route_point = riser.locator("path").first.evaluate(
            """line => {
              for (let i=1;i<100;i++) {
                const p = line.getPointAtLength(line.getTotalLength() * i / 100).matrixTransform(line.getScreenCTM());
                if (document.elementFromPoint(p.x,p.y)?.closest('[data-riser-host]')) return {x:p.x,y:p.y};
              }
              throw new Error('No accessible point on legacy riser');
            }"""
        )
        page.mouse.click(route_point["x"], route_point["y"])
        assert page.locator(".connection").count() == 1
        converted = page.evaluate("window.__subsea.spec.connections[0]")
        assert converted["kind"] == "riser" and converted["fromPort"].startswith("J-")
        assert_attached(page, (converted["from"], converted["fromPort"]), (converted["to"], converted["toPort"]))
        page.click("#i_add_bend")
        assert page.locator(".route-bend").count() == 1
        items = page.evaluate("window.__subsea.spec.chain")
        page.click("#b_layout")
        assert page.evaluate("window.__subsea.spec.chain") == items
        assert page.locator(".train").count() == 1
        print("PASS: hostless designs stay hostless; preset risers editable; layout preserves inline train contents")
        network = copy.deepcopy(spec)
        network["freeform"] = False
        network["branches"] = [{
            "chain": [{"id": "branch1", "type": "plem"}],
            "from": {"item": "b", "side": "down"}, "dy": 120,
        }, {
            "chain": [{"id": "branch2", "type": "plet"}],
            "from": {"item": "branch1", "side": "down"}, "dy": 100,
            "mirror": True,
        }]
        html.write_text(build_html(network), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        page.click("#b_layout")
        train_boxes = page.locator(".train").evaluate_all(
            "items => items.map(e=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};})"
        )
        for i, a in enumerate(train_boxes):
            for b in train_boxes[i + 1:]:
                assert a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"] or a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"], (a, b)
        print("PASS: dependent/mirrored preset trains auto-space without overlaps")
        page.locator('[data-id="a"] .hit').click(force=True, position={"x": 3, "y": 3})
        page.locator('[data-id="branch2"] .hit').click(force=True, modifiers=["Shift"], position={"x": 3, "y": 3})
        before = {item: screen_port(page, item, "P-left") for item in ("a", "branch2")}
        hit = page.locator('[data-id="a"] .hit').bounding_box()
        drag(page, {"x": hit["x"] + 4, "y": hit["y"] + 4}, 35, 25)
        after = {item: screen_port(page, item, "P-left") for item in ("a", "branch2")}
        for axis in ("x", "y"):
            assert abs((after["a"][axis] - before["a"][axis]) - (after["branch2"][axis] - before["branch2"][axis])) < .1
        page.wait_for_function("() => document.querySelector('#b_undo_layout').disabled")
        print("PASS: block movement across mirrored trains; layout undo disabled after further edits")
        for change in ({"connectionWidth": 0}, {"connectionWidth": True},
                       {"seaLevel": {"offset": float("inf")}},
                       {"connections": [{"width": 21}]},
                       {"connections": [{"flow": "invalid"}]},
                       {"connections": [{"waypoints": [{"x": 1, "y": float("nan")}]}]}):
            assert validate({**spec, **change}), change
        print("PASS: invalid thickness, flow and route/sea-level coordinates rejected")
        for from_host in (True, False):
            automatic = copy.deepcopy(spec)
            automatic["flow"] = "auto"
            automatic["connections"] = [{
                "from": "h" if from_host else "a", "to": "a" if from_host else "h",
                "fromPort": "J-0" if from_host else "P-left",
                "toPort": "P-left" if from_host else "J-0", "lane": "P", "kind": "riser",
            }]
            html.write_text(build_html(automatic), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            assert ("rev" in page.locator(".connection-flow").get_attribute("class").split()) == from_host
        print("PASS: automatic production flow points toward host regardless of drag direction")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    run()
