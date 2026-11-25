"""The comparison lab (evals/lab): provider adapters, arms, sandbox, runs, votes, judging and the local web app.

No test calls a real model: OpenAI-compatible providers get an httpx MockTransport that plays a scripted model, and
the Anthropic adapter gets a scripted client.
"""

import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from evals.lab import arms, previews, sandbox  # noqa: E402
from evals.lab.providers import (  # noqa: E402
    AnthropicChat, Call, OpenAIChat, ProviderConfig, ProviderError, function_schema, redact,
)
from evals.lab.runner import Lab, RunSpec  # noqa: E402

SECRET = "sk-test-SECRET-key-1234567890"
PNG_SCRIPT = ("from PIL import Image, ImageDraw\nimage = Image.new('RGB', (200, 120), '#203040')\n"
              "ImageDraw.Draw(image).rectangle((20, 20, 180, 100), fill='#f0b030')\nimage.save('card.png')\n"
              "print('saved')\n")


def tool_call(name, arguments, n=0):
    return {"id": f"call_{name}_{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


SCRIPTS = {
    "no tools": [
        {"content": "Here it is.\n```svg poster.svg\n<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'>"
                    "<rect width='120' height='80' fill='#e04040'/></svg>\n```\nDone."},
    ],
    "run_python": [
        {"content": "", "tool_calls": [tool_call("run_python", {"code": PNG_SCRIPT})]},
        {"content": "", "tool_calls": [tool_call("view_image", {"path": "card.png"}, 1)]},
        {"content": "Saved card.png."},
    ],
    "vixl_": [
        {"content": "", "tool_calls": [tool_call("vixl_document", {"action": "create", "path": "card.vixl",
                                                                   "width": 320, "height": 200,
                                                                   "background": "#1c2733"})]},
        {"content": "", "tool_calls": [tool_call("vixl_apply", {"operations": [
            {"type": "text", "name": "title", "text": "Hello", "size": 48, "x": 24, "y": 60, "color": "#ffffff"}]}),
            tool_call("not_a_tool", {}, 1)]},
        {"content": "", "tool_calls": [tool_call("vixl_export", {"path": "card.png"})]},
        {"content": "Exported card.png."},
    ],
}


FOLLOW_UPS = {
    "no tools": [
        {"content": "Updated.\n```svg poster.svg\n<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'>"
                    "<rect width='120' height='80' fill='#2060e0'/></svg>\n```"},
    ],
    "run_python": [
        {"content": "", "tool_calls": [tool_call("run_python", {"code": PNG_SCRIPT.replace("#f0b030", "#30b0f0")}, 5)]},
        {"content": "Recoloured card.png."},
    ],
    "vixl_": [
        {"content": "", "tool_calls": [tool_call("vixl_document", {"action": "open", "path": "card.vixl"}, 5)]},
        {"content": "", "tool_calls": [tool_call("vixl_apply", {"operations": [
            {"type": "text", "name": "subtitle", "text": "Again", "size": 24, "x": 24, "y": 140,
             "color": "#ffd166"}]}, 6)]},
        {"content": "", "tool_calls": [tool_call("vixl_export", {"path": "card.png", "overwrite": True}, 7)]},
        {"content": "Added a subtitle."},
    ],
}


def position(messages):
    """(round, turn): which user prompt the conversation is answering and how many replies it already has."""
    prompts = [i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str)]
    last = prompts[-1]
    return len(prompts), sum(m["role"] == "assistant" for m in messages[last:])


class ScriptedServer:
    """An OpenAI-compatible server: picks the script by the arm's system prompt, one reply per assistant turn."""

    def __init__(self, scripts=SCRIPTS):
        self.scripts, self.requests = scripts, []

    def __call__(self, request):
        assert request.headers.get("authorization") == f"Bearer {SECRET}"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "fake-b"}, {"id": "fake-a"}]})
        body = json.loads(request.content)
        self.requests.append(body)
        system = body["messages"][0]["content"]
        if "Score the design" in json.dumps(body["messages"][-1]):
            reply = {"content": json.dumps({"scores": {k: 4 for k in
                                                       ("hierarchy", "spacing", "type", "colour", "motif", "finish")},
                                            "notes": "Fine."})}
        else:
            key = next(k for k in self.scripts if k in system)
            number, turn = position(body["messages"])
            reply = (self.scripts if number == 1 else FOLLOW_UPS)[key][turn]
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", **reply},
                         "finish_reason": "tool_calls" if reply.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40}}})


