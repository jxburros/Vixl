"""The browser half of the presenter export: one stylesheet, one script and the static chrome.

Everything here is plain text that ``presenter.py`` embeds into the HTML file. The page loads no
other resource and runs exactly one inline script and one inline style block, so the file's
Content-Security-Policy can allow just their hashes. The script only toggles classes and calls the
CSS Object Model (never ``setAttribute("style", …)``), which a hash-only ``style-src`` permits.
Placeholders look like ``@@NAME@@`` and are filled by ``presenter.style``.
"""

STYLE = r"""
:root{--aw:@@AW@@;--ah:@@AH@@;--dur:450ms;--bg:#000;--fg:#f2f2f5;--chrome:rgba(24,24,28,.8);--line:rgba(255,255,255,.22);--accent:#6ea8ff;--cell:280px;color-scheme:dark}
:root[data-theme=light]{--bg:#e8e8ed;--fg:#17171c;--chrome:rgba(255,255,255,.88);--line:rgba(0,0,0,.2);--accent:#1b5ed6;color-scheme:light}
@media (prefers-color-scheme:light){:root[data-theme=auto]{--bg:#e8e8ed;--fg:#17171c;--chrome:rgba(255,255,255,.88);--line:rgba(0,0,0,.2);--accent:#1b5ed6;color-scheme:light}}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
button{font:inherit}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0;user-select:text}
.deck{position:fixed;inset:0;display:grid;place-items:center;overflow:hidden}
.stage{position:relative;width:min(100vw,calc(100vh*var(--aw)/var(--ah)));width:min(100vw,calc(100dvh*var(--aw)/var(--ah)));aspect-ratio:var(--aw)/var(--ah);overflow:hidden;background:#fff;user-select:none;-webkit-user-select:none;touch-action:pan-y pinch-zoom}
body.idle .stage{cursor:none}
.slide{position:absolute;inset:0;visibility:hidden;overflow:hidden;background:#fff}
.slide.is-cur,.slide.is-out{visibility:visible}
.slide.is-cur{z-index:2}
.slide.is-out{z-index:1}
.slide>svg,.slide>img{display:block;width:100%;height:100%;pointer-events:none}
.zone{position:absolute;top:0;bottom:0;z-index:5;cursor:pointer;-webkit-tap-highlight-color:transparent}
.zone-prev{left:0;width:25%}
.zone-next{left:25%;right:0}
.zone::after{position:absolute;top:50%;width:44px;height:44px;margin-top:-22px;border-radius:50%;background:var(--chrome);color:var(--fg);font-size:30px;line-height:42px;text-align:center;opacity:0;transition:opacity .2s}
.zone-prev::after{content:"\2039";left:14px}
.zone-next::after{content:"\203A";right:14px}
.zone:hover::after{opacity:.9}
@media (hover:none){.zone::after{display:none}}
.progress{position:fixed;left:0;right:0;bottom:0;height:4px;z-index:20;background:var(--line)}
.progress>div{height:100%;background:var(--accent);transform-origin:0 50%;transform:scaleX(0);transition:transform .25s}
.bar{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:30;display:flex;align-items:center;gap:2px;padding:4px;border-radius:999px;background:var(--chrome);color:var(--fg);box-shadow:0 2px 14px rgba(0,0,0,.35);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);transition:opacity .25s}
body.idle .bar:not(:focus-within){opacity:0;pointer-events:none}
button{color:inherit;background:none;border:0;border-radius:999px;padding:6px 12px;cursor:pointer}
button:hover{background:var(--line)}
button:focus-visible,.slide:focus-visible,.sp-notes:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.count{min-width:4.8em;text-align:center;font-variant-numeric:tabular-nums}
@media (max-width:560px){.bar .opt{display:none}}
.blank{position:fixed;inset:0;z-index:50}
.blank.b{background:#000}
.blank.w{background:#fff}
.toast{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:60;padding:8px 14px;border-radius:8px;background:var(--chrome);color:var(--fg);opacity:0;pointer-events:none;transition:opacity .2s}
.toast.on{opacity:1}
.help{position:fixed;inset:0;z-index:55;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.6)}
.help>div{max-width:560px;max-height:100%;overflow:auto;padding:18px 22px;border-radius:12px;background:var(--bg);color:var(--fg);box-shadow:0 8px 40px rgba(0,0,0,.5)}
.help h2{margin:0 0 8px;font-size:18px}
.help dl{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;margin:0}
.help dt{font-weight:600;white-space:nowrap}
.help dd{margin:0}
body.overview .deck{place-items:start;overflow:auto}
body.overview .stage{width:100%;height:auto;aspect-ratio:auto;overflow:visible;background:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(var(--cell),100%),1fr));gap:20px;padding:24px 24px 72px;touch-action:auto}
body.overview .slide{position:relative;inset:auto;z-index:auto;visibility:visible;aspect-ratio:var(--aw)/var(--ah);cursor:pointer;outline:2px solid var(--line);border-radius:3px}
body.overview .slide.is-cur{outline:4px solid var(--accent)}
body.overview .slide::after{content:attr(data-n);position:absolute;left:6px;bottom:6px;min-width:1.8em;padding:1px 6px;border-radius:999px;background:var(--chrome);color:var(--fg);font-size:12px;text-align:center}
body.overview .zone{display:none}
[data-tr] .is-in,[data-tr] .is-out{animation-duration:var(--dur);animation-timing-function:cubic-bezier(.4,0,.2,1);animation-fill-mode:both}
[data-tr=fade] .is-in{animation-name:t-fade}
[data-tr=push][data-dir=f] .is-in{animation-name:t-from-right}
[data-tr=push][data-dir=f] .is-out{animation-name:t-to-left}
[data-tr=push][data-dir=b] .is-in{animation-name:t-from-left}
[data-tr=push][data-dir=b] .is-out{animation-name:t-to-right}
[data-tr=cover][data-dir=f] .is-in{animation-name:t-from-right}
[data-tr=cover][data-dir=b] .is-out{animation-name:t-to-right;z-index:3}
[data-tr=wipe][data-dir=f] .is-in{animation-name:t-wipe-f}
[data-tr=wipe][data-dir=b] .is-in{animation-name:t-wipe-b}
[data-tr=split] .is-in{animation-name:t-split}
[data-tr=zoom][data-dir=f] .is-in{animation-name:t-zoom-in}
[data-tr=zoom][data-dir=b] .is-in{animation-name:t-zoom-out}
@keyframes t-fade{from{opacity:0}to{opacity:1}}
@keyframes t-from-right{from{transform:translateX(100%)}to{transform:none}}
@keyframes t-from-left{from{transform:translateX(-100%)}to{transform:none}}
@keyframes t-to-left{from{transform:none}to{transform:translateX(-100%)}}
@keyframes t-to-right{from{transform:none}to{transform:translateX(100%)}}
@keyframes t-wipe-f{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes t-wipe-b{from{clip-path:inset(0 0 0 100%)}to{clip-path:inset(0 0 0 0)}}
@keyframes t-split{from{clip-path:inset(0 50% 0 50%)}to{clip-path:inset(0 0 0 0)}}
@keyframes t-zoom-in{from{opacity:0;transform:scale(.8)}to{opacity:1;transform:none}}
@keyframes t-zoom-out{from{opacity:0;transform:scale(1.2)}to{opacity:1;transform:none}}
.speaker{position:fixed;inset:0;display:none;grid-template-rows:auto minmax(0,1fr);gap:12px;padding:12px 16px;background:var(--bg);color:var(--fg);overflow:hidden}
body.speaker-mode .speaker{display:grid}
body.speaker-mode .deck,body.speaker-mode .bar,body.speaker-mode .progress{display:none}
.sp-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 20px;font-variant-numeric:tabular-nums}
.sp-big{font-size:clamp(20px,3vw,34px);font-weight:600}
.sp-flag{display:none;padding:2px 10px;border-radius:999px;background:var(--accent);color:#fff;font-size:13px}
body[data-blank=b] .sp-flag,body[data-blank=w] .sp-flag{display:inline-block}
.sp-main{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:16px;min-height:0}
.sp-col{display:flex;flex-direction:column;gap:8px;min-height:0}
.sp-col h2{display:flex;align-items:center;justify-content:space-between;margin:0;font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;opacity:.7}
.slot{position:relative;width:100%;aspect-ratio:var(--aw)/var(--ah);overflow:hidden;background:#222;border-radius:4px;outline:1px solid var(--line)}
.sp-cur .slot{width:min(100%,calc((100vh - 190px)*var(--aw)/var(--ah)))}
.slot .slide{position:absolute;inset:0;visibility:visible;z-index:auto}
.sp-end{position:absolute;inset:0;display:grid;place-items:center;margin:0;color:#aaa}
.sp-notes{flex:1;min-height:80px;overflow:auto;padding:12px 14px;border-radius:8px;background:var(--chrome);white-space:pre-wrap;overflow-wrap:anywhere;font-size:20px;line-height:1.45}
.sp-notes.none{opacity:.6;font-style:italic}
.sp-ctl{display:flex;gap:8px;flex-wrap:wrap}
.sp-ctl button,.sp-col h2 button{padding:6px 14px;background:var(--line)}
.sp-next-slot{cursor:pointer}
@media (max-width:800px){.sp-main{grid-template-columns:1fr;overflow:auto}.sp-cur .slot{width:100%}}
@media (prefers-reduced-motion:reduce){.slide,.slide *{animation:none!important}.progress>div,.bar,.zone::after,.toast{transition:none}}
@page{size:@@PW@@in @@PH@@in;margin:0}
@media print{
html,body{height:auto;overflow:visible;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.bar,.progress,.blank,.toast,.help,.speaker,.zone,.status{display:none!important}
.deck,body.overview .deck{position:static;display:block;place-items:normal;overflow:visible}
.stage,body.overview .stage{display:block;width:auto;height:auto;aspect-ratio:auto;overflow:visible;padding:0;background:none}
.slide,body.overview .slide{position:relative;inset:auto;display:block;visibility:visible;width:@@PW@@in;height:@@PH@@in;overflow:hidden;outline:0;border-radius:0;break-after:page;page-break-after:always}
.slide:last-of-type{break-after:auto;page-break-after:auto}
.slide::after{display:none}
}
@media (scripting:none){
html,body{height:auto;overflow:auto}
.deck{position:static;display:block;place-items:normal;padding:16px;overflow:visible}
.stage{width:auto;height:auto;aspect-ratio:auto;overflow:visible;background:none}
.slide{position:relative;inset:auto;visibility:visible;width:min(100%,1100px);aspect-ratio:var(--aw)/var(--ah);margin:0 auto 16px;outline:1px solid var(--line)}
.bar,.progress,.zone,.speaker{display:none}
}
"""

