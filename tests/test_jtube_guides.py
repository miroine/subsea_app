"""Optional host guide tubes and pulled-in riser geometry."""
from pathlib import Path
import logging
import os
import tempfile

from playwright.sync_api import sync_playwright

from test_connections import assert_attached, browser_executable, drag_ports
from subsea.html import build_html
from subsea.spec import validate
from subsea.presets import get_preset


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-jtubes-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_executable())
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = Path(directory) / "drawing.html"
        for type_id in ("jacket", "platform"):
            spec = {"freeform": True, "host": None, "showLegend": False, "animate": False, "chain": [
                {"id": "h", "type": type_id, "x": 100, "y": 120, "slots": ["Gas", "Umbilical"]},
                {"id": "p", "type": "plet", "x": 700, "y": 450},
            ]}
            html.write_text(build_html(spec), encoding="utf-8")
            page.goto(html.as_uri())
            page.wait_for_function("() => !!window.__subsea")
            assert page.locator(".j-tube-guide").count() == 0
            page.locator('[data-id="h"] .hit').click(force=True, position={"x": 20, "y": 5})
            page.check("#i_show_jtubes")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator(".j-tube-guide").count() == 2
            assert page.locator('[data-id="h"]').evaluate("""host => {
                return [...host.querySelectorAll('.j-tube-bore')].every(tube => {
                    const start = tube.getPointAtLength(0), end = tube.getPointAtLength(tube.getTotalLength());
                    const vertical = tube.getPointAtLength(30);
                    return Math.abs(vertical.x - start.x) < .01 && end.x < start.x - 35
                        && end.y > start.y + 100 && !tube.getAttribute('d').includes('H');
                });
            }""")
            assert page.locator('[data-id="h"]').evaluate("""host => {
                const tubes = [...host.querySelectorAll('.j-tube-bore')];
                const startY = tubes[0].getPointAtLength(0).y;
                const endY = Math.min(...tubes.map(t => t.getPointAtLength(t.getTotalLength()).y));
                for (let y = startY + 1; y < endY; y += 2) {
                    const xs = tubes.map(tube => {
                        let low = 0, high = tube.getTotalLength();
                        for (let step = 0; step < 30; step++) {
                            const mid = (low + high) / 2;
                            if (tube.getPointAtLength(mid).y < y) low = mid; else high = mid;
                        }
                        return tube.getPointAtLength((low + high) / 2).x;
                    });
                    if (xs.some((x, i) => i && x <= xs[i-1])) return false;
                }
                return true;
            }""")
            page.locator("#insp").evaluate("e => e.style.display='none'")
            page.click("#b_connect")
            drag_ports(page, ("p", "U-left"), ("h", "J-1"))
            assert_attached(page, ("p", "U-left"), ("h", "J-1"))
            assert page.locator(".j-tube-riser").count() == 1
            guide = page.locator('.j-tube-guide[data-tube="1"]')
            assert guide.locator(".j-tube-riser").get_attribute("d") == guide.locator(".j-tube-bore").get_attribute("d")
            assert page.locator('[data-id="h"]').evaluate("""host => {
                const guide = host.querySelector('[data-tube="1"] .j-tube-riser');
                const end = guide.getPointAtLength(guide.getTotalLength());
                const port = host.querySelector('[data-port="J-1"]');
                return Math.hypot(end.x - +port.dataset.x, end.y - +port.dataset.y) < .01;
            }""")
            page.click("#b_connect")
            page.locator('[data-id="h"] .hit').click(force=True, position={"x": 20, "y": 5})
            page.fill("#i_scale", "125")
            page.locator("#i_scale").press("Tab")
            assert_attached(page, ("p", "U-left"), ("h", "J-1"))
            saved = page.evaluate("window.__subsea.spec")
            assert validate(saved) == []
            html.write_text(build_html(saved), encoding="utf-8")
            page.reload()
            page.wait_for_function("() => !!window.__subsea")
            assert_attached(page, ("p", "U-left"), ("h", "J-1"))
            assert page.locator(".j-tube-riser").count() == 1
            with page.expect_download() as downloaded:
                page.click("#b_svg")
            export = Path(directory) / "guides.svg"
            downloaded.value.save_as(export)
            assert 'class="j-tube-riser"' in export.read_text(encoding="utf-8")
            page.locator('[data-id="h"] .hit').click(force=True, position={"x": 20, "y": 5})
            page.uncheck("#i_show_jtubes")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert page.locator(".j-tube-guide").count() == 0
            assert_attached(page, ("p", "U-left"), ("h", "J-1"))
            assert page.evaluate("window.__subsea.spec.connections") == saved["connections"]
            page.check("#i_show_jtubes")
            page.select_option("#i_jtube_side", "right")
            page.locator("#insp").click(position={"x": 1, "y": 1})
            assert_attached(page, ("p", "U-left"), ("h", "J-1"))
            assert page.locator('.j-tube-bore').first.evaluate("""tube => {
                const start = tube.getPointAtLength(0), end = tube.getPointAtLength(tube.getTotalLength());
                return end.x > start.x + 35;
            }""")
        preset = get_preset("Two-template tieback to platform")
        preset["host"]["showJTubes"] = True
        html.write_text(build_html(preset), encoding="utf-8")
        page.goto(html.as_uri())
        page.wait_for_function("() => !!window.__subsea")
        assert page.locator(".j-tube-riser").count() > 0
        for count in (0, 24):
            candidate = {**spec, "chain": [{**spec["chain"][0], "showJTubes": True,
                                            "slots": [f"J{i+1}" for i in range(count)]}]}
            page.evaluate("spec => window.__subsea.replaceSpec(spec)", candidate)
            assert page.locator(".j-tube-guide").count() == count
        assert not errors, errors
        browser.close()
        from streamlit.testing.v1 import AppTest
        previous = os.environ.get("SUBSEA_CASES_PATH")
        previous_logging = logging.root.manager.disable
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state.spec = spec
            app.session_state.selected_element = "h"
            app.run()
            next(check for check in app.checkbox if check.label == "Draw J-tubes with pulled-in risers").check()
            app.run()
            assert not app.exception and not app.error
            assert app.session_state.spec["chain"][0]["showJTubes"] is True
        finally:
            logging.disable(previous_logging)
            if previous is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = previous
    print("PASS: optional J-tube walls/pulled-in risers, real attachment, scaling, reload/export and reversible toggle")


if __name__ == "__main__":
    run()
