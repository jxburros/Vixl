import asyncio
import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import time

from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import build_server


def deck():
    """Three pages with a master, notes (one with markup characters) and two transitions."""
    p = Project(960, 540, "#ffffff")
    p.apply([
        {"type": "master", "action": "add", "name": "std", "background": "#f4f4f4"},
        {"type": "text", "text": "${page} / ${pages}", "name": "num", "size": 14, "x": 880, "y": 500, "color": "#333"},
        {"type": "page", "action": "add", "name": "cover", "master": "std", "notes": "Open with the headline.\n\nThen the agenda."},
        {"type": "text", "text": "Quarterly Review", "name": "title", "size": 60, "x": 60, "y": 200, "color": "#111"},
        {"type": "page", "action": "add", "name": "results", "master": "std", "notes": "Revenue up 42% <b>& more</b>",
         "transition": "push"},
        {"type": "text", "text": "Results", "name": "title", "size": 44, "x": 60, "y": 50, "color": "#111"},
        {"type": "rich-text", "name": "body", "markdown": "Revenue grew **42%**\n- Faster *checkout*\n- New markets",
         "size": 28, "width": 500, "x": 60, "y": 140, "color": "#222"},
        {"type": "page", "action": "add", "name": "close", "master": "std", "transition": "zoom"},
        {"type": "text", "text": "Thanks", "name": "title", "size": 44, "x": 60, "y": 50, "color": "#111"},
    ])
    return p


def export(p, **options):
    report = {}
    return p.export(format="HTML", report=report, **options).decode("utf-8"), report


def slides_of(html):
    pattern = (r'<section class="slide[^"]*" id="slide-(\d+)" data-n="\d+" data-name="([^"]*)" '
               r'data-transition="([^"]*)" role="group" aria-roledescription="slide" aria-label="([^"]*)"')
    return [match.groups() for match in re.finditer(pattern, html)]


def test_three_pages_export_as_one_self_contained_presentation(tmp_path):
    p = deck()
    report = {}
    data = p.export(tmp_path / "deck.html", report=report)
    html = data.decode("utf-8")
    assert (tmp_path / "deck.html").read_bytes() == data
    assert html.startswith("<!doctype html>")
    # Nothing is fetched: no URLs, only data: pictures and in-page fragments, one inline script and style.
    assert not re.search(r"https?:|<link|@import|<iframe|<img[^>]*src=\"(?!data:)", html)
    assert all(ref.startswith(("data:", "#")) for ref in re.findall(r'(?:src|href)="([^"]*)"', html))
    assert set(re.findall(r"url\(([^)]*)\)", html)) <= {m for m in re.findall(r"url\(([^)]*)\)", html) if m.startswith("#")}
    assert html.count("<script") == 1 and html.count("<style") == 1
    assert " style=" not in html
    assert report["slides"] == 3 and report["notes"] == 2 and report["slide_images"] == "svg"
    assert report["raster_fallbacks"] == {}


def test_content_security_policy_names_the_inline_script_and_style_by_hash():
    html, _ = export(deck())
    policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', html).group(1)
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    for kind, content in (("style", style), ("script", script)):
        digest = base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode()
        assert f"{kind}-src 'sha256-{digest}'" in policy
    assert "default-src 'none'" in policy and "'unsafe-inline'" not in policy and "connect-src" not in policy


def test_every_slide_is_in_order_with_titles_and_transitions():
    html, _ = export(deck())
    assert slides_of(html) == [
        ("1", "cover", "none", "Slide 1 of 3: Quarterly Review"),
        ("2", "results", "push", "Slide 2 of 3: Results"),
        ("3", "close", "zoom", "Slide 3 of 3: Thanks"),
    ]
    assert html.count('<svg viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet" aria-hidden="true"') == 3
    assert html.count("<section") == 3
    assert "<title>Quarterly Review</title>" in html
    assert 'data-start="1"' in html and html.count('<section class="slide is-cur"') == 1