# Static chrome after the slides: controls, progress bar, blank screen, messages, help and the
# speaker view's skeleton (shown only in the speaker window, where the script fills it).
CHROME = r"""
<nav class="bar" id="bar" aria-label="Presentation controls">
<button type="button" data-act="prev" title="Previous slide (Left arrow)" aria-label="Previous slide">&#8249;</button>
<span class="count" id="count" aria-hidden="true"></span>
<button type="button" data-act="next" title="Next slide (Right arrow, Space)" aria-label="Next slide">&#8250;</button>
<button type="button" data-act="overview" title="Overview (O)">Overview</button>
<button type="button" class="opt" data-act="fullscreen" title="Fullscreen (F)">Fullscreen</button>
<button type="button" class="opt" data-act="speaker" title="Speaker view (S)">Speaker</button>
<button type="button" class="opt" data-act="help" title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts">?</button>
</nav>
<div class="progress" aria-hidden="true"><div id="progress"></div></div>
<div class="blank" id="blank" hidden></div>
<div class="toast" id="toast" aria-hidden="true"></div>
<div class="sr status" id="status" role="status" aria-live="polite"></div>
<div class="help" id="help" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" hidden>
<div><h2>Keyboard shortcuts</h2><dl>
<dt>Right, Down, Space, PageDown</dt><dd>Next slide</dd>
<dt>Left, Up, Shift+Space, PageUp</dt><dd>Previous slide</dd>
<dt>Home, End</dt><dd>First, last slide</dd>
<dt>Number, Enter</dt><dd>Go to that slide</dd>
<dt>O, Esc</dt><dd>Overview of all slides</dd>
<dt>F</dt><dd>Fullscreen</dd>
<dt>B, W</dt><dd>Black, white screen</dd>
<dt>S</dt><dd>Speaker view in a new window</dd>
<dt>?</dt><dd>This list</dd>
</dl><p><button type="button" data-act="help">Close</button></p></div>
</div>
<div class="speaker" id="speaker" aria-label="Speaker view">
<header class="sp-head">
<div class="sp-big" id="sp-count"></div>
<div class="sp-big" id="sp-elapsed" role="timer" aria-label="Elapsed time">00:00:00</div>
<div class="sp-ctl"><button type="button" data-act="timer" id="sp-toggle">Pause</button><button type="button" data-act="reset">Reset</button><span class="sp-flag" id="sp-flag">Screen blanked</span></div>
<div class="sp-big" id="sp-clock" aria-label="Time of day"></div>
</header>
<div class="sp-main">
<div class="sp-col sp-cur"><h2>Current slide</h2><div class="slot" id="sp-cur"></div>
<div class="sp-ctl"><button type="button" data-act="prev">Previous</button><button type="button" data-act="next">Next</button></div></div>
<div class="sp-col sp-side"><h2>Next slide</h2><div class="slot sp-next-slot" id="sp-next" data-act="next"><p class="sp-end" id="sp-end" hidden>End of the presentation</p></div>
<h2>Notes <span><button type="button" data-act="smaller" aria-label="Smaller notes text">A-</button> <button type="button" data-act="larger" aria-label="Larger notes text">A+</button></span></h2>
<div class="sp-notes" id="sp-notes" tabindex="0" aria-label="Speaker notes"></div></div>
</div>
</div>
"""

