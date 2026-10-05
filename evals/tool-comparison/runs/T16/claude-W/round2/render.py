import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width":816,"height":1344}, device_scale_factor=1275/816)
    pg.goto("file:///home/user/Vixl/evals/tool-comparison/runs/T16/claude-W/round2/menu.html")
    pg.wait_for_timeout(300)
    info = pg.evaluate("""() => {
      const dots = [...document.querySelectorAll('.price')].map(e => {
        const r = document.createRange(); const t = e.firstChild; const i = t.data.indexOf('.');
        r.setStart(t,i); r.setEnd(t,i+1); const b = r.getBoundingClientRect(); return +(b.left).toFixed(2); });
      const m = document.getElementById('main'); const s=[...m.children].pop().getBoundingClientRect();
      const fonts = new Set([...document.querySelectorAll('*')].map(e=>getComputedStyle(e).fontSize));
      return {dots:[...new Set(dots)], overflow: m.scrollHeight > m.clientHeight, docH: document.documentElement.scrollHeight, fonts:[...fonts]};
    }""")
    print(json.dumps(info))
    pg.screenshot(path="menu-preview.png", clip={"x":0,"y":0,"width":816,"height":1344})
    pg.pdf(path="menu.pdf", width="8.5in", height="14in", print_background=True, margin={"top":"0","bottom":"0","left":"0","right":"0"})
    b.close()