def test_screen_readers_get_a_hidden_text_layer_without_master_chrome():
    html, _ = export(deck())
    second = re.search(r'id="slide-2".*?</section>', html, re.S).group(0)
    layer = re.search(r'<div class="sr" dir="auto">(.*?)</div>', second, re.S).group(1)
    assert layer.startswith("<h2>Results</h2>")
    assert "<p>Revenue grew 42%</p>" in layer and "<p>Faster checkout</p>" in layer and "<p>New markets</p>" in layer
    assert "2 / 3" not in layer, "the master's page number is chrome"
    assert 'aria-hidden="true"' in second and 'focusable="false"' in second


def test_variables_reach_the_slides_and_their_hidden_text():
    p = deck()
    p.apply([{"type": "variable", "name": "who", "value": "nobody"}, {"type": "page", "action": "select", "page": "cover"},
             {"type": "text", "text": "Prepared for ${who}", "name": "byline", "size": 24, "x": 60, "y": 300, "color": "#111"}])
    assert "<p>Prepared for nobody</p>" in export(p)[0]
    html, _ = export(p, variables={"who": "Ada <Lovelace>"})
    assert "<p>Prepared for Ada &lt;Lovelace&gt;</p>" in html and "${who}" not in html
    assert "${" not in export(p, variables={"who": "Ada"}, presenter={"slide_images": "png"})[0].split("<aside")[0]


def test_unusual_text_and_page_names_cannot_break_out_of_the_markup():
    p = Project(400, 200, "white")
    p.apply([{"type": "page", "action": "add", "name": "x-1", "notes": "</script><script>alert(1)</script> \u0000 ‮"},
             {"type": "text", "text": "Café 日本語 שלום", "name": "title", "size": 30, "x": 10, "y": 10}])
    html, _ = export(p, presenter={"title": '"><img src=x onerror=alert(1)>'})
    assert html.count("<script") == 1 and "<img src=x" not in html and "&lt;/script&gt;" in html
    assert "\u0000" not in html and "<h2>Café 日本語 שלום</h2>" in html


def test_speaker_notes_are_embedded_escaped_and_optional():
    html, report = export(deck())
    notes = re.findall(r'<aside class="notes" hidden>(.*?)</aside>', html, re.S)
    assert notes == ["Open with the headline.\n\nThen the agenda.", "Revenue up 42% &lt;b&gt;&amp; more&lt;/b&gt;"]
    assert report["notes"] == 2
    quiet, report = export(deck(), presenter={"notes": False})
    assert "<aside" not in quiet and "Open with the headline" not in quiet and report["notes"] == 0


def test_hidden_pages_are_skipped_unless_asked_for():
    p = deck()
    p.apply({"type": "page", "action": "set", "page": "results", "hidden": True})
    html, report = export(p)
    assert [s[1] for s in slides_of(html)] == ["cover", "close"] and report["slides"] == 2
    assert "Revenue grew" not in html and "Revenue up 42%" not in html
    assert "Slide 2 of 2: Thanks" in html
    chosen, _ = export(p, pages="close,results")
    assert [s[1] for s in slides_of(chosen)] == ["close", "results"]
    all_hidden = deck()
    all_hidden.apply([{"type": "page", "action": "set", "page": name, "hidden": True} for name in ("cover", "results", "close")])
    with pytest.raises(VixlError, match="every page is hidden"):
        all_hidden.export(format="HTML")


def test_output_is_deterministic_and_changes_with_content():
    first, second = deck().export(format="HTML"), deck().export(format="HTML")
    assert first == second
    changed = deck()
    changed.apply({"type": "page", "action": "set", "page": "cover", "notes": "Different"})
    assert changed.export(format="HTML") != first


def test_options_theme_start_title_and_slide_images():
    html, _ = export(deck(), presenter={"theme": "light", "start": "results", "title": "Q3 <deck>"})
    assert 'data-theme="light"' in html and 'data-start="2"' in html
    assert "<title>Q3 &lt;deck&gt;</title>" in html
    assert re.search(r'<section class="slide is-cur" id="slide-2"', html)
    png, report = export(deck(), presenter={"slide_images": "png"}, scale=1)
    assert "<svg" not in png.split("<script>")[0].split("<body>")[1].split('<div class="zone')[0]
    images = re.findall(r'<img src="data:image/png;base64,([^"]+)"', png)
    assert len(images) == 3 and report["slide_images"] == "png"
    assert Image.open(io.BytesIO(base64.b64decode(images[0]))).size == (960, 540)
    assert not re.search(r"https?:", png)


