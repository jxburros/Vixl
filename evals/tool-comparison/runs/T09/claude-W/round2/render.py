# Renders each size from campaign.html with headless Chromium (Playwright).
import pathlib
from playwright.sync_api import sync_playwright
here=pathlib.Path(__file__).resolve().parent
sizes={"instagram-square":(1080,1080),"instagram-story":(1080,1920),"x-post":(1600,900),
       "facebook-event":(1920,1005),"leaderboard":(728,90),"email-header":(600,200)}
with sync_playwright() as p:
    b=p.chromium.launch()
    for name,(w,h) in sizes.items():
        pg=b.new_page(viewport={"width":w,"height":h},device_scale_factor=1)
        pg.goto((here/"campaign.html").as_uri()+"#"+name)
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.fonts.check('800 40px Fraunces') && document.fonts.check('500 20px \"DM Sans\"')")
        # overflow check: text box inside canvas
        box=pg.evaluate("""()=>{const t=document.querySelector('.txt');const r=t.getBoundingClientRect();
          let maxR=0,maxB=0,minT=1e9;t.querySelectorAll('*').forEach(e=>{const q=e.getBoundingClientRect();maxR=Math.max(maxR,q.right);maxB=Math.max(maxB,q.bottom);minT=Math.min(minT,q.top)});return [minT,maxR,maxB]}""")
        print(name,w,h,"text top/right/bottom:",[round(v) for v in box])
        pg.locator(f"#{name}").screenshot(path=str(here/f"{name}.png"))
        pg.close()
    b.close()
