"""The lab's local web app: one page plus a small JSON API, bound to 127.0.0.1.

Requests must name a local host (a guard against DNS rebinding) and every ``/api`` call must carry the per-launch
token embedded in the page, so another site open in your browser cannot start runs on your key. Files the models
made are served with a sandbox Content-Security-Policy, so model-written HTML runs without access to the lab.
"""

import hmac
import os
from pathlib import Path
import secrets
import time

from . import arms, previews, sandbox
from .providers import PRESETS, ProviderConfig, ProviderError
from .runner import Lab

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
FILE_HEADERS = {"Content-Security-Policy": "sandbox allow-scripts", "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store"}


def host_name(header):
    header = (header or "").strip().lower()
    if header.startswith("["):
        return header.split("]")[0] + "]"
    return header.split(":")[0]


def create_app(root, chat_factory=None, token=None):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

    lab = Lab(root, **({"chat_factory": chat_factory} if chat_factory else {}))
    token = token or secrets.token_urlsafe(24)
    app = FastAPI(title="Vixl Lab", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lab, app.state.token = lab, token

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if host_name(request.headers.get("host")) not in LOCAL_HOSTS:
            return JSONResponse({"error": "the lab only answers on localhost"}, status_code=403)
        if request.url.path.startswith("/api/"):
            sent = request.headers.get("x-lab-token", "")
            if not hmac.compare_digest(sent.encode(), token.encode()):
                return JSONResponse({"error": "missing or wrong lab token; reload the page"}, status_code=403)
        return await call_next(request)

    def fail(status, message):
        raise HTTPException(status_code=status, detail=message)

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        return page.replace("__LAB_TOKEN__", token)

    @app.get("/static/{name}")
    def static(name: str):
        path = STATIC / name
        if "/" in name or "\\" in name or not path.is_file():
            fail(404, "not found")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.get("/api/config")
    def config():
        providers = {name: {"label": p["label"], "kind": p["kind"], "base_url": p["base_url"],
                            "key_required": p["key_required"], "env": p["env"],
                            "suggestions": p.get("suggestions", []), "key_known": lab.key_known(name)}
                     for name, p in PRESETS.items()}
        return {"providers": providers, "arms": arms.ARMS,
                "capabilities": {"render_html": previews.playwright_available(),
                                 "network_isolation": bool(sandbox.network_isolation()),
                                 "python_libraries": sandbox.installed_libraries(),
                                 "skill": arms.SKILL.is_file()},
                "results": str(lab.root)}

    @app.post("/api/models")
    async def models(request: Request):
        data = await request.json()
        provider = data.get("provider")
        if provider not in PRESETS:
            fail(400, "unknown provider")
        try:
            key = lab.resolve_key(provider, data.get("base_url", ""), data.get("api_key", ""))
            chat = lab.chat_factory(ProviderConfig(provider=provider, model="", base_url=data.get("base_url", ""),
                                                   api_key=key))
            return {"models": chat.list_models()}
        except (ValueError, ProviderError) as exc:
            fail(400, str(exc))

    @app.post("/api/runs")
    async def start(request: Request):
        data = await request.json()
        key = data.pop("api_key", "") or ""
        try:
            return {"run_id": lab.start(data, key)}
        except (ValueError, TypeError) as exc:
            fail(400, str(exc))

    @app.get("/api/runs")
    def runs():
        return {"runs": lab.store.runs()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        found = lab.store.run(run_id)
        if found is None:
            fail(404, "no such run")
        found["judging"] = run_id in lab.judging
        found["busy"] = lab.busy(run_id)
        return found

    @app.post("/api/runs/{run_id}/rounds")
    async def follow_up(run_id: str, request: Request):
        data = await request.json()
        try:
            return {"round": lab.follow_up(run_id, data.get("prompt", ""), data.get("api_key", "") or "")}
        except KeyError:
            fail(404, "no such run")
        except ValueError as exc:
            fail(400, str(exc))

    @app.get("/api/sessions/{session_id}/events")
    def events(session_id: str, since: int = 0):
        return {"events": lab.session_events(session_id, max(0, since))}

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str):
        lab.cancel(run_id)
        return {"ok": True}

    @app.delete("/api/runs/{run_id}")
    def delete(run_id: str):
        try:
            lab.delete(run_id)
        except KeyError:
            fail(404, "no such run")
        except ValueError as exc:
            fail(409, str(exc))
        return {"ok": True}

    @app.post("/api/runs/{run_id}/votes")
    async def vote(run_id: str, request: Request):
        data = await request.json()
        found = lab.store.run(run_id)
        if found is None:
            fail(404, "no such run")
        repeat, winner, number = data.get("repeat"), data.get("winner"), data.get("round", 1)
        members = {s["id"] for s in found["sessions"] if s["repeat"] == repeat
                   and any(g["round"] == number for g in s["generations"])}
        if not members or (winner not in members and winner not in ("tie", "none")):
            fail(400, "winner must be a session of that repeat and round, 'tie' or 'none'")
        lab.store.vote(run_id, number, repeat, winner)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/judge")
    async def judge(run_id: str, request: Request):
        data = await request.json()
        key = data.pop("api_key", "") or ""
        try:
            return {"judging": lab.judge(run_id, data, key)}
        except KeyError:
            fail(404, "no such run")
        except ValueError as exc:
            fail(400, str(exc))

    @app.get("/api/stats")
    def stats():
        return {"rows": lab.store.stats()}

    @app.post("/api/export")
    async def export_runs(request: Request):
        from starlette.background import BackgroundTask

        from .export import build

        data = await request.json()
        try:
            path = build(lab, data.get("runs") or None)
        except ValueError as exc:
            fail(400, str(exc))
        name = f"vixl-lab-export-{time.strftime('%Y%m%d-%H%M')}.zip"
        return FileResponse(path, media_type="application/zip", filename=name,
                            background=BackgroundTask(lambda: Path(path).unlink(missing_ok=True)))

    def round_file(run_id, session_id, number, relative):
        session = lab.store.session(session_id)
        if session is None or session["run_id"] != run_id:
            fail(404, "not found")
        folder = lab.root / "runs" / run_id / session_id / "rounds" / str(number)
        try:
            path = arms.inside(folder / "files", relative) if relative is not None else folder / "preview.png"
        except arms.ToolError:
            fail(404, "not found")
        if not path.is_file():
            fail(404, "not found")
        return path

    @app.get("/files/{run_id}/{session_id}/{number}/preview.png")
    def preview(run_id: str, session_id: str, number: int):
        return FileResponse(round_file(run_id, session_id, number, None), headers=FILE_HEADERS)

    @app.get("/files/{run_id}/{session_id}/{number}/files/{relative:path}")
    def round_files(run_id: str, session_id: str, number: int, relative: str, download: int = 0):
        path = round_file(run_id, session_id, number, relative)
        headers = dict(FILE_HEADERS)
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        return FileResponse(path, headers=headers)

    return app


def serve(root, host="127.0.0.1", port=8765, open_browser=True):
    import threading
    import webbrowser

    import uvicorn

    if host_name(host) not in LOCAL_HOSTS:
        raise SystemExit("the lab holds your API keys in memory and only listens on localhost")
    app = create_app(root)
    url = f"http://{'localhost' if host == '127.0.0.1' else host}:{port}/"
    print(f"Vixl Lab: {url}  (results in {Path(root).resolve()}; Ctrl+C stops it)")
    if not previews.playwright_available():
        print("  Playwright is not installed: HTML and SVG cannot be rendered for previews or the code-tools arm.")
    if not sandbox.network_isolation():
        print("  Python in the code-tools arm runs with network access (no unshare on this system).")
    if open_browser and not os.environ.get("VIXL_LAB_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