@pytest.mark.parametrize("bad,message", [
    ({"theme": "blue"}, "theme"),
    ({"slide_images": "gif"}, "slide_images"),
    ({"notes": "yes"}, "notes"),
    ({"start": 9}, "start must be 1"),
    ({"start": 0}, "start must be 1"),
    ({"start": "nowhere"}, "does not exist"),
    ({"colour": "red"}, "Unknown presenter option"),
    ("dark", "presenter is true"),
])
def test_bad_options_are_rejected_with_the_field(bad, message):
    with pytest.raises(VixlError, match=message) as caught:
        deck().export(format="HTML", presenter=bad)
    assert caught.value.details.get("field") in ("presenter", "page", None)


def test_when_html_is_a_presentation():
    p = deck()
    assert "aria-roledescription" in p.export(format="HTML").decode()
    plain = p.export(format="HTML", presenter=False).decode()
    assert "aria-roledescription" not in plain and "data:image/svg+xml" in plain and "<script" not in plain
    one_page = p.export(format="HTML", page="results").decode()
    assert "<script" not in one_page, "an explicit page keeps the single-image HTML"
    single = Project(200, 100, "white")
    assert "<script" not in single.export(format="HTML").decode()
    assert "aria-roledescription" in single.export(format="HTML", presenter=True).decode()
    for fmt in ("PNG", "PDF", "PPTX"):
        with pytest.raises(VixlError, match="presenter applies to HTML"):
            p.export(format=fmt, presenter=True)
    with pytest.raises(VixlError, match="presentation shows pages in RGB"):
        p.export(format="HTML", color_space="cmyk", presenter=True)
    with pytest.raises(VixlError, match="SVG export is RGB"):
        p.export(format="HTML", color_space="cmyk")  # not asked for: the single-image page's own rules apply


def test_effects_svg_cannot_express_fall_back_per_layer_and_are_listed():
    p = deck()
    p.apply([{"type": "page", "action": "select", "page": "results"},
             {"type": "filter", "target": "title", "name": "ink-blot"}])
    html, report = export(p)
    assert "data:image/png;base64" in html
    assert set(report["raster_fallbacks"]) == {"2"}
    fallback = report["raster_fallbacks"]["2"][0]
    assert fallback["layer"] == "title" and fallback["effects"] == ["ink-blot"] and fallback["reason"]
    with pytest.raises(VixlError) as caught:
        p.export(format="HTML", svg_policy="strict")
    assert caught.value.code == "svg_raster_required"