def factory(server):
    def make(config):
        return OpenAIChat(config, http=httpx.Client(transport=httpx.MockTransport(server)), sleep=lambda _: None)
    return make


def spec(**overrides):
    return {"prompt": "Make a small card.", "provider": "openai", "model": "fake-model", "arms": ["bare", "code", "vixl"],
            "repeats": 1, "price_in": 1.0, "price_out": 2.0, **overrides}


@pytest.fixture
def lab(tmp_path):
    server = ScriptedServer()
    instance = Lab(tmp_path / "results", chat_factory=factory(server))
    instance.server = server
    return instance


# --- a whole run ------------------------------------------------------------------------------------------------

def test_a_run_drives_every_arm_in_its_own_session(lab):
    run_id = lab.start(spec(), SECRET)
    lab.wait(run_id, 120)
    run = lab.store.run(run_id)
    assert run["status"] == "done"
    sessions = {s["arm"]: s for s in run["sessions"]}
    assert set(sessions) == {"bare", "code", "vixl"}
    first = {arm: session["generations"][0] for arm, session in sessions.items()}
    for arm, generation in first.items():
        assert generation["status"] == "done", (arm, generation["error"])
    # SVG previews need a browser; without one the note says why and the page shows the SVG itself.
    bare = first["bare"]
    assert bare["preview"] == "poster.svg" or bare["preview_note"].startswith("poster.svg:")
    assert first["code"]["preview"] == "card.png"
    assert first["vixl"]["preview"] == "card.png"
    assert {c["path"] for c in first["vixl"]["changed"]} == {"card.png", "card.vixl"}
    vixl = first["vixl"]["metrics"]
    assert vixl["tool_calls"] == 4 and vixl["tool_errors"] == 1 and vixl["turns"] == 4
    assert vixl["input"] == 4 * 60 and vixl["cache_read"] == 4 * 40 and vixl["output"] == 4 * 20
    assert vixl["cost"] == pytest.approx((240 + 16) * 1.0 / 1e6 + 80 * 2.0 / 1e6, abs=1e-5)
    # Each session's workspace is its own; the bare reply was saved as a file.
    root = lab.root / "runs" / run_id
    assert (root / sessions["bare"]["id"] / "workspace" / "poster.svg").is_file()
    assert (root / sessions["bare"]["id"] / "rounds" / "1" / "files" / "poster.svg").is_file()
    assert (root / sessions["vixl"]["id"] / "system-prompt.txt").read_text().startswith(arms.BASE_SYSTEM)
    assert not (root / sessions["code"]["id"] / "workspace" / "card.vixl").exists()
    events = lab.session_events(sessions["code"]["id"])
    assert [e["kind"] for e in events][0] == "status" and any(e["kind"] == "tool" for e in events)


def test_arms_differ_only_in_their_tools_and_tool_paragraph(lab):
    lab.wait(lab.start(spec(), SECRET), 120)
    firsts = {}
    for body in lab.server.requests:
        if sum(m["role"] == "assistant" for m in body["messages"]) == 0:
            firsts[body["messages"][0]["content"]] = body
    assert len(firsts) == 3
    systems = [b["messages"][0]["content"] for b in firsts.values()]
    assert all(s.startswith(arms.BASE_SYSTEM) for s in systems)
    assert {b["messages"][1]["content"] for b in firsts.values()} == {"Make a small card."}
    tools = {tuple(sorted(t["function"]["name"] for t in b.get("tools", []))) for b in firsts.values()}
    assert () in tools
    assert any("run_python" in names and not any(n.startswith("vixl_") for n in names) for names in tools)
    assert any("vixl_apply" in names and "run_python" not in names for names in tools)


