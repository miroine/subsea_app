"""Render presets / catalogue to PNG with headless Chrome and report JS errors.
usage: python3 -I tests/render.py OUTDIR
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from subsea.html import build_html
from subsea.presets import PRESETS
from subsea.catalog import CATALOG

out = pathlib.Path(sys.argv[1]); out.mkdir(exist_ok=True)
import copy
jobs = [(f"preset{i}", build_html(s), (1400, 860)) for i, s in enumerate(PRESETS.values())]
first = next(iter(PRESETS.values()))
for th in ("mono", "blueprint", "classic"):
    sp = copy.deepcopy(first); sp["themeName"] = th; jobs.append((f"theme_{th}", build_html(sp), (1400, 860)))
jobs.append(("catalog", build_html(None, "catalog"), (1500, 1800)))
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for name, html, (w, h) in jobs:
        f = out / f"{name}.html"; f.write_text(html, encoding="utf-8")
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e, n=name: errs.append((n, str(e))))
        pg.on("console", lambda m, n=name: errs.append((n, m.text)) if m.type == "error" and "fonts.g" not in m.text and "ERR_" not in m.text else None)
        pg.goto(f"file://{f}"); pg.wait_for_timeout(500)
        pg.screenshot(path=str(out / f"{name}.png"))
        pg.close()
    b.close()
print("errors:", errs or "none")