def test_ids_are_unique_across_slides_so_gradients_do_not_collide():
    p = Project(400, 200, "white")
    for name, color in (("a", "red"), ("b", "blue")):
        p.apply([{"type": "page", "action": "add", "name": name},
                 {"type": "shape", "shape": "rectangle", "name": "box", "width": 200, "height": 100, "x": 20, "y": 20,
                  "fill": color}])
    html, _ = export(p)
    ids = re.findall(r' id="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    refs = set(re.findall(r"url\(#([^)]+)\)", html))
    assert refs <= set(ids)


def test_size_warning_for_very_large_files(monkeypatch):
    from vixl import presenter

    monkeypatch.setattr(presenter, "WARN_BYTES", 1000)
    _, report = export(deck())
    assert "MiB" in report["warnings"][0]
    tiny = Project(100, 100, "white")
    tiny.limits = type(tiny.limits)(max_project_bytes=5000)
    tiny.apply([{"type": "page", "action": "add", "name": "a"}])
    with pytest.raises(VixlError, match="size limit"):
        tiny.export(format="HTML")


def test_cli_export_html_flags(tmp_path):
    deck().save(tmp_path / "deck.vixl")

    def run(*args):
        return subprocess.run([sys.executable, "-m", "vixl", "-p", "deck.vixl", "--json", *args], cwd=tmp_path,
                              capture_output=True, timeout=60)

    result = run("export", "out.html", "--presenter-theme", "light", "--slide-images", "png", "--start-slide", "2",
                 "--no-notes")
    assert result.returncode == 0, result.stderr.decode()
    info = json.loads(result.stdout)
    assert info["slides"] == 3 and info["slide_images"] == "png" and info["notes"] == 0
    text = (tmp_path / "out.html").read_text(encoding="utf-8")
    assert 'data-theme="light"' in text and 'data-start="2"' in text and "<aside" not in text
    run("export", "plain.html", "--no-presenter")
    assert "<script" not in (tmp_path / "plain.html").read_text(encoding="utf-8")
    run("export", "some.html", "--pages", "1,3")
    assert len(slides_of((tmp_path / "some.html").read_text(encoding="utf-8"))) == 2
    assert run("export", "bad.html", "--presenter-theme", "blue").returncode != 0
    assert run("export", "bad.html", "--start-slide", "9").returncode != 0


def test_mcp_and_rest_exports(tmp_path):
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    deck().save(tmp_path / "deck.vixl")
    session = Session(workspace=tmp_path)
    server = build_server(session)
    result = asyncio.run(server.call_tool("vixl_export_file", {
        "path": "deck.html", "document": "deck.vixl", "pages": "1-2", "presenter": {"theme": "auto", "notes": False}}))
    info = json.loads(result[0][0].text) if isinstance(result, tuple) else json.loads(result[0].text)
    assert info["slides"] == 2 and info["format"] == "HTML" and info["notes"] == 0
    text = (tmp_path / "deck.html").read_text(encoding="utf-8")
    assert 'data-theme="auto"' in text and len(slides_of(text)) == 2
    with TestClient(create_app(tmp_path / "deck.vixl")) as client:
        response = client.post("/export", json={"format": "HTML", "presenter": {"start": 3}})
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
        assert 'data-start="3"' in response.text
        assert client.post("/export", json={"format": "HTML", "presenter": {"start": 99}}).status_code == 400


# The script, in a real browser. Skipped unless Playwright and a Chromium are available.


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")
    manager = sync_api.sync_playwright().start()
    try:
        try:
            chromium = manager.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - any launch failure means there is no usable browser
            pytest.skip(f"Chromium is not available: {exc}")
        yield chromium
        chromium.close()
    finally:
        manager.stop()


@pytest.fixture(scope="module")
def deck_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("presenter") / "deck.html"
    deck().export(path)
    return path


class Viewer:
    """A page showing the presentation, with its console, requests and CSP reports recorded."""

    def __init__(self, browser, path, hash="", scripts=(), **context):
        self.context = browser.new_context(viewport={"width": 1280, "height": 720}, **context)
        self.problems, self.requests = [], []
        self.context.add_init_script("""
            window.__csp = [];
            document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective));
        """)
        for script in scripts:
            self.context.add_init_script(script)
        self.page = self.watch(self.context.new_page())
        self.uri = path.as_uri()
        self.page.goto(self.uri + hash)

    def watch(self, page):
        page.on("console", lambda m: self.problems.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.problems.append(str(e)))
        page.on("request", lambda r: self.requests.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
        return page

    def current(self, page=None):
        return int((page or self.page).evaluate("document.querySelector('.slide.is-cur').dataset.n"))

    def wait(self, expression, page=None):
        """Poll until the expression is truthy. (Playwright's own wait_for_function evaluates a string, which the
        page's Content-Security-Policy rightly refuses.)"""
        target = page or self.page
        deadline = time.monotonic() + 8
        while not target.evaluate(expression):
            assert time.monotonic() < deadline, f"timed out waiting for {expression}"
            time.sleep(0.02)

    def settle(self, page=None):
        self.wait("!document.getElementById('stage').hasAttribute('data-tr')", page)

    def press(self, *keys):
        for key in keys:
            self.page.keyboard.press(key)
        self.settle()

    def close(self):
        assert not self.problems, self.problems
        assert not self.requests
        for page in self.context.pages:
            assert page.evaluate("window.__csp") == []
        self.context.close()


@pytest.fixture
def viewer(browser, deck_file):
    made = []

    def make(hash="", **context):
        made.append(Viewer(browser, deck_file, hash, **context))
        return made[-1]

    yield make
    for item in made:
        item.close()


def test_browser_keyboard_navigation_updates_the_hash(viewer):
    v = viewer()
    assert v.current() == 1 and v.page.url.endswith("#1")
    v.press("ArrowRight")
    assert v.current() == 2 and v.page.url.endswith("#2")
    v.press("Space")
    assert v.current() == 3
    v.press("ArrowRight")
    assert v.current() == 3, "stays on the last slide"
    v.press("PageUp")
    assert v.current() == 2
    v.press("Home")
    assert v.current() == 1
    v.press("End")
    assert v.current() == 3 and v.page.url.endswith("#3")
    v.press("ArrowLeft", "ArrowLeft", "ArrowLeft")
    assert v.current() == 1
    v.press("3", "Enter")
    assert v.current() == 3
    v.press("2")
    assert v.current() == 3, "digits wait for Enter"
    v.press("Enter")
    assert v.current() == 2
    v.page.evaluate("location.hash = '#1'")
    v.wait("document.querySelector('.slide.is-cur').dataset.n === '1'")
    assert v.page.evaluate("document.getElementById('status').textContent") == "Slide 1 of 3: Quarterly Review"


def test_browser_hash_deep_links_open_the_slide(viewer):
    assert viewer("#3").current() == 3
    assert viewer("#results").current() == 2
    assert viewer("#99").current() == 3


def test_browser_scales_each_slide_to_the_window_with_letterboxing(viewer):
    v = viewer()
    for width, height in ((1000, 1000), (500, 900), (2000, 500)):
        v.page.set_viewport_size({"width": width, "height": height})
        box = v.page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); "
                              "return [r.left, r.top, r.width, r.height]; })()")
        scale = min(width / 960, height / 540)
        assert box[2] == pytest.approx(960 * scale, abs=1) and box[3] == pytest.approx(540 * scale, abs=1)
        assert box[0] == pytest.approx((width - box[2]) / 2, abs=1) and box[1] == pytest.approx((height - box[3]) / 2, abs=1)