def test_api_keys_are_never_written_to_disk(lab, tmp_path):
    lab.wait(lab.start(spec(), SECRET), 120)
    for path in lab.root.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path


def test_images_from_tools_reach_openai_models_in_a_user_message(lab):
    lab.wait(lab.start(spec(arms=["code"]), SECRET), 120)
    last = lab.server.requests[-1]["messages"]
    tool_messages = [m for m in last if m["role"] == "tool"]
    assert all(isinstance(m["content"], str) for m in tool_messages)
    image_messages = [m for m in last if m["role"] == "user" and isinstance(m["content"], list)]
    assert image_messages and image_messages[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_off_sends_no_images(lab):
    lab.wait(lab.start(spec(arms=["code"], vision=False), SECRET), 120)
    text = json.dumps(lab.server.requests[-1])
    assert "image_url" not in text and "image input is turned off" in text


def test_votes_judging_and_the_scoreboard(lab):
    run_id = lab.start(spec(repeats=2, arms=["code", "vixl"]), SECRET)
    lab.wait(run_id, 120)
    run = lab.store.run(run_id)
    winner = next(s["id"] for s in run["sessions"] if s["repeat"] == 0 and s["arm"] == "vixl")
    lab.store.vote(run_id, 1, 0, winner)
    lab.store.vote(run_id, 1, 1, "tie")
    assert lab.judge(run_id, {}, "") == 4
    for _ in range(200):
        if run_id not in lab.judging:
            break
        import time
        time.sleep(0.05)
    run = lab.store.run(run_id)
    assert all(g["judgments"][0]["mean"] == 4.0 for s in run["sessions"] for g in s["generations"])
    rows = {row["arm"]: row for row in lab.store.stats()}
    assert rows["vixl"]["wins"] == 1 and rows["vixl"]["votes"] == 2
    assert rows["code"]["wins"] == 0 and rows["code"]["votes"] == 2
    assert rows["vixl"]["judge_mean"] == 4.0 and rows["vixl"]["delivered"] == 2


def test_a_failed_model_call_is_recorded_with_the_key_removed(tmp_path):
    def refuse(request):
        return httpx.Response(401, text=f"bad key {SECRET}")

    lab = Lab(tmp_path, chat_factory=factory(refuse))
    run_id = lab.start(spec(arms=["bare"]), SECRET)
    lab.wait(run_id, 60)
    generation = lab.store.run(run_id)["sessions"][0]["generations"][0]
    assert generation["status"] == "failed" and "HTTP 401" in generation["error"]
    assert SECRET not in generation["error"]


def test_turn_limit_and_cancel(lab):
    run_id = lab.start(spec(arms=["vixl"], max_turns=2), SECRET)
    lab.wait(run_id, 120)
    assert lab.store.run(run_id)["sessions"][0]["generations"][0]["status"] == "turn limit"
    lab.cancel("later")
    assert lab.cancelled("later")


def test_run_spec_validation():
    with pytest.raises(ValueError, match="prompt"):
        RunSpec.parse(spec(prompt=" "))
    with pytest.raises(ValueError, match="arm"):
        RunSpec.parse(spec(arms=["photoshop"]))
    with pytest.raises(ValueError, match="provider"):
        RunSpec.parse(spec(provider="nope"))
    parsed = RunSpec.parse(spec(repeats=99, arms=["vixl", "bare"]))
    assert parsed.repeats == 10 and parsed.arms == ["bare", "vixl"]


def test_keys_come_from_the_form_memory_or_the_environment(tmp_path, monkeypatch):
    lab = Lab(tmp_path)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MOONSHOT_API_KEY"):
        lab.resolve_key("moonshot", "", "")
    monkeypatch.setenv("MOONSHOT_API_KEY", "from-env")
    assert lab.resolve_key("moonshot", "", "") == "from-env"
    assert lab.resolve_key("moonshot", "", "typed") == "typed"
    assert lab.resolve_key("moonshot", "", "") == "typed"  # remembered for this process
    assert lab.resolve_key("ollama", "", "") == ""  # local servers need none


# --- adapters ---------------------------------------------------------------------------------------------------

def test_openai_adapter_keeps_reasoning_content_and_reports_bad_arguments():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "reasoning_content": "thinking", "annotations": [],
            "tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{broken"}}]}}]})

    chat = OpenAIChat(ProviderConfig("moonshot", "kimi", api_key="k" * 8),
                      http=httpx.Client(transport=httpx.MockTransport(handler)))
    chat.start("sys", [{"name": "x", "description": "", "input_schema": {"$schema": "s", "type": "object"}}])
    assert chat.tools[0]["function"]["parameters"] == {"type": "object", "properties": {}}
    chat.add_user([{"type": "text", "text": "hi"}])
    turn = chat.step()
    assert turn.calls[0].invalid and chat.messages[-1] == {
        "role": "assistant", "content": "", "reasoning_content": "thinking",
        "tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{broken"}}]}


