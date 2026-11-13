import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from subsea.html import build_html
from subsea.presets import PRESETS
f = pathlib.Path('/tmp/out2/i.html'); f.write_text(build_html(list(PRESETS.values())[0]))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 1400, 'height': 760}, accept_downloads=True); pg = ctx.new_page()
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(f'file://{f}'); pg.wait_for_timeout(400)
    # hover tooltip
    box = pg.locator('[data-id="plem"]').bounding_box(); pg.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
    pg.wait_for_timeout(100); print('tooltip:', pg.inner_text('#tip')[:60].replace('\n',' | '))
    # click -> inspector, rename label
    pg.mouse.click(box['x']+box['width']/2, box['y']+box['height']/2); print('inspector visible:', pg.is_visible('#insp'))
    pg.fill('#i_lab', 'PLEM-1'); pg.dispatch_event('#i_lab', 'change'); pg.wait_for_timeout(100)
    print('renamed:', 'PLEM-1' in pg.inner_html('#svg'))
    # drag template 1 down 40px
    t = pg.locator('[data-id="t1"]').bounding_box(); x, y = t['x']+t['width']/2, t['y']+t['height']/2
    pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x, y+40, steps=5); pg.mouse.up(); pg.wait_for_timeout(100)
    print('override after drag:', pg.evaluate('JSON.stringify(window.__subsea.spec.overrides.t1)'))
    # zoom + fit
    vb0 = pg.get_attribute('#svg', 'viewBox'); pg.mouse.wheel(0, -300); pg.wait_for_timeout(100)
    print('zoom changed viewBox:', vb0 != pg.get_attribute('#svg', 'viewBox')); pg.click('#b_fit')
    # exports
    for bid, ext in (('#b_svg','svg'), ('#b_json','json'), ('#b_png','png')):
        with pg.expect_download() as d: pg.click(bid)
        path = f'/tmp/out2/export.{ext}'; d.value.save_as(path); print(ext, pathlib.Path(path).stat().st_size, 'bytes')
    j = json.load(open('/tmp/out2/export.json')); print('json overrides keys:', list(j['overrides']))
    print('hit rects in svg export:', open('/tmp/out2/export.svg').read().count('class="hit"'))
    pg.screenshot(path='/tmp/out2/interact.png'); print('errors:', errs or 'none')