def test_browser_overview_opens_and_picks_a_slide(viewer):
    v = viewer()
    v.press("o")
    assert v.page.evaluate("document.body.classList.contains('overview')")
    boxes = v.page.evaluate("[...document.querySelectorAll('.slide')].map(s => { const r = s.getBoundingClientRect(); "
                            "return [getComputedStyle(s).visibility, r.width, r.height]; })")
    assert len(boxes) == 3 and all(b[0] == "visible" and b[1] > 100 and b[2] > 50 for b in boxes)
    v.press("ArrowRight")
    assert v.current() == 2
    v.press("Escape")
    assert not v.page.evaluate("document.body.classList.contains('overview')") and v.current() == 2
    v.press("o")
    v.page.click("#slide-3")
    assert v.current() == 3 and not v.page.evaluate("document.body.classList.contains('overview')")
    v.page.click(".bar [data-act=overview]")
    assert v.page.evaluate("document.body.classList.contains('overview')")
    v.press("Enter")
    assert not v.page.evaluate("document.body.classList.contains('overview')")


def test_browser_click_zones_buttons_and_swipes(viewer):
    v = viewer()
    v.page.mouse.click(1000, 300)
    v.settle()
    assert v.current() == 2
    v.page.mouse.click(60, 300)
    v.settle()
    assert v.current() == 1
    v.page.click(".bar [data-act=next]")
    v.settle()
    assert v.current() == 2

    def swipe(start, end):
        v.page.evaluate("""([a, b]) => {
            const stage = document.getElementById('stage');
            const fire = (type, x) => stage.dispatchEvent(new PointerEvent(type, {pointerType: 'touch', clientX: x, clientY: 300, bubbles: true}));
            fire('pointerdown', a); fire('pointerup', b);
        }""", [start, end])
        v.settle()

    swipe(700, 300)
    assert v.current() == 3
    swipe(300, 700)
    assert v.current() == 2
    swipe(500, 520)
    assert v.current() == 2, "a short drag is not a swipe"


