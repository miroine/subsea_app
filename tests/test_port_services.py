"""Per-port services, host capacity and concept examples: python tests\\test_port_services.py."""
import copy
import json
import re
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, drag_ports
from subsea.bom import equipment_list
from subsea.equipment import customization_errors, removed_port_errors
from subsea.html import build_html
from subsea.presets import PRESETS, get_preset
from subsea.spec import chain_to_df, df_to_chain, validate


def select_element(page, item_id):
    page.locator(f'[data-id="{item_id}"] .hit').click(force=True, position={"x": 3, "y": 3})


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-port-services-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        spec = {
            "freeform": True, "host": None, "showLegend": False, "animate": False,
            "chain": [
                {"id": "template", "type": "template", "x": 500, "y": 150, "wells": 4},
                {"id": "p1", "type": "plet", "x": 100, "y": 150},
                {"id": "p2", "type": "plet", "x": 100, "y": 350},
            ],
        }
        html.write_text(build_html(spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        page.click("#b_connect")
        drag_ports(page, ("p1", "P-right"), ("template", "P-left"))
        page.locator("#insp").evaluate("e => e.style.display='none'")
        drag_ports(page, ("template", "S-left"), ("p2", "S-right"))
        assert page.locator(".connection").count() == 2
        assert_attached(page, ("template", "S-left"), ("p2", "S-right"), 1)
        assert page.locator("#connection-line-1").get_attribute("stroke") == "#E87500"
        assert page.evaluate("window.__subsea.spec.connections[1].lane") == "S"
        page.click("#b_connect")
        select_element(page, "p2")
        page.select_option("#i_port_id", "S-right")
        page.select_option("#i_port_service", "chemical")
        page.fill("#i_port_label", "MEG inlet")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="p2"] [data-port="S-right"]').get_attribute("data-connection-type") == "chemical"
        page.select_option("#i_port_service", "gas")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_port_error").text_content()
        assert page.locator('[data-id="p2"] [data-port="S-right"]').get_attribute("data-lane") == "S"
        page.select_option("#i_port_id", "P-left")
        page.select_option("#i_port_service", "water_injection")
        assert page.locator("#i_port_compatible").input_value() == "P"
        assert page.locator("#i_port_compatible").is_disabled()
        page.locator("#insp").click(position={"x": 1, "y": 1})
        saved = page.evaluate("window.__subsea.spec")
        assert saved["chain"][2]["portOverrides"]["P-left"]["connectionType"] == "water_injection"
        assert saved["chain"][2]["portOverrides"]["S-right"]["connectionType"] == "chemical"
        assert validate(saved) == []
        chain, problems = df_to_chain(chain_to_df(saved["chain"]))
        assert not problems and chain[2]["portOverrides"] == saved["chain"][2]["portOverrides"]
        row = equipment_list(saved).query("Id == 'p2'").iloc[0]
        assert json.loads(row["Per-port fluids"]) == saved["chain"][2]["portOverrides"]
        html.write_text(build_html(saved), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_attached(page, ("template", "S-left"), ("p2", "S-right"), 1)
        assert page.locator('[data-id="p2"] [data-port="P-left"]').get_attribute("data-connection-type") == "water_injection"
        with page.expect_download() as downloaded:
            page.click("#b_json")
        json_file = Path(directory) / "ports.json"
        downloaded.value.save_as(json_file)
        assert json.loads(json_file.read_text(encoding="utf-8"))["chain"][2]["portOverrides"] == saved["chain"][2]["portOverrides"]
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg_file = Path(directory) / "ports.svg"
        downloaded.value.save_as(svg_file)
        assert "MEG inlet" in svg_file.read_text(encoding="utf-8")
        print("PASS: orange service connection attaches to second PLET; individual fluids, guard and round-trips")

        # Host count and occupied-port protection in the actual inspector.
        host_spec = {
            "host": {"id": "host", "type": "jacket", "slots": ["J1", "J2"],
                     "risers": [{"lane": "P", "slot": 0, "style": "rigid"}]},
            "chain": [{"id": "a", "type": "plet"}, {"id": "line", "type": "pipeline_rigid", "w": 250}, {"id": "b", "type": "template"}],
            "connections": [{"from": "a", "to": "b", "fromPort": "P-right", "toPort": "P-left", "lane": "P"}],
            "showLegend": False, "animate": False,
        }
        html.write_text(build_html(host_spec), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        select_element(page, "host")
        page.fill("#i_jtube_count", "8")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert page.locator('[data-id="host"] .j-tube-port').count() == 8
        assert page.evaluate("window.__subsea.spec.host.slots") == [f"J{i}" for i in range(1, 9)]
        page.fill("#i_jtube_count", "0")
        page.locator("#insp").click(position={"x": 1, "y": 1})
        assert "connected" in page.locator("#i_equipment_error").text_content()
        assert page.locator('[data-id="host"] .j-tube-port').count() == 8
        page.locator("#insp").evaluate("e => e.style.display='none'")
        legacy = page.locator("[data-riser-host]").first
        original_d = legacy.locator("path").first.get_attribute("d")
        original_width = legacy.locator("path:not(.legacy-riser-hit)").first.get_attribute("stroke-width")
        page.locator('[data-id="line"] .hit').click(force=True, position={"x": 120, "y": 3})
        page.fill("#i_line_width", "8")
        page.locator("#i_line_width").press("Tab")
        assert legacy.locator("path").first.get_attribute("d") == original_d
        assert legacy.locator("path:not(.legacy-riser-hit)").first.get_attribute("stroke-width") == original_width
        page.evaluate("""() => {
          const next = structuredClone(window.__subsea.spec);
          next.connectionWidth = 12; next.themeName = 'mono';
          window.__subsea.replaceSpec(next);
        }""")
        assert legacy.locator("path").first.get_attribute("d") == original_d
        assert legacy.locator("path:not(.legacy-riser-hit)").first.get_attribute("stroke-width") == original_width
        page.locator("#insp").evaluate("e => e.style.display='none'")
        legacy.locator("path").first.evaluate("""line => {
          for(let i=5;i<95;i++) {
            const p=line.getPointAtLength(line.getTotalLength()*i/100).matrixTransform(line.getScreenCTM());
            if(document.elementFromPoint(p.x,p.y)?.closest('[data-riser-host]')) {
              window.riserClick={x:p.x,y:p.y};return;
            }
          }
          throw new Error('No accessible riser point');
        }""")
        point = page.evaluate("window.riserClick")
        page.mouse.click(point["x"], point["y"])
        assert page.evaluate("window.__subsea.spec.connections[1].riserCurve") == "sweep"
        converted_d = page.locator("#connection-line-1").get_attribute("d")
        number = r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?"
        assert re.sub(number, "", converted_d) == re.sub(number, "", original_d)
        assert all(abs(float(a) - float(b)) < 1e-8 for a, b in zip(re.findall(number, converted_d), re.findall(number, original_d)))
        assert page.locator("#connection-line-1").get_attribute("stroke-width") == original_width
        page.fill("#i_connection_width", "5")
        page.locator("#i_connection_width").press("Tab")
        assert page.locator("#connection-line-1").get_attribute("d") == converted_d
        print("PASS: J-tube count/guard; flowline width/theme edits and riser selection preserve sweep bend")
        no_risers = {"host": {"id": "h", "type": "jacket", "slots": ["J1"]}, "chain": []}
        html.write_text(build_html(no_risers), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        select_element(page, "h")
        for count in (24, 0):
            page.fill("#i_jtube_count", str(count))
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator(".j-tube-port").count() == count
            assert validate(page.evaluate("window.__subsea.spec")) == []
        assert page.locator(".connection-port").count() == 0
        print("PASS: actual J-tube controls support full 0-24 range without phantom ports")

        for name in PRESETS:
            if not name.startswith("North Sea concept:"):
                continue
            example = get_preset(name)
            assert validate(example) == [], (name, validate(example))
            html.write_text(build_html(example), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            assert page.locator(".connection").count() == len(example["connections"]), name
            for index, connection in enumerate(example["connections"]):
                assert_attached(page, (connection["from"], connection["fromPort"]),
                                (connection["to"], connection["toPort"]), index)
            print(f"PASS: concept has valid, actually attached service routes: {name}")
        candidate = copy.deepcopy(saved["chain"][2])
        candidate["portOverrides"]["S-right"]["connectionType"] = "gas"
        assert removed_port_errors(saved, candidate)
        candidate["portOverrides"]["S-right"]["connectionType"] = "invalid"
        assert customization_errors(candidate)
        assert removed_port_errors({"connections": [{"from": "h", "fromPort": "J-3"}]},
                                   {"id": "h", "type": "jacket", "slots": ["J1"]})
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    run()
