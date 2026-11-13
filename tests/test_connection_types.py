"""Service-type browser regressions: python tests\\test_connection_types.py."""
import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import browser_executable, drag_ports, assert_attached
from subsea.connections import CONNECTION_TYPES
from subsea.html import build_html
from subsea.spec import validate


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-services-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        spec = {
            "freeform": True, "host": None, "animate": False, "showLegend": True,
            "chain": [
                {"id": "a", "type": "plem", "x": 100, "y": 120},
                {"id": "b", "type": "template", "x": 500, "y": 180},
            ],
        }
        html = Path(directory) / "services.html"
        for theme in ("consulting", "mono", "blueprint", "classic"):
            spec["themeName"] = theme
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            page.click("#b_connect")
            source, target = ("a", "P-right"), ("b", "P-left")
            drag_ports(page, source, target)
            assert page.locator("#i_connection_type option").count() == len(CONNECTION_TYPES) + 1
            original_colour = page.locator(".connection path:not(.connection-hit)").get_attribute("stroke")
            before = page.locator("#svg").get_attribute("viewBox")
            for type_id, definition in CONNECTION_TYPES.items():
                page.select_option("#i_connection_type", type_id)
                assert page.evaluate("window.__subsea.spec.connections[0].connectionType") == type_id
                assert_attached(page, source, target)
                assert page.locator("#svg").get_attribute("viewBox") == before
                assert page.locator(".connection title").text_content() == definition["label"]
                assert definition["label"] in page.locator("#decor").text_content()
                path = page.locator(".connection path:not(.connection-hit)")
                assert path.get_attribute("stroke") == ("#111111" if theme == "mono" else definition["color"])
                if theme == "mono" and "monoDash" in definition:
                    assert (path.get_attribute("stroke-dasharray") or "") == definition["monoDash"]
                if definition.get("dash"):
                    assert path.get_attribute("stroke-dasharray") == definition["dash"]
            page.select_option("#i_connection_type", "")
            assert page.evaluate("window.__subsea.spec.connections[0].connectionType") is None
            assert page.locator(".connection path:not(.connection-hit)").get_attribute("stroke") == original_colour
            assert_attached(page, source, target)
            page.select_option("#i_connection_type", "umbilical_dynamic")
            page.fill("#i_connection_label", "Dynamic controls cable")
            page.locator("#i_connection_label").press("Tab")
            assert page.locator(".connection text").text_content() == "Dynamic controls cable"
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            svg = Path(directory) / f"{theme}.svg"
            downloaded.value.save_as(svg)
            exported = browser.new_page()
            exported.goto(svg.as_uri())
            assert exported.locator(".connection path").get_attribute("stroke-dasharray") == "5 3 1 3"
            assert exported.locator(".connection path").get_attribute("fill") == "none"
            assert exported.locator(".connection text").text_content() == "Dynamic controls cable"
            exported.close()
            with page.expect_download() as downloaded:
                page.click("#b_json")
            saved = Path(directory) / "services.json"
            downloaded.value.save_as(saved)
            restored = json.loads(saved.read_text(encoding="utf-8"))
            assert validate(restored) == []
            html.write_text(build_html(restored), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert page.locator(".connection path:not(.connection-hit)").get_attribute("stroke-dasharray") == "5 3 1 3"
            assert_attached(page, source, target)
            print(f"PASS: all service types, legend, label, SVG/JSON reload, unchanged ports/zoom ({theme})")
        restored["connections"][0]["connectionType"] = "invalid"
        assert any("unknown connection type" in problem for problem in validate(restored))
        assert not errors, errors
        assert CONNECTION_TYPES["gas"]["color"] == "#D32F2F"
        assert CONNECTION_TYPES["oil"]["color"] == "#00843D"
        assert CONNECTION_TYPES["water_injection"]["color"] == "#0077CC"
        browser.close()


if __name__ == "__main__":
    run()
