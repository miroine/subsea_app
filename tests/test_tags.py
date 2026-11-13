"""Tags drawn by the JS engine must equal the Python equipment list."""
import sys, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from subsea.html import build_html
from subsea.presets import PRESETS
from subsea.bom import equipment_list
SENS = {"PT", "TT", "SD"}
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for name, spec in PRESETS.items():
        f = pathlib.Path("/tmp/out3/t.html"); f.write_text(build_html(spec)); pg = b.new_page(); pg.goto(f"file://{f}"); pg.wait_for_timeout(300)
        drawn = set(pg.evaluate("[...document.querySelectorAll('#content text')].map(t=>t.textContent.trim()).filter(t=>/^[A-Z]{1,3}-\\d{3}$/.test(t))"))
        py = {t for t in equipment_list(spec)["Tag"] if t and t.split("-")[0] not in SENS}
        if drawn != py: bad += 1; print("MISMATCH", name, "js-only", drawn - py, "py-only", py - drawn)
        pg.close()
    b.close()
print("FAIL" if bad else "OK – JS and Python tags agree on all presets")
sys.exit(bad)