def test_openai_uses_max_completion_tokens_and_others_max_tokens():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]})

    for provider in ("openai", "meta"):
        chat = OpenAIChat(ProviderConfig(provider, "m", max_tokens=999, effort="low"),
                          http=httpx.Client(transport=httpx.MockTransport(handler)))
        chat.start("s", [])
        chat.add_user([{"type": "text", "text": "x"}])
        chat.step()
    assert seen[0]["max_completion_tokens"] == 999 and "max_tokens" not in seen[0]
    assert seen[1]["max_tokens"] == 999 and seen[1]["reasoning_effort"] == "low" and "tools" not in seen[1]


def test_openai_retries_overload_then_reports():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="busy")

    chat = OpenAIChat(ProviderConfig("ollama", "m"), http=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=lambda _: None)
    chat.start("s", [])
    chat.add_user([{"type": "text", "text": "x"}])
    with pytest.raises(ProviderError, match="HTTP 503"):
        chat.step()
    assert len(calls) == 4


def test_model_listing_through_the_app(tmp_path):
    from fastapi.testclient import TestClient
    from evals.lab.server import create_app

    app = create_app(tmp_path, chat_factory=factory(ScriptedServer()), token="t")
    client = TestClient(app, base_url="http://localhost")
    reply = client.post("/api/models", json={"provider": "moonshot", "api_key": SECRET}, headers={"X-Lab-Token": "t"})
    assert reply.status_code == 200 and reply.json()["models"] == ["fake-a", "fake-b"]


class FakeMessages:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def create(self, **arguments):
        self.requests.append(arguments)
        return self.replies.pop(0)


def test_anthropic_adapter_appends_turns_unchanged_and_batches_results():
    reply = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="tool_use", id="t1", name="view_image", input={"path": "a.png"})],
        usage=SimpleNamespace(input_tokens=5, output_tokens=3, cache_read_input_tokens=2,
                              cache_creation_input_tokens=1), stop_reason="tool_use")
    messages = FakeMessages([reply])
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))
    chat = AnthropicChat(ProviderConfig("anthropic", "claude-haiku-5-5", effort="low", vision=False), client=client)
    chat.start("sys", [{"name": "view_image", "description": "d", "input_schema": {"type": "object"}}])
    chat.add_user([{"type": "text", "text": "go"}])
    turn = chat.step()
    request = messages.requests[0]
    assert request["output_config"] == {"effort": "low"} and request["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in request
    assert turn.calls[0].name == "view_image" and turn.usage == {"input": 5, "output": 3, "cache_read": 2,
                                                                  "cache_write": 1}
    assert chat.messages[-1]["content"] is reply.content
    chat.add_results([(turn.calls[0], False, [{"type": "image", "media_type": "image/png", "data": "AA=="}])])
    result = chat.messages[-1]["content"][0]
    assert result["type"] == "tool_result" and result["content"][0]["type"] == "text"  # vision off


def test_anthropic_fallback_models_use_the_server_side_fallback():
    reply = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")],
                            usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason="end_turn")
    plain, beta = FakeMessages([]), FakeMessages([reply])
    chat = AnthropicChat(ProviderConfig("anthropic", "claude-opus-5-5"),
                         client=SimpleNamespace(messages=plain, beta=SimpleNamespace(messages=beta)))
    chat.start("s", [])
    chat.add_user([{"type": "text", "text": "x"}])
    assert chat.step().text == "hi"
    assert beta.requests[0]["fallbacks"] == "default" and "tools" not in beta.requests[0]