SCRIPT = r"""
(function () {
  "use strict";
  var doc = document, root = doc.documentElement, body = doc.body;
  var KEY = "vixl-presenter:" + root.getAttribute("data-deck");
  var stage = doc.getElementById("stage");
  var slides = [].slice.call(stage.querySelectorAll(".slide"));
  var total = slides.length;
  var DUR = 450;
  var isSpeaker = /[?&]speaker(?:[=&]|$)/.test(location.search) || String(window.name).indexOf("vixl-speaker") === 0;
  var motion = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  var cur = -1, busy = 0, overview = false, blank = "", digits = "", digitTimer = 0, idleTimer = 0;
  var toastTimer = 0, swiped = false, speakerWin = null, peers = [], seen = [], seq = 0;
  var me = Math.random().toString(36).slice(2, 10);
  var chan = null, timer = { running: true, base: 0, since: Date.now() }, notesSize = 20;

  function $(id) { return doc.getElementById(id); }
  function clamp(n) { return Math.max(0, Math.min(total - 1, n)); }
  function toast(text) {
    var t = $("toast");
    t.textContent = text;
    t.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove("on"); }, 1800);
  }

  /* ---- showing slides ---------------------------------------------------------------- */
  function settle() {
    if (busy) { clearTimeout(busy); busy = 0; }
    stage.removeAttribute("data-tr");
    stage.removeAttribute("data-dir");
    slides.forEach(function (s) { s.classList.remove("is-in", "is-out"); });
  }

  function present(from, to, animate) {
    var a = slides[from], b = slides[to];
    slides.forEach(function (s) { if (s !== a && s !== b) s.classList.remove("is-cur"); });
    if (overview) {
      b.classList.add("is-cur");
      if (a && a !== b) a.classList.remove("is-cur");
      b.scrollIntoView({ block: "nearest" });
      b.focus({ preventScroll: true });
      return;
    }
    var type = a && b ? ((to > from ? b : a).getAttribute("data-transition") || "none") : "none";
    if (!a || a === b || !animate || type === "none" || motion.matches) {
      if (a && a !== b) a.classList.remove("is-cur");
      b.classList.add("is-cur");
      return;
    }
    stage.setAttribute("data-tr", type);
    stage.setAttribute("data-dir", to > from ? "f" : "b");
    a.classList.remove("is-cur");
    a.classList.add("is-out");
    b.classList.add("is-cur", "is-in");
    busy = setTimeout(settle, DUR + 80);
  }

  function go(n, o) {
    o = o || {};
    n = clamp(n);
    if (n === cur && !o.force) return;
    var from = cur;
    settle();
    cur = n;
    slides.forEach(function (s, i) { if (i === n) s.setAttribute("aria-current", "true"); else s.removeAttribute("aria-current"); });
    if (isSpeaker) renderSpeaker(); else present(from, n, !o.instant);
    refresh();
    if (!o.silent) post({ k: "go", n: n });
  }

  function step(d) {
    if (blank) { toggleBlank(blank); return; }
    go(cur + d);
  }

  function refresh() {
    var s = slides[cur];
    $("progress").style.transform = "scaleX(" + ((cur + 1) / total) + ")";
    $("count").textContent = (cur + 1) + " / " + total;
    $("status").textContent = s.getAttribute("aria-label") || "";
    if (!isSpeaker) writeHash();
  }

  /* ---- URL hash: #3 opens slide 3 (a page name works too) ----------------------------- */
  function hashIndex() {
    var h = location.hash.replace(/^#/, "");
    if (!h) return -1;
    var m = /^(?:slide-)?(\d+)$/.exec(h);
    if (m) return clamp(parseInt(m[1], 10) - 1);
    try { h = decodeURIComponent(h); } catch (e) { /* keep the raw text */ }
    for (var i = 0; i < total; i++) if (slides[i].getAttribute("data-name") === h) return i;
    return -1;
  }
  function writeHash() {
    var h = "#" + (cur + 1);
    if (location.hash === h) return;
    try { history.replaceState(null, "", h); } catch (e) { try { location.hash = h; } catch (e2) { /* read-only location */ } }
  }
  window.addEventListener("hashchange", function () {
    var i = hashIndex();
    if (i >= 0 && i !== cur) go(i);
  });

  /* ---- overview, blank screen, fullscreen, help --------------------------------------- */
  function setOverview(on) {
    if (isSpeaker || on === overview) return;
    settle();
    overview = on;
    body.classList.toggle("overview", on);
    slides.forEach(function (s, i) {
      if (on) { s.setAttribute("tabindex", "0"); s.classList.toggle("is-cur", i === cur); } else { s.removeAttribute("tabindex"); }
    });
    if (on) {
      slides[cur].scrollIntoView({ block: "center" });
      slides[cur].focus({ preventScroll: true });
    } else {
      slides.forEach(function (s, i) { s.classList.toggle("is-cur", i === cur); });
      if (doc.activeElement && doc.activeElement.blur) doc.activeElement.blur();
    }
  }
  function columns() {
    var top = slides[0].getBoundingClientRect().top, n = 0;
    for (var i = 0; i < slides.length; i++) { if (Math.abs(slides[i].getBoundingClientRect().top - top) < 3) n++; else break; }
    return Math.max(1, n);
  }
  function applyBlank(mode) {
    blank = mode || "";
    var el = $("blank");
    el.hidden = !blank;
    el.className = "blank" + (blank ? " " + blank : "");
    body.setAttribute("data-blank", blank);
  }
  function toggleBlank(mode) {
    applyBlank(blank === mode ? "" : mode);
    post({ k: "blank", mode: blank });
  }
  function fullscreen() {
    try {
      if (doc.fullscreenElement || doc.webkitFullscreenElement) {
        (doc.exitFullscreen || doc.webkitExitFullscreen).call(doc);
      } else {
        var ask = root.requestFullscreen || root.webkitRequestFullscreen;
        var result = ask && ask.call(root);
        if (result && result.catch) result.catch(function () { toast("Fullscreen was refused"); });
      }
    } catch (e) { /* fullscreen is optional */ }
  }
  function toggleHelp() { $("help").hidden = !$("help").hidden; }

  /* ---- speaker view ------------------------------------------------------------------- */
  function openSpeaker() {
    if (isSpeaker) return;
    if (speakerWin && !speakerWin.closed) { speakerWin.focus(); return; }
    var base = location.href.split("#")[0].split("?")[0];
    var w = null;
    try { w = window.open(base + "?speaker#" + (cur + 1), "vixl-speaker-" + root.getAttribute("data-deck"), "popup,width=1180,height=760"); } catch (e) { w = null; }
    if (!w) { toast("Allow pop-ups to open the speaker view"); return; }
    speakerWin = w;
    peers.push(w);
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function elapsed() { return timer.base + (timer.running ? Date.now() - timer.since : 0); }
  function saveTimer() { try { sessionStorage.setItem(KEY + ":timer", JSON.stringify(timer)); } catch (e) { /* storage may be blocked */ } }
  function tick() {
    var s = Math.floor(elapsed() / 1000);
    $("sp-elapsed").textContent = pad(Math.floor(s / 3600)) + ":" + pad(Math.floor(s / 60) % 60) + ":" + pad(s % 60);
    var d = new Date();
    $("sp-clock").textContent = pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function renderSpeaker() {
    var a = slides[cur], b = slides[cur + 1], curSlot = $("sp-cur"), nextSlot = $("sp-next");
    slides.forEach(function (s) { if (s !== a && s !== b && s.parentNode !== stage) stage.appendChild(s); });
    if (a.parentNode !== curSlot) curSlot.appendChild(a);
    if (b && b.parentNode !== nextSlot) nextSlot.appendChild(b);
    $("sp-end").hidden = !!b;
    var note = a.querySelector(".notes"), text = note ? note.textContent.trim() : "";
    var box = $("sp-notes");
    box.textContent = text || "No notes for this slide.";
    box.className = "sp-notes" + (text ? "" : " none");
    box.scrollTop = 0;
    $("sp-count").textContent = "Slide " + (cur + 1) + " of " + total;
    doc.title = "Speaker view - " + (a.getAttribute("aria-label") || "");
  }
  function initSpeaker() {
    body.classList.add("speaker-mode");
    try { var saved = JSON.parse(sessionStorage.getItem(KEY + ":timer")); if (saved && typeof saved.base === "number") timer = saved; } catch (e) { /* start fresh */ }
    if (window.opener) peers.push(window.opener);
    $("sp-toggle").textContent = timer.running ? "Pause" : "Resume";
    setInterval(tick, 500);
    tick();
    post({ k: "hello" });
  }
  function setNotesSize(d) {
    notesSize = Math.max(12, Math.min(64, notesSize + d));
    $("sp-notes").style.fontSize = notesSize + "px";
  }

  /* ---- keeping the two windows in step: BroadcastChannel, localStorage and postMessage -- */
  function post(msg) {
    msg.from = me;
    msg.id = me + ":" + (++seq);
    if (chan) { try { chan.postMessage(msg); } catch (e) { /* channel closed */ } }
    // Writing then removing the key still raises a storage event in the other window and leaves nothing behind.
    try { localStorage.setItem(KEY, JSON.stringify(msg)); localStorage.removeItem(KEY); } catch (e) { /* storage may be blocked */ }
    peers = peers.filter(function (w) { return w && !w.closed; });
    peers.forEach(function (w) { try { w.postMessage({ vixl: KEY, msg: msg }, "*"); } catch (e) { /* window gone */ } });
  }
  function receive(m) {
    if (!m || m.from === me || !m.id || seen.indexOf(m.id) >= 0) return;
    seen.push(m.id);
    if (seen.length > 60) seen.shift();
    if (m.k === "go" && typeof m.n === "number") go(m.n, { silent: true });
    else if (m.k === "blank") applyBlank(m.mode);
    else if (m.k === "hello" && !isSpeaker) { post({ k: "go", n: cur }); post({ k: "blank", mode: blank }); }
  }
  try {
    if (window.BroadcastChannel) {
      chan = new BroadcastChannel(KEY);
      chan.onmessage = function (e) { receive(e.data); };
    }
  } catch (e) { chan = null; }
  window.addEventListener("storage", function (e) {
    if (e.key !== KEY || !e.newValue) return;
    try { receive(JSON.parse(e.newValue)); } catch (x) { /* not ours */ }
  });
  window.addEventListener("message", function (e) {
    var d = e.data;
    if (!d || d.vixl !== KEY) return;
    if (e.source && e.source !== window && peers.indexOf(e.source) < 0) peers.push(e.source);
    receive(d.msg);
  });

  /* ---- input -------------------------------------------------------------------------- */
  function act(name) {
    if (name === "prev") step(-1);
    else if (name === "next") step(1);
    else if (name === "overview") setOverview(!overview);
    else if (name === "fullscreen") fullscreen();
    else if (name === "speaker") openSpeaker();
    else if (name === "help") toggleHelp();
    else if (name === "timer") {
      timer = timer.running ? { running: false, base: elapsed(), since: 0 } : { running: true, base: timer.base, since: Date.now() };
      $("sp-toggle").textContent = timer.running ? "Pause" : "Resume";
      saveTimer(); tick();
    } else if (name === "reset") {
      timer = { running: timer.running, base: 0, since: Date.now() };
      saveTimer(); tick();
    } else if (name === "smaller") setNotesSize(-2);
    else if (name === "larger") setNotesSize(2);
  }
  doc.addEventListener("click", function (e) {
    var t = e.target;
    if (!t.closest) return;
    var b = t.closest("[data-act]");
    if (b) { act(b.getAttribute("data-act")); return; }
    if (t.closest("#help") && t === $("help")) { toggleHelp(); return; }
    if (!t.closest("#stage")) return;
    if (overview) {
      var s = t.closest(".slide");
      if (s) { go(slides.indexOf(s)); setOverview(false); }
      return;
    }
    if (swiped) return;
    var z = t.closest("[data-go]");
    if (z) step(z.getAttribute("data-go") === "prev" ? -1 : 1);
  });

  var sx = null, sy = 0, st = 0;
  stage.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse" || overview) return;
    sx = e.clientX; sy = e.clientY; st = Date.now();
  });
  stage.addEventListener("pointerup", function (e) {
    if (sx === null) return;
    var dx = e.clientX - sx, dy = e.clientY - sy;
    sx = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - st < 900) {
      swiped = true;
      setTimeout(function () { swiped = false; }, 350);
      step(dx < 0 ? 1 : -1);
    }
  });
  stage.addEventListener("pointercancel", function () { sx = null; });

  function armDigits() {
    clearTimeout(digitTimer);
    digitTimer = setTimeout(function () { digits = ""; }, 3000);
  }
  doc.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var k = e.key, t = e.target;
    if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
    if (t && t.tagName === "BUTTON" && (k === " " || k === "Enter")) return;
    if (t && t.id === "sp-notes" && /^(ArrowUp|ArrowDown|PageUp|PageDown|Home|End| )$/.test(k)) return;
    if (/^[0-9]$/.test(k)) {
      digits = (digits + k).slice(-4);
      toast("Go to slide " + digits + " (press Enter)");
      armDigits();
      e.preventDefault();
      return;
    }
    if (k === "Enter" && digits) {
      var n = parseInt(digits, 10) - 1;
      digits = "";
      go(n);
      if (overview) setOverview(false);
      e.preventDefault();
      return;
    }
    if (k !== "Shift") digits = "";
    var handled = true;
    switch (k) {
      case "ArrowRight": case "PageDown": case "n": case "N": step(1); break;
      case "ArrowDown": if (overview) step(columns()); else step(1); break;
      case "ArrowLeft": case "PageUp": case "p": case "P": case "Backspace": step(-1); break;
      case "ArrowUp": if (overview) step(-columns()); else step(-1); break;
      case " ": case "Enter":
        if (overview && !e.shiftKey) setOverview(false); else step(e.shiftKey ? -1 : 1);
        break;
      case "Home": go(0); break;
      case "End": go(total - 1); break;
      case "o": case "O": setOverview(!overview); break;
      case "Escape":
        if (!$("help").hidden) toggleHelp();
        else if (blank) toggleBlank(blank);
        else if (overview) setOverview(false);
        else handled = false;
        break;
      case "f": case "F": fullscreen(); break;
      case "b": case "B": case ".": toggleBlank("b"); break;
      case "w": case "W": toggleBlank("w"); break;
      case "s": case "S": openSpeaker(); break;
      case "?": case "h": case "H": toggleHelp(); break;
      case "+": case "=": if (isSpeaker) setNotesSize(2); else handled = false; break;
      case "-": case "_": if (isSpeaker) setNotesSize(-2); else handled = false; break;
      default: handled = false;
    }
    if (handled) e.preventDefault();
  });

  function wake() {
    body.classList.remove("idle");
    clearTimeout(idleTimer);
    if (!isSpeaker) idleTimer = setTimeout(function () { if (!overview) body.classList.add("idle"); }, 2500);
  }
  doc.addEventListener("mousemove", wake, { passive: true });
  doc.addEventListener("pointerdown", wake, { passive: true });

  /* ---- start -------------------------------------------------------------------------- */
  var first = hashIndex();
  if (first < 0) first = clamp(parseInt(root.getAttribute("data-start") || "1", 10) - 1);
  if (isSpeaker) initSpeaker();
  go(first, { instant: true, silent: true, force: true });
  wake();
})();
"""