def test_browser_progress_bar_and_blank_screens(viewer):
    v = viewer()
    v.press("ArrowRight")
    assert v.page.evaluate("document.getElementById('progress').style.transform") == "scaleX(0.666667)"
    v.press("b")
    assert v.page.evaluate("document.body.dataset.blank") == "b" and v.page.is_visible("#blank")
    v.press("ArrowRight")
    assert v.page.evaluate("document.body.dataset.blank") == "" and v.current() == 2, "any step brings the slide back"
    v.press("w")
    assert v.page.evaluate("getComputedStyle(document.getElementById('blank')).backgroundColor") == "rgb(255, 255, 255)"
    v.press("Escape")
    assert not v.page.is_visible("#blank")
    v.press("?")
    assert v.page.is_visible("#help")
    v.press("Escape")
    assert not v.page.is_visible("#help")
    v.press("f", "f")  # fullscreen may be refused in a headless browser; it must not break anything


def test_browser_transitions_come_from_the_page_settings(viewer):
    v = viewer()
    v.page.keyboard.press("ArrowRight")  # cover -> results: the incoming page's own transition, push
    state = v.page.evaluate("[document.getElementById('stage').dataset.tr, document.getElementById('stage').dataset.dir, "
                            "document.querySelector('#slide-1').className, document.querySelector('#slide-2').className]")
    assert state == ["push", "f", "slide is-out", "slide is-cur is-in"]
    assert v.page.evaluate("getComputedStyle(document.querySelector('#slide-2')).animationName") == "t-from-right"
    v.settle()
    assert v.page.evaluate("document.querySelector('#slide-1').className") == "slide"
    v.page.keyboard.press("ArrowLeft")  # going back reverses the page being left
    assert v.page.evaluate("[document.getElementById('stage').dataset.tr, document.getElementById('stage').dataset.dir]") == ["push", "b"]
    v.page.keyboard.press("ArrowRight")  # a keypress during a transition finishes it and starts the next
    v.page.keyboard.press("ArrowRight")
    assert v.page.evaluate("document.getElementById('stage').dataset.tr") == "zoom"
    v.settle()
    assert v.current() == 3


def test_browser_reduced_motion_skips_transitions(viewer):
    v = viewer(reduced_motion="reduce")
    v.page.keyboard.press("ArrowRight")
    assert v.page.evaluate("document.getElementById('stage').hasAttribute('data-tr')") is False
    assert v.current() == 2 and v.page.evaluate("document.querySelectorAll('.is-out').length") == 0


def test_browser_slides_render_and_the_screen_reader_text_is_not_visible(viewer):
    v = viewer()
    shot = Image.open(io.BytesIO(v.page.screenshot())).convert("RGB")
    assert shot.size == (1280, 720)
    assert shot.getpixel((640, 360)) == (244, 244, 244), "the master background fills the slide"
    colors = shot.crop((0, 200, 640, 520)).getcolors(100000)
    assert any(sum(c) < 120 for _, c in colors), "title glyphs are drawn"
    assert v.page.evaluate("document.querySelector('#slide-1 .sr').getBoundingClientRect().width") <= 1
    assert v.page.evaluate("document.querySelector('#slide-3').getAttribute('aria-label')") == "Slide 3 of 3: Thanks"
    hidden = v.page.evaluate("getComputedStyle(document.querySelector('#slide-3')).visibility")
    assert hidden == "hidden", "slides that are not showing are out of the accessibility tree"


def test_browser_draws_the_slide_like_vixl_does(viewer):
    np = pytest.importorskip("numpy")
    v = viewer("#2")
    v.page.set_viewport_size({"width": 960, "height": 540})
    v.page.evaluate("for (const s of ['.bar', '.progress']) document.querySelector(s).style.display = 'none'")
    v.page.mouse.move(900, 10)
    shot = np.asarray(Image.open(io.BytesIO(v.page.screenshot())).convert("RGB"), dtype=int)
    reference = np.asarray(deck().render(page="results").convert("RGB"), dtype=int)
    difference = np.abs(shot - reference)
    assert shot.shape == reference.shape
    assert difference.mean() < 1 and (difference.max(axis=2) > 96).mean() < 0.001


