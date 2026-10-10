"""Agent evaluation harness for Vixl's MCP tools.

Each task gives an agent a natural-language design brief and a fresh workspace, lets it work
through the real MCP server (in-process), then grades the resulting files with programmatic
checks. Results record success, model round trips, tool calls, tool errors and token usage, so
changes to tool descriptions, schemas, errors or responses can be measured instead of guessed.

Agents:
  reference  replays each task's scripted reference solution (offline; validates tasks + harness)
  claude     drives the tools with Claude through the official Anthropic SDK
"""

import asyncio
import os
from unittest.mock import patch
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time

from PIL import Image

TASK_DIR = Path(__file__).parent / "tasks"
SYSTEM_PROMPT = (
    "You are a design agent working through Vixl's image-editing tools in a sandboxed workspace. "
    "Complete the user's brief end to end: create or open documents, apply operations, verify the "
    "result with vixl_check and vixl_render_preview, fix problems, and export files when asked. "
    "Use workspace-relative paths. When the brief is fully done, reply with a one-line summary."
)


# --- tasks ---------------------------------------------------------------------------------------


def load_tasks(directory=TASK_DIR, pattern="*"):
    tasks = []
    for path in sorted(Path(directory).glob(f"{pattern}.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        task.setdefault("id", path.stem)
        tasks.append(task)
    return tasks


def prepare_workspace(task, workspace):
    """Create the task's starting files: generated images and pre-built documents."""
    from vixl import Project

    for name, content in task.get("setup", {}).get("files", {}).items():
        destination = (workspace / name).resolve()
        if not destination.is_relative_to(workspace.resolve()):
            raise ValueError("Eval fixture path escapes workspace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    for pairing in task.get("setup", {}).get("font_pairings", []):
        from vixl.typefaces import get_pairing, slug
        from vixl import fonts
        cache = workspace / ".font-cache"
        cache.mkdir(exist_ok=True)
        fixture = (Path(fonts.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
        for spec in (get_pairing(pairing)[role] for role in ("heading", "body")):
            (cache / f"{slug(spec['family'])}-{spec['weight']}.ttf").write_bytes(fixture)
    for spec in task.get("setup", {}).get("images", []):
        image = Image.new("RGB", (spec["width"], spec["height"]), spec.get("color", "gray"))
        if spec.get("gradient"):
            top, bottom = Image.new("RGB", image.size, spec["gradient"][0]), Image.new("RGB", image.size, spec["gradient"][1])
            mask = Image.linear_gradient("L").resize(image.size)
            image = Image.composite(bottom, top, mask)
        if spec.get("lines"):
            # A stand-in for a photographed sketch: dark pen polylines on paper.
            from PIL import ImageDraw

            draw = ImageDraw.Draw(image)
            for line in spec["lines"]:
                draw.line([tuple(point) for point in line], fill=spec.get("ink", "#222222"),
                          width=spec.get("line_width", 6), joint="curve")
        image.save(workspace / spec["path"])
    for spec in task.get("setup", {}).get("documents", []):
        project = Project(spec["width"], spec["height"], spec.get("background", "transparent"))
        for batch in spec.get("batches", []):
            project.apply(batch)
        project.save(workspace / spec["path"])


# --- grading -------------------------------------------------------------------------------------


def _matches(layer, match):
    for key, expected in match.items():
        if key == "text_contains":
            if expected.lower() not in str(layer.get("text", "")).lower():
                return False
        elif key == "min_size":
            if layer.get("size", 0) < expected:
                return False
        elif key in ("min_width", "min_height"):
            if layer.get(key[4:], 0) < expected:
                return False
        elif key == "type":
            if layer.get("type") not in (expected if isinstance(expected, list) else [expected]):
                return False
        elif key in ("field_key", "field_kind"):
            if (layer.get("field") or {}).get(key[6:]) != expected:
                return False
        elif layer.get(key) != expected:
            return False
    return True


def grade(task, workspace):
    """Run every check in ``task["checks"]``; return a list of {check, passed, detail}."""
    from vixl import Project, VixlError
    from vixl.validation import assert_rule

    results = []
    documents = {}

    def document(path):
        if path not in documents:
            documents[path] = Project.load(workspace / path)
        return documents[path]

    for check in task["checks"]:
        kind = check["type"]
        passed, detail = False, None
        try:
            if kind == "file":
                path = workspace / check["path"]
                passed = path.is_file()
                if passed and check.get("image_size"):
                    with Image.open(path) as image:
                        detail = list(image.size)
                        passed = detail == check["image_size"]
                        if check.get("image_mode"):
                            passed = passed and image.mode == check["image_mode"]
                if passed and check.get("contains"):
                    passed = check["contains"] in path.read_text(encoding="utf-8", errors="replace")
            elif kind == "files_differ":
                first, second = (workspace / path for path in check["paths"])
                passed = first.is_file() and second.is_file() and first.read_bytes() != second.read_bytes()
            elif kind == "pptx":
                from pptx import Presentation

                slides = Presentation(workspace / check["path"]).slides
                texts = " ".join(shape.text_frame.text for slide in slides for shape in slide.shapes if shape.has_text_frame)
                notes = " ".join(slide.notes_slide.notes_text_frame.text for slide in slides if slide.has_notes_slide)
                detail = {"slides": len(slides), "missing": [t for t in check.get("texts", []) if t.lower() not in texts.lower()]
                          + [t for t in check.get("notes", []) if t.lower() not in notes.lower()]}
                passed = ("slides" not in check or detail["slides"] == check["slides"]) and not detail["missing"]
            elif kind == "pdf_fields":
                import pypdf

                reader = pypdf.PdfReader(workspace / check["path"])
                fields = sorted(reader.get_fields() or {})
                detail = {"pages": len(reader.pages), "fields": fields}
                passed = set(check.get("includes", [])) <= set(fields) and (
                    "pages" not in check or len(reader.pages) == check["pages"]) and (
                    "max_fields" not in check or len(fields) <= check["max_fields"])
            else:
                project = document(check.get("document", task.get("document")))
                state = project.inspect()
                layers = state["layers"]
                if kind == "state_field":
                    detail = state
                    for key in check["field"]:
                        detail = detail[key]
                    passed = detail == check["equals"]
                elif kind == "animated":
                    # The layer has a timeline track (for ``property`` when given) whose values change.
                    target = project.layer(check["layer"])["id"]
                    tracks = [t for t in state.get("timeline", {}).get("tracks", []) if t["target"] == target
                              and check.get("property") in (None, t["property"])]
                    detail = [t["property"] for t in tracks]
                    passed = any(len({json.dumps(k["value"]) for k in t["keys"]}) > 1 for t in tracks)
                elif kind == "pixel":
                    # The rendered document at one point: alpha_max (see-through) or alpha_min (painted).
                    detail = list(project.render().convert("RGBA").getpixel(tuple(check["at"])))
                    passed = detail[3] <= check.get("alpha_max", 255) and detail[3] >= check.get("alpha_min", 0)
                elif kind == "canvas":
                    detail = [state["canvas"]["width"], state["canvas"]["height"]]
                    passed = detail == [check["width"], check["height"]]
                elif kind == "layer":
                    found = [x for x in layers if _matches(x, check.get("match", {}))]
                    detail = [x["name"] for x in found]
                    passed = len(found) >= check.get("min", 1) and len(found) <= check.get("max", 10**6)
                    region = check.get("within")
                    if passed and region:
                        x, y, w, h = region
                        passed = any(
                            b[0] >= x and b[1] >= y and b[0] + b[2] <= x + w and b[1] + b[3] <= y + h
                            for b in (layer["resolved_bounds"] for layer in found)
                        )
                elif kind == "design":
                    report = project.check(**check.get("options", {}))
                    # forbid: issue codes that fail the check whatever their severity (a loop seam is a warning).
                    forbidden = set(check.get("forbid", []))
                    detail = [issue["message"] for issue in report["issues"]
                              if issue["severity"] == "error" or issue.get("code") in forbidden]
                    passed = report["errors"] == 0 and not any(issue.get("code") in forbidden for issue in report["issues"])
                elif kind == "spacing":
                    report = project.measure_spacing(**check["options"])
                    detail = [gap["pixels"] for gap in report["gaps"]]
                    passed = report["passed"]
                elif kind == "variable":
                    detail = state["variables"].get(check["variable"])
                    passed = detail == check["equals"]
                elif kind == "layer_field":
                    # field is a key, or a path of keys and list indexes into nested data (["chart", "kind"]).
                    path = check["field"] if isinstance(check["field"], list) else [check["field"]]
                    detail = project.layer(check["layer"])
                    for key in path:
                        detail = detail[key] if isinstance(detail, (dict, list)) else None
                    passed = detail == check["equals"]
                elif kind == "object":
                    # A declared object: its kind (or a kind below it), no missing required parts, the parts and
                    # sub-object kinds it must have, and (connected) no part floating free of its body.
                    from vixl.objects import descends, record, tree

                    target = project.layer(check["layer"])
                    found = record(target)
                    info = tree(project, target["id"]) if found else {}
                    named = {part["part"] for part in info.get("parts", [])}
                    subs = [sub["kind"] for sub in info.get("sub_objects", [])]
                    floating = []
                    if check.get("connected"):
                        report = project.check(checks=["connected"], targets=[target["id"]])
                        floating = [i["message"] for i in report["issues"] if i["check"] == "connected"]
                    detail = {"kind": found and found["kind"], "missing_parts": info.get("missing_parts"),
                              "parts": sorted(named), "sub_objects": subs, "floating": floating}
                    passed = bool(found) and descends(found["kind"], check.get("kind", found["kind"]))
                    passed = passed and (not check.get("complete") or not info["missing_parts"])
                    passed = passed and set(check.get("parts", [])) <= named | set(subs)
                    passed = passed and all(any(descends(s, k) for s in subs) for k in check.get("sub_objects", []))
                    passed = passed and not floating
                elif kind == "assert":
                    detail = [rule for rule in check["rules"] if not assert_rule(project, rule)]
                    passed = not detail
                elif kind == "centered":
                    target = project.layer(check["layer"])
                    x, y, w, h = project.inspect(target["id"])["resolved_bounds"]
                    c = state["canvas"]
                    offsets = [abs(x + w / 2 - c["width"] / 2), abs(y + h / 2 - c["height"] / 2)]
                    axes = check.get("axes", ["x", "y"])
                    detail = offsets
                    passed = all(offsets[i] <= check.get("tolerance", 2) for i, a in enumerate(("x", "y")) if a in axes)
                else:
                    raise ValueError(f"Unknown check type {kind!r}")
        except (VixlError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            detail = f"{type(exc).__name__}: {exc}"
        results.append({"check": check.get("name", kind), "passed": bool(passed), "detail": detail})
    return results


# --- tool plumbing -------------------------------------------------------------------------------


class Tools:
    """Synchronous wrapper around an in-process Vixl MCP server."""

    def __init__(self, workspace, schema="full", tools="all"):
        from vixl.interfaces import mcp_server

        self.server = mcp_server(workspace=workspace, schema=schema, tools=tools)
        self.font_cache = Path(workspace) / ".font-cache"
        self.loop = asyncio.new_event_loop()
        self.calls = 0
        self.errors = 0
        self.result_chars = 0

    def definitions(self):
        tools = self.loop.run_until_complete(self.server.list_tools())
        return [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema} for t in tools]

    def call(self, name, arguments):
        """Return (is_error, blocks) where blocks are Anthropic-style text/image content blocks."""
        self.calls += 1
        try:
            environment = {"VIXL_FONT_CACHE": str(self.font_cache)} if self.font_cache.is_dir() else {}
            with patch.dict(os.environ, environment):
                result = self.loop.run_until_complete(self.server.call_tool(name, arguments))
        except Exception as exc:  # ToolError and validation failures become error results
            self.errors += 1
            text = str(exc)
            self.result_chars += len(text)
            return True, [{"type": "text", "text": text}]
        content = result[0] if isinstance(result, tuple) else result
        blocks = []
        for item in content:
            if getattr(item, "type", None) == "image":
                blocks.append(
                    {"type": "image", "source": {"type": "base64", "media_type": item.mimeType, "data": item.data}}
                )
            else:
                text = getattr(item, "text", "")
                self.result_chars += len(text)
                blocks.append({"type": "text", "text": text})
        return False, blocks or [{"type": "text", "text": "(no output)"}]

    def close(self):
        self.loop.close()


# --- agents --------------------------------------------------------------------------------------


class ReferenceAgent:
    """Replays the task's scripted solution. Fails the run if any scripted call errors."""

    name = "reference"

    def run(self, task, tools):
        trace, saved = [], {}
        for step in task.get("reference", []):
            failed, blocks = tools.call(step["tool"], _fill(step.get("arguments", {}), saved))
            trace.append({"tool": step["tool"], "error": failed, "output": _text(blocks)[:500]})
            if step.get("save_as") and not failed:
                # A later step can use a value only known at run time (an imported asset id): "${name.key}".
                saved[step["save_as"]] = json.loads(blocks[0]["text"])
        return {"round_trips": len(task.get("reference", [])), "trace": trace, "usage": {}}


def _fill(value, saved):
    if isinstance(value, dict):
        return {key: _fill(item, saved) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, saved) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        name, _, key = value[2:-1].partition(".")
        return saved[name][key]
    return value


class ClaudeAgent:
    """Manual tool-use loop through the official Anthropic SDK (append-only history)."""

    name = "claude"

    def __init__(self, model="claude-opus-5-5", effort=None, max_turns=40, fallbacks=True, client=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client, self.model, self.effort = client, model, effort
        self.max_turns, self.fallbacks = max_turns, fallbacks

    def create(self, **arguments):
        if self.effort:
            arguments["output_config"] = {"effort": self.effort}
        if self.fallbacks:
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **arguments
            )
        return self.client.messages.create(**arguments)

    def run(self, task, tools):
        definitions = tools.definitions()
        messages = [{"role": "user", "content": task["prompt"]}]
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        trace, turns, stop = [], 0, None
        while turns < self.max_turns:
            turns += 1
            response = self.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=definitions,
                messages=messages,
                cache_control={"type": "ephemeral"},
            )
            for key in usage:
                usage[key] += getattr(response.usage, key, 0) or 0
            stop = response.stop_reason
            # Append the assistant turn exactly as returned so thinking blocks stay valid.
            messages.append({"role": "assistant", "content": response.content})
            if stop == "refusal":
                break
            uses = [block for block in response.content if block.type == "tool_use"]
            if stop != "tool_use" or not uses:
                if stop == "pause_turn":
                    continue
                break
            results = []
            for use in uses:
                failed, blocks = tools.call(use.name, use.input)
                trace.append({"tool": use.name, "input": use.input, "error": failed, "output": _text(blocks)[:500]})
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": blocks, "is_error": failed})
            # All results for one assistant turn go back in a single user message.
            messages.append({"role": "user", "content": results})
        final = next((b.text for b in messages[-1]["content"] if getattr(b, "type", None) == "text"), "") if messages[-1]["role"] == "assistant" else ""
        return {"round_trips": turns, "stop_reason": stop, "usage": usage, "trace": trace, "final": final}


def _text(blocks):
    return " ".join(block.get("text", "[image]") for block in blocks)


# --- running ---------------------------------------------------------------------------------------


def run_task(task, agent, schema="full", keep=None, tool_set="all"):
    with tempfile.TemporaryDirectory(prefix=f"vixl-eval-{task['id']}-") as directory:
        workspace = Path(directory)
        prepare_workspace(task, workspace)
        tools = Tools(workspace, schema=schema, tools=tool_set)
        started = time.monotonic()
        error = None
        try:
            outcome = agent.run(task, tools)
        except Exception as exc:  # A crashed agent run is a failed task, not a crashed eval.
            outcome, error = {"round_trips": 0, "usage": {}, "trace": []}, f"{type(exc).__name__}: {exc}"
        finally:
            tools.close()
        checks = grade(task, workspace)
        if keep:
            target = Path(keep) / task["id"]
            target.mkdir(parents=True, exist_ok=True)
            for path in workspace.iterdir():
                if path.is_file() and not path.name.endswith(".lock"):
                    (target / path.name).write_bytes(path.read_bytes())
        return {
            "task": task["id"],
            "agent": agent.name,
            "passed": error is None and all(c["passed"] for c in checks),
            "checks": checks,
            "round_trips": outcome["round_trips"],
            "tool_calls": tools.calls,
            "tool_errors": tools.errors,
            "tool_result_tokens_estimate": tools.result_chars // 4,
            "usage": outcome.get("usage", {}),
            "seconds": round(time.monotonic() - started, 2),
            "error": error,
            "stop_reason": outcome.get("stop_reason"),
            "final": outcome.get("final"),
            "trace": outcome.get("trace", []),
        }


def over_budget(results, budgets):
    """Tasks whose tool calls exceed their budget ({task: max calls}), as 'task (calls > budget)'."""
    return [f"{r['task']} ({r['tool_calls']} calls > {budgets[r['task']]})"
            for r in results if r["task"] in budgets and r["tool_calls"] > budgets[r["task"]]]


def summarize(results):
    count = len(results) or 1
    total = {key: sum(r["usage"].get(key, 0) for r in results) for key in ("input_tokens", "output_tokens")}
    return {
        "tasks": len(results),
        "passed": sum(r["passed"] for r in results),
        "success_rate": round(sum(r["passed"] for r in results) / count, 3),
        "mean_round_trips": round(sum(r["round_trips"] for r in results) / count, 2),
        "mean_tool_calls": round(sum(r["tool_calls"] for r in results) / count, 2),
        "max_tool_calls": max((r["tool_calls"] for r in results), default=0),
        "tool_error_rate": round(sum(r["tool_errors"] for r in results) / max(1, sum(r["tool_calls"] for r in results)), 3),
        "mean_tool_result_tokens": round(sum(r["tool_result_tokens_estimate"] for r in results) / count),
        **{f"total_{key}": value for key, value in total.items()},
    }


def markdown(results, summary, meta):
    lines = [
        f"# Vixl agent eval — {meta.get('agent')} {meta.get('model') or ''}".rstrip(),
        "",
        f"Success **{summary['passed']}/{summary['tasks']}** ({summary['success_rate']:.0%}) · "
        f"round trips {summary['mean_round_trips']} · tool calls {summary['mean_tool_calls']} · "
        f"tool error rate {summary['tool_error_rate']:.1%} · tool result tokens ≈{summary['mean_tool_result_tokens']}/task",
        "",
        "| Task | Result | Round trips | Tool calls | Tool errors | Input tok | Output tok | Failed checks |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in results:
        failed = ", ".join(c["check"] for c in r["checks"] if not c["passed"]) or ("error: " + r["error"] if r["error"] else "")
        lines.append(
            f"| {r['task']} | {'pass' if r['passed'] else 'FAIL'} | {r['round_trips']} | {r['tool_calls']} | "
            f"{r['tool_errors']} | {r['usage'].get('input_tokens', '–')} | {r['usage'].get('output_tokens', '–')} | {failed} |"
        )
    return "\n".join(lines) + "\n"


def run(tasks, agent, schema="full", keep=None, tool_set="all"):
    results = [run_task(deepcopy(task), agent, schema, keep, tool_set) for task in tasks]
    return results, summarize(results)