def test_redact_and_schema_helpers():
    assert redact(f"Bearer {SECRET} failed", SECRET) == "Bearer *** failed"
    assert redact("short", "abc") == "short"
    assert function_schema(None) == {"type": "object", "properties": {}}


# --- arms -------------------------------------------------------------------------------------------------------

def test_bare_replies_become_files(tmp_path):
    reply = ("```svg logo.svg\n<svg/>\n```\n```html\n<p>hi</p>\n```\n```html\n<p>2</p>\n```\n"
             "```python\nprint(1)\n```\n```md ../../escape.md\n# x\n```")
    written = arms.extract_files(reply, tmp_path)
    assert written == ["logo.svg", "output.html", "output-2.html", "escape.md"]
    assert not (tmp_path.parent.parent / "escape.md").exists()


def test_bare_loose_svg_is_saved(tmp_path):
    assert arms.extract_files("Sure: <svg width='1'><rect/></svg> there.", tmp_path) == ["output.svg"]


def test_file_tools_stay_in_the_workspace(tmp_path):
    files = arms.FileTools(tmp_path)
    with pytest.raises(arms.ToolError, match="outside"):
        files.call("write_file", {"path": "../evil.txt", "content": "x"})
    files.call("write_file", {"path": "a/b.svg", "content": "<svg/>"})
    assert (tmp_path / "a" / "b.svg").read_text() == "<svg/>"
    assert "a/b.svg" in files.call("list_files", {})[0]["text"]
    assert files.call("read_file", {"path": "a/b.svg"})[0]["text"] == "<svg/>"


def test_view_image_returns_a_scaled_png(tmp_path):
    from PIL import Image

    Image.new("RGB", (3000, 1500), "red").save(tmp_path / "big.png")
    blocks = arms.FileTools(tmp_path).call("view_image", {"path": "big.png"})
    image = Image.open(io.BytesIO(base64.b64decode(blocks[0]["data"])))
    assert max(image.size) == previews.MODEL_SIDE and "3000x1500" in blocks[1]["text"]


def test_toolbox_never_raises(tmp_path):
    box = arms.build("code", tmp_path / "w", tmp_path / "s")
    (tmp_path / "w").mkdir()
    failed, blocks = box.call("read_file", {"path": "missing.txt"})
    assert failed and "no file" in blocks[0]["text"]
    failed, blocks = box.call("vixl_apply", {})
    assert failed and "no tool named" in blocks[0]["text"]


def test_vixl_arm_system_prompt_carries_the_server_instructions_and_skill(tmp_path):
    box = arms.build("vixl", tmp_path, tmp_path / "s", skill=True)
    try:
        assert "vixl_document" in box.system and "# Vixl for agents" in box.system
    finally:
        box.close()
    box = arms.build("vixl", tmp_path, tmp_path / "s", skill=False)
    try:
        assert "# Vixl for agents" not in box.system
    finally:
        box.close()


# --- sandbox ----------------------------------------------------------------------------------------------------