def test_browser_speaker_view_shows_notes_and_stays_in_sync(viewer):
    v = viewer("#2")
    with v.context.expect_page() as opened:
        v.page.keyboard.press("s")
    speaker = v.watch(opened.value)
    speaker.wait_for_selector("#sp-count")
    assert speaker.evaluate("window.name").startswith("vixl-speaker") and "?speaker" in speaker.url
    v.wait("document.getElementById('sp-count').textContent === 'Slide 2 of 3'", speaker)
    assert speaker.inner_text("#sp-notes") == "Revenue up 42% <b>& more</b>"
    assert speaker.evaluate("document.querySelector('#sp-cur .slide').dataset.n") == "2"
    assert speaker.evaluate("document.querySelector('#sp-next .slide').dataset.n") == "3"
    assert re.fullmatch(r"\d\d:\d\d:\d\d", speaker.inner_text("#sp-elapsed"))
    # The audience window leads ...
    v.page.keyboard.press("ArrowRight")
    v.wait("document.getElementById('sp-count').textContent === 'Slide 3 of 3'", speaker)
    assert speaker.is_visible("#sp-end") and speaker.inner_text("#sp-notes") == "No notes for this slide."
    # ... and the speaker's keys, buttons and blank screen drive it.
    speaker.keyboard.press("Home")
    v.wait("document.querySelector('.slide.is-cur').dataset.n === '1'")
    assert speaker.inner_text("#sp-notes").startswith("Open with the headline.")
    speaker.click(".sp-cur [data-act=next]")
    v.wait("document.querySelector('.slide.is-cur').dataset.n === '2'")
    speaker.keyboard.press("b")
    v.wait("document.body.dataset.blank === 'b'")
    speaker.keyboard.press("b")
    v.wait("document.body.dataset.blank === ''")
    speaker.click("#sp-toggle")
    assert speaker.inner_text("#sp-toggle") == "Resume"
    speaker.click("[data-act=larger]")
    assert speaker.evaluate("document.getElementById('sp-notes').style.fontSize") == "22px"
    assert v.current() == 2 and v.page.url.endswith("#2")


NO_BROADCAST = "delete window.BroadcastChannel;"
NO_STORAGE = "Storage.prototype.setItem = function () { throw new Error('storage blocked'); };"
NO_MESSAGES = "window.addEventListener('message', e => e.stopImmediatePropagation(), true);"


@pytest.mark.parametrize("name,scripts", [
    ("BroadcastChannel", [NO_STORAGE, NO_MESSAGES]),
    ("localStorage", [NO_BROADCAST, NO_MESSAGES]),
    ("postMessage", [NO_BROADCAST, NO_STORAGE]),
])
def test_browser_speaker_view_sync_works_over_each_transport_alone(viewer, name, scripts):
    v = viewer("#1", scripts=scripts)
    with v.context.expect_page() as opened:
        v.page.keyboard.press("s")
    speaker = v.watch(opened.value)
    speaker.wait_for_selector("#sp-count")
    v.page.keyboard.press("ArrowRight")
    v.wait("document.getElementById('sp-count').textContent === 'Slide 2 of 3'", speaker)
    speaker.keyboard.press("End")
    v.wait("document.querySelector('.slide.is-cur').dataset.n === '3'")


def test_browser_print_gives_one_page_per_slide(viewer):
    pypdf = pytest.importorskip("pypdf")
    v = viewer()
    v.page.emulate_media(media="print")
    reader = pypdf.PdfReader(io.BytesIO(v.page.pdf(prefer_css_page_size=True)))
    assert len(reader.pages) == 3
    width, height = (float(x) for x in reader.pages[0].mediabox[2:])
    assert (round(width / 72, 2), round(height / 72, 2)) == (13.33, 7.5)


def test_browser_without_javascript_lists_the_slides(browser, deck_file):
    context = browser.new_context(java_script_enabled=False, viewport={"width": 900, "height": 700})
    page = context.new_page()
    page.goto(deck_file.as_uri())
    boxes = [page.locator(f"#slide-{n}").bounding_box() for n in (1, 2, 3)]
    assert all(box and box["width"] > 800 for box in boxes) and boxes[0]["y"] < boxes[1]["y"] < boxes[2]["y"]
    context.close()
