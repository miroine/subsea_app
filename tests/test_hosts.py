"""Host library browser regressions. Run: python tests\\test_hosts.py."""
import json
from pathlib import Path
import tempfile

from test_connections import browser_executable, component_width, drag_ports, assert_attached
from playwright.sync_api import sync_playwright

from subsea.catalog import HOST_IDS
from subsea.html import build_html
from subsea.presets import get_preset
from subsea.spec import chain_to_df, df_to_chain, validate


def assert_risers_attached(page):
    errors = page.locator("[data-riser-host]").evaluate_all("""risers => risers.map(riser => {
      const host = [...document.querySelectorAll('.host.el')]
        .find(host => host.dataset.id === riser.dataset.riserHost);
      const point = host.ownerSVGElement.createSVGPoint();
      point.x = +riser.dataset.ax; point.y = +riser.dataset.ay;
      const expected = point.matrixTransform(host.getScreenCTM());
      const path = riser.querySelector('path');
      const actual = path.getPointAtLength(0).matrixTransform(path.getScreenCTM());
      return Math.hypot(expected.x - actual.x, expected.y - actual.y);
    })""")
    assert errors and max(errors) < 0.1, errors


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-hosts-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "hosts.html"
        for preset in ("Blank canvas – draw your own", "Two-template tieback to platform"):
            html.write_text(build_html(get_preset(preset)), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            for host_type in HOST_IDS:
                page.click("#b_palette")
                page.select_option("#palette-category", "Hosts & topsides")
                assert page.locator(".palette-item").count() == len(HOST_IDS)
                page.click(f'.palette-item[data-type="{host_type}"]')
                page.click("#palette-close")
                bounds = page.locator("#svg").bounding_box()
                page.mouse.click(bounds["x"] + bounds["width"] * 0.45,
                                 bounds["y"] + bounds["height"] * 0.65)
                host_id = page.evaluate("window.__subsea.sel")
                assert page.locator(f'.el[data-id="{host_id}"]').get_attribute("data-type") == host_type
                width = component_width(page, host_id)
                page.locator("#i_scale").fill("125")
                page.locator("#i_scale").press("Tab")
                assert page.locator(f'.el[data-id="{host_id}"]').evaluate(
                    "element => element.transform.baseVal.consolidate().matrix.a"
                ) == 1.25
                assert abs(component_width(page, host_id) / width - 1.25) < 0.015, (
                    preset, host_type, host_id, width, component_width(page, host_id),
                    page.evaluate("window.__subsea.spec.overrides"),
                )
                page.click("#i_copy")
                copy_id = page.evaluate("window.__subsea.sel")
                assert copy_id != host_id
                assert abs(component_width(page, copy_id) - component_width(page, host_id)) < 0.001
                page.click("#i_delete")
                assert page.locator(f'.el[data-id="{copy_id}"]').count() == 0
                page.locator(f'.el[data-id="{host_id}"] .hit').click(force=True)
                page.click("#i_delete")
            print(f"PASS: all {len(HOST_IDS)} host types placed, resized, copied, deleted on {preset}")
            page.click("#b_palette")
            page.locator('.palette-item[data-type="fpso"]').drag_to(
                page.locator("#svg"), target_position={"x": 650, "y": 550}
            )
            page.click("#palette-close")
            dropped_id = page.evaluate("window.__subsea.sel")
            assert page.locator(f'.el[data-id="{dropped_id}"]').get_attribute("data-type") == "fpso"
            page.locator("#i_scale").fill("80")
            page.locator("#i_scale").press("Tab")
            host = page.locator(f'.el[data-id="{dropped_id}"]')
            before = host.bounding_box()
            page.mouse.move(before["x"] + 4, before["y"] + 4)
            page.mouse.down()
            page.mouse.move(before["x"] + 24, before["y"] + 24, steps=8)
            page.mouse.up()
            after = host.bounding_box()
            assert abs(after["x"] - before["x"] - 20) < 2
            assert abs(after["width"] - before["width"]) < 1
            page.click("#i_delete")
            print("PASS: native host library drag/drop and movement retain component size")

        main_id = page.evaluate("window.__subsea.spec.host.id")
        page.locator(f'.host[data-id="{main_id}"] .hit').click(position={"x": 2, "y": 2}, force=True)
        assert page.evaluate("window.__subsea.sel") == main_id
        page.locator("#i_scale").fill("150")
        page.locator("#i_scale").press("Tab")
        assert_risers_attached(page)
        main = page.locator(f'.host[data-id="{main_id}"]')
        start = main.bounding_box()
        page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
        page.mouse.down()
        page.mouse.move(start["x"] + start["width"] / 2 + 20,
                        start["y"] + start["height"] / 2 + 25, steps=8)
        page.mouse.up()
        assert page.evaluate("(id) => window.__subsea.spec.overrides[id].dx", main_id) != 0
        assert_risers_attached(page)
        page.click("#i_copy")
        copy_id = page.evaluate("window.__subsea.sel")
        assert page.locator(f'.el[data-id="{copy_id}"]').count() == 1
        assert page.evaluate("(id) => window.__subsea.spec.overrides[id].scale", copy_id) == 1.5
        print("PASS: existing template host selectable, movable, resizable, copyable; risers stay attached")

        page.click("#b_connect")
        page.click("#b_fit")
        drag_ports(page, (copy_id, "J-0"), ("t1", "P-left"))
        assert page.locator(".connection").count() == 1
        assert_attached(page, (copy_id, "J-0"), ("t1", "P-left"))
        assert page.locator("#i_riser_style").input_value() == "rigid"
        assert page.locator("#i_jtube option").count() >= 2
        page.select_option("#i_jtube", "J-1")
        assert_attached(page, (copy_id, "J-1"), ("t1", "P-left"))
        page.select_option("#i_riser_style", "flex")
        assert page.locator('.connection path:not(.connection-hit)').get_attribute("stroke-dasharray") == "10 3"
        assert_attached(page, (copy_id, "J-1"), ("t1", "P-left"))
        page.select_option("#i_jtube", "J-0")
        page.select_option("#i_riser_style", "rigid")
        assert_attached(page, (copy_id, "J-0"), ("t1", "P-left"))
        page.select_option("#i_riser_style", "flex")
        print("PASS: named J-tube selection and rigid/flexible riser routing")
        page.click("#b_connect")
        with page.expect_download() as downloaded:
            page.click("#b_json")
        saved = Path(directory) / "hosts.json"
        downloaded.value.save_as(saved)
        spec = json.loads(saved.read_text(encoding="utf-8"))
        assert validate(spec) == [], validate(spec)
        chain, problems = df_to_chain(chain_to_df(spec["chain"]))
        assert not problems and chain == spec["chain"], problems
        html.write_text(build_html(spec), encoding="utf-8")
        page.reload()
        page.wait_for_function("() => !!window.__subsea")
        assert_risers_attached(page)
        assert_attached(page, (copy_id, "J-0"), ("t1", "P-left"))
        assert page.evaluate("window.__subsea.spec.connections[0].style") == "flex"
        with page.expect_download() as downloaded:
            page.click("#b_svg")
        svg_export = Path(directory) / "risers.svg"
        downloaded.value.save_as(svg_export)
        exported = browser.new_page()
        exported.goto(svg_export.as_uri())
        assert exported.locator(".j-tube-port").count() == 0
        assert exported.locator('.connection path').get_attribute("stroke-dasharray") == "10 3"
        assert exported.locator('.connection path').get_attribute("fill") == "none"
        exported.close()
        page.locator(f'.el[data-id="{copy_id}"] .hit').click(force=True)
        page.locator("#i_scale").fill("120")
        page.locator("#i_scale").press("Tab")
        assert_attached(page, (copy_id, "J-0"), ("t1", "P-left"))
        print("PASS: flexible riser JSON/SVG export and attachment after host resizing")
        page.click("#b_connect")
        drag_ports(page, ("t1", "P-right"), (copy_id, "J-1"))
        assert page.locator(".connection").count() == 2
        assert_attached(page, ("t1", "P-right"), (copy_id, "J-1"), index=1)
        assert page.evaluate("window.__subsea.spec.connections[1].lane") == "P"
        page.select_option("#i_riser_style", "flex")
        assert_attached(page, ("t1", "P-right"), (copy_id, "J-1"), index=1)
        page.click("#b_connect")
        print("PASS: equipment-to-J-tube riser drag works in reverse direction")
        page.locator(f'.host[data-id="{main_id}"] .hit').click(position={"x": 2, "y": 2}, force=True)
        assert page.evaluate("window.__subsea.sel") == main_id
        page.click("#i_delete")
        assert page.evaluate("window.__subsea.spec.host") is None
        assert page.locator("[data-riser-host]").count() == 0
        assert validate(page.evaluate("window.__subsea.spec")) == []
        print("PASS: host connections, JSON reload, table round-trip, and original host deletion")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    run()