def test_python_runs_in_the_workspace_without_keys_or_vixl(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    workspace = tmp_path / "w"
    workspace.mkdir()
    code = ("import os\nprint(os.environ.get('OPENAI_API_KEY'))\nopen('out.txt', 'w').write('x')\n"
            "try:\n    import vixl\nexcept ImportError as e:\n    print('blocked', e)\n")
    failed, output = sandbox.run_python(code, workspace, tmp_path / "s")
    assert not failed and "None" in output and "blocked" in output and SECRET not in output
    assert "out.txt" in output and (workspace / "out.txt").read_text() == "x"
    assert not list(workspace.glob("*.py"))


def test_python_time_limit(tmp_path):
    workspace = tmp_path / "w"
    workspace.mkdir()
    failed, output = sandbox.run_python("import time\ntime.sleep(30)", workspace, tmp_path / "s", timeout=1)
    assert failed and "time limit" in output


@pytest.mark.skipif(not sandbox.network_isolation(), reason="no unshare on this system")
def test_python_has_no_network_where_isolation_works(tmp_path):
    workspace = tmp_path / "w"
    workspace.mkdir()
    code = "import socket\ns = socket.socket()\ns.settimeout(3)\ns.connect(('1.1.1.1', 80))\nprint('connected')"
    failed, output = sandbox.run_python(code, workspace, tmp_path / "s")
    assert failed and "connected" not in output.split("stderr")[0]


# --- the web app ------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from evals.lab.server import create_app

    app = create_app(tmp_path, chat_factory=factory(ScriptedServer()), token="tok")
    test_client = TestClient(app, base_url="http://localhost:8765")
    test_client.headers["X-Lab-Token"] = "tok"
    test_client.lab = app.state.lab
    return test_client


def test_page_carries_the_token_and_api_needs_it(client):
    page = client.get("/")
    assert page.status_code == 200 and 'content="tok"' in page.text
    assert client.get("/api/config").json()["providers"]["meta"]["base_url"] == "https://api.meta.ai/v1"
    assert client.get("/api/config", headers={"X-Lab-Token": "wrong"}).status_code == 403


def test_other_hosts_are_refused(client):
    assert client.get("/", headers={"Host": "evil.example:8765"}).status_code == 403
    assert client.get("/", headers={"Host": "127.0.0.1:8765"}).status_code == 200


def test_run_through_the_api_and_files_are_sandboxed(client):
    run_id = client.post("/api/runs", json={**spec(arms=["code"]), "api_key": SECRET}).json()["run_id"]
    client.lab.wait(run_id, 120)
    run = client.get(f"/api/runs/{run_id}").json()
    session = run["sessions"][0]
    assert session["status"] == "done" and "api_key" not in json.dumps(run["spec"])
    preview = client.get(f"/files/{run_id}/{session['id']}/1/preview.png")
    assert preview.status_code == 200 and preview.headers["content-security-policy"].startswith("sandbox")
    assert client.get(f"/files/{run_id}/{session['id']}/1/files/card.png").status_code == 200
    assert client.get(f"/files/{run_id}/{session['id']}/1/files/..%2F..%2F..%2F..%2Flab.db").status_code == 404
    assert client.get(f"/files/{run_id}/{session['id']}/2/preview.png").status_code == 404
    assert client.get(f"/api/sessions/{session['id']}/events").json()["events"]
    assert client.post(f"/api/runs/{run_id}/votes", json={"repeat": 0, "winner": "someone"}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/votes", json={"repeat": 0, "winner": session["id"]}).status_code == 200
    assert client.get("/api/stats").json()["rows"][0]["wins"] == 1
    assert client.get("/api/runs").json()["runs"][0]["votes"] == 1
    assert client.delete(f"/api/runs/{run_id}").status_code == 200
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_bad_run_requests_are_400(client, monkeypatch):
    assert client.post("/api/runs", json={**spec(prompt=""), "api_key": SECRET}).status_code == 400
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reply = client.post("/api/runs", json=spec(provider="anthropic"))
    assert reply.status_code == 400 and "ANTHROPIC_API_KEY" in reply.json()["detail"]


def test_call_dataclass_defaults():
    assert Call("1", "x", {}).invalid == ""


# --- follow-up rounds -------------------------------------------------------------------------------------------

def finished(lab, run_id):
    lab.wait(run_id, 120)
    return lab.store.run(run_id)


def test_a_follow_up_continues_every_session_in_its_own_workspace(lab):
    run_id = lab.start(spec(), SECRET)
    finished(lab, run_id)
    assert lab.follow_up(run_id, "Make it blue.") == 2
    run = finished(lab, run_id)
    assert [r["prompt"] for r in run["rounds"]] == ["Make a small card.", "Make it blue."]
    for session in run["sessions"]:
        second = session["generations"][1]
        assert second["round"] == 2 and second["status"] == "done", (session["arm"], second["error"])
    second = {s["arm"]: s["generations"][1] for s in run["sessions"]}
    assert second["code"]["changed"] == [{"path": "card.png", "change": "modified"}]
    assert {"path": "card.png", "change": "modified"} in second["vixl"]["changed"]
    assert second["bare"]["changed"] == [{"path": "poster.svg", "change": "modified"}]
    # The follow-up went into the same conversation: the brief and the first round's replies came with it.
    followups = [b for b in lab.server.requests if position(b["messages"])[0] == 2]
    assert followups and all(b["messages"][1]["content"] == "Make a small card." for b in followups)
    # Each round keeps its own snapshot: round 1's card is still the original.
    code = next(s for s in run["sessions"] if s["arm"] == "code")
    rounds = lab.root / "runs" / run_id / code["id"] / "rounds"
    assert (rounds / "1" / "files" / "card.png").read_bytes() != (rounds / "2" / "files" / "card.png").read_bytes()
    events = lab.session_events(code["id"])
    assert {e["round"] for e in events} == {1, 2}


def test_follow_ups_survive_a_restart(tmp_path):
    server = ScriptedServer()
    first = Lab(tmp_path, chat_factory=factory(server))
    run_id = first.start(spec(arms=["code", "vixl"]), SECRET)
    finished(first, run_id)
    for session in first.live.values():
        session.close()
    restarted = Lab(tmp_path, chat_factory=factory(server))
    with pytest.raises(ValueError, match="API key"):
        restarted.follow_up(run_id, "Make it blue.")
    restarted.follow_up(run_id, "Make it blue.", SECRET)
    run = finished(restarted, run_id)
    for session in run["sessions"]:
        second = session["generations"][1]
        assert second["status"] == "done" and second["metrics"]["tool_errors"] == 0, (session["arm"], second)
    notes = [e["text"] for s in run["sessions"] for e in restarted.session_events(s["id"]) if e["kind"] == "note"]
    assert any("Continued the saved conversation" in note for note in notes)


def test_follow_up_rules(lab):
    run_id = lab.start(spec(arms=["bare"]), SECRET)
    with pytest.raises(ValueError, match="empty"):
        lab.follow_up(run_id, "  ")
    finished(lab, run_id)
    with pytest.raises(KeyError):
        lab.follow_up("no-such-run", "x")


def test_votes_and_judging_are_per_round(lab):
    run_id = lab.start(spec(arms=["code", "vixl"]), SECRET)
    finished(lab, run_id)
    lab.follow_up(run_id, "Make it blue.")
    run = finished(lab, run_id)
    vixl = next(s["id"] for s in run["sessions"] if s["arm"] == "vixl")
    code = next(s["id"] for s in run["sessions"] if s["arm"] == "code")
    lab.store.vote(run_id, 1, 0, code)
    lab.store.vote(run_id, 2, 0, vixl)
    lab.judge(run_id, {"round": 2}, "")
    for _ in range(200):
        if run_id not in lab.judging:
            break
        import time
        time.sleep(0.05)
    run = lab.store.run(run_id)
    assert run["votes"] == {"1:0": code, "2:0": vixl}
    for session in run["sessions"]:
        assert not session["generations"][0]["judgments"] and session["generations"][1]["judgments"]
    rows = {row["arm"]: row for row in lab.store.stats()}
    assert rows["vixl"]["wins"] == 1 and rows["code"]["wins"] == 1 and rows["vixl"]["followups"] == 1


def test_follow_up_through_the_api(client):
    run_id = client.post("/api/runs", json={**spec(arms=["bare"]), "api_key": SECRET}).json()["run_id"]
    client.lab.wait(run_id, 60)
    assert client.post(f"/api/runs/{run_id}/rounds", json={"prompt": ""}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/rounds", json={"prompt": "Blue."}).json() == {"round": 2}
    client.lab.wait(run_id, 60)
    run = client.get(f"/api/runs/{run_id}").json()
    assert len(run["rounds"]) == 2 and run["busy"] is False
    session = run["sessions"][0]
    assert client.post(f"/api/runs/{run_id}/votes", json={"round": 3, "repeat": 0, "winner": "tie"}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/votes", json={"round": 2, "repeat": 0, "winner": "tie"}).status_code == 200
    assert client.get(f"/files/{run_id}/{session['id']}/2/files/poster.svg").status_code == 200


# --- export -----------------------------------------------------------------------------------------------------

def test_export_holds_every_generation_and_how_it_was_made(lab, tmp_path):
    import zipfile

    from evals.lab.export import build

    run_id = lab.start(spec(), SECRET)
    finished(lab, run_id)
    lab.follow_up(run_id, "Make it blue.")
    run = finished(lab, run_id)
    winner = next(s["id"] for s in run["sessions"] if s["arm"] == "vixl")
    lab.store.vote(run_id, 2, 0, winner)
    path = build(lab, [run_id], tmp_path / "export.zip")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        top = names[0].split("/")[0]
        read = lambda name: archive.read(f"{top}/{name}").decode("utf-8")  # noqa: E731
        for name in ("index.html", "GUIDE.md", "data.json", f"runs/{run_id}/README.md"):
            assert f"{top}/{name}" in names
        for session in run["sessions"]:
            base = f"runs/{run_id}/{session['id']}"
            assert f"{top}/{base}/system-prompt.txt" in names and f"{top}/{base}/events.jsonl" in names
            for number in (1, 2):
                guide = read(f"{base}/round-{number}/how-it-was-made.md")
                assert "## Steps" in guide and "## Files after this round" in guide
        vixl = next(s for s in run["sessions"] if s["arm"] == "vixl")
        guide = read(f"runs/{run_id}/{vixl['id']}/round-2/how-it-was-made.md")
        assert "Make it blue." in guide and "Make a small card." in guide
        assert '"overwrite": true' in guide and "vixl_export" in guide and "Picked as best" in guide
        assert f"{top}/runs/{run_id}/{vixl['id']}/round-1/files/card.vixl" in names
        code = next(s for s in run["sessions"] if s["arm"] == "code")
        assert f"{top}/runs/{run_id}/{code['id']}/python/script-001.py" in names
        assert f"{top}/runs/{run_id}/{code['id']}/round-2/preview.png" in names
        assert "run_python" in read(f"runs/{run_id}/{code['id']}/round-1/how-it-was-made.md")
        report = read("index.html")
        assert "Make it blue." in report and f"runs/{run_id}/{code['id']}/round-2/preview.png" in report
        data = json.loads(read("data.json"))
        assert data["runs"][0]["id"] == run_id and len(data["runs"][0]["rounds"]) == 2
        assert "Vixl Lab export" in read("GUIDE.md")
        for name in names:
            assert SECRET.encode() not in archive.read(name), name


def test_export_through_the_api(client):
    run_id = client.post("/api/runs", json={**spec(arms=["bare"]), "api_key": SECRET}).json()["run_id"]
    client.lab.wait(run_id, 60)
    reply = client.post("/api/export", json={"runs": [run_id]})
    assert reply.status_code == 200 and reply.headers["content-type"] == "application/zip"
    assert "vixl-lab-export-" in reply.headers["content-disposition"]
    assert reply.content[:2] == b"PK"
    assert client.post("/api/export", json={"runs": ["missing"]}).status_code == 400
    assert client.post("/api/export", json={}, headers={"X-Lab-Token": "no"}).status_code == 403


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc to list open files")
def test_export_leaves_no_handle_open_on_its_temporary_file(lab):
    # Windows cannot delete a file that is still open, so the server's clean-up after sending would fail there.
    import os

    from evals.lab.export import build

    run_id = lab.start(spec(arms=["bare"]), SECRET)
    finished(lab, run_id)
    path = build(lab, [run_id])
    try:
        held = [fd for fd in os.listdir("/proc/self/fd")
                if os.path.realpath(f"/proc/self/fd/{fd}") == os.path.realpath(path)]
        assert held == []
    finally:
        path.unlink()
