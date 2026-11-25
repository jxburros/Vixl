"""Export lab runs as one ZIP that stands on its own: every generation, and how each one was made.

Layout of the archive (``vixl-lab-export-<time>/``):

    index.html                 an offline report: every run, round and generation side by side, with the steps
    GUIDE.md                   how the runs were made, how to read them, and a summary per run
    data.json                  everything as data: specs, rounds, metrics, votes, judge scores, environment
    runs/<run>/README.md       the run's brief, follow-ups, settings and results table
    runs/<run>/<session>/      system-prompt.txt, tools.json, events.jsonl, python/ (scripts the code arm ran)
    runs/<run>/<session>/round-<n>/
        preview.png            the round's main deliverable as an image
        files/                 every file in the workspace after the round
        how-it-was-made.md     the round step by step: each model message, each tool call with its full
                               arguments, each result, timings and tokens

API keys are never stored by the lab, so none can be exported; the saved conversations (which repeat the steps
with base64 images) stay in the results folder.
"""

import html
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import zipfile

from . import arms, previews, sandbox
from .providers import PRESETS

INLINE_OUTPUT = 1500  # characters of a tool result shown inside index.html; the Markdown guide has the full text


def environment():
    try:
        from vixl import __version__ as vixl_version
    except ImportError:  # pragma: no cover - the lab always runs beside Vixl
        vixl_version = "unknown"
    return {"vixl": vixl_version, "python": sys.version.split()[0], "platform": platform.platform(),
            "html_rendering": previews.playwright_available(), "network_isolation": bool(sandbox.network_isolation()),
            "python_libraries": sandbox.installed_libraries()}


def provider_label(name):
    return PRESETS.get(name, {}).get("label", name)


def arm_label(name):
    return arms.ARMS.get(name, {}).get("label", name)


def fmt_tokens(metrics):
    return sum(metrics.get(k, 0) for k in ("input", "output", "cache_read", "cache_write"))


def round_events(events, number):
    return [e for e in events if e.get("round", 1) == number]


def steps(events):
    """The round's turns, each with its tool calls paired to their results."""
    turns, results = [], {}
    for event in events:
        if event["kind"] == "tool":
            results.setdefault(event.get("id") or event["name"], []).append(event)
    for event in events:
        if event["kind"] != "turn":
            continue
        calls = []
        for index, call in enumerate(event.get("tool_calls") or [{"name": c, "arguments": None}
                                                                   for c in event.get("calls", [])]):
            found = results.get(call.get("id") or call["name"]) or []
            calls.append({**call, "result": found.pop(0) if found else None, "index": index + 1})
        turns.append({**event, "calls": calls})
    return turns


def vote_text(run, number, session):
    winner = run["votes"].get(f"{number}:{session['repeat']}")
    if winner is None:
        return ""
    if winner == session["id"]:
        return "picked as best in the blind vote"
    return {"tie": "blind vote: tie", "none": "blind vote: none was good"}.get(winner, "another output was picked")


def describe_settings(spec):
    parts = [f"provider {provider_label(spec['provider'])}", f"model `{spec['model']}`"]
    if spec.get("base_url"):
        parts.append(f"endpoint {spec['base_url']}")
    parts += [f"effort {spec.get('effort') or 'default'}", f"max output {spec['max_tokens']} tokens per turn",
              f"up to {spec['max_turns']} turns and {spec['session_minutes']:g} minutes per round",
              "images sent to the model" if spec.get("vision", True) else "no images sent to the model",
              "Vixl arm given the agent skill" if spec.get("skill", True) else "Vixl arm without the agent skill"]
    if spec.get("extra"):
        parts.append(f"extra request fields `{json.dumps(spec['extra'])}`")
    return ", ".join(parts)


# --- Markdown -----------------------------------------------------------------------------------------------------

def fence(text, language=""):
    text = text or ""
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{language}\n{text}\n{ticks}"


def generation_markdown(run, session, generation, events, tool_names):
    number, metrics = generation["round"], generation["metrics"] or {}
    prompts = {r["round"]: r["prompt"] for r in run["rounds"]}
    lines = [f"# {arm_label(session['arm'])} · repeat {session['repeat'] + 1} · round {number}", "",
             f"Run `{run['id']}`, session `{session['id']}`. Settings: {describe_settings(run['spec'])}.", ""]
    lines += ["## What was asked", ""]
    if number == 1:
        lines += ["The brief, sent as the first user message:", "", fence(prompts[1]), ""]
    else:
        lines += [f"A follow-up in the same conversation (round {number} of {len(prompts)}). Earlier rounds:", ""]
        lines += [f"{n}. {prompts[n]}" for n in range(1, number)]
        lines += ["", "This round's message:", "", fence(prompts[number]), ""]
    lines += ["## How the session was set up", "",
              f"- Arm: **{arm_label(session['arm'])}**: {arms.ARMS.get(session['arm'], {}).get('description', '')}",
              f"- Tools: {', '.join(f'`{n}`' for n in tool_names) or 'none'}",
              "- System prompt: [`../system-prompt.txt`](../system-prompt.txt); tool definitions: "
              "[`../tools.json`](../tools.json)", ""]
    lines += ["## Result", "",
              f"- Status: **{generation['status']}**" + (f" ({generation['error']})" if generation["error"] else ""),
              f"- Time {metrics.get('seconds', 0)} s, {metrics.get('turns', 0)} model turns, "
              f"{metrics.get('tool_calls', 0)} tool calls ({metrics.get('tool_errors', 0)} errors), "
              f"{metrics.get('images', 0)} images returned to the model",
              f"- Tokens: {metrics.get('input', 0)} input, {metrics.get('output', 0)} output, "
              f"{metrics.get('cache_read', 0)} cache reads, {metrics.get('cache_write', 0)} cache writes"
              + (f"; cost ${metrics['cost']:.4f}" if metrics.get("cost") is not None else "")]
    if generation["preview"]:
        lines.append(f"- Preview made from `{generation['preview']}`: [preview.png](preview.png)"
                     + (f" ({generation['preview_note']})" if generation["preview_note"] else ""))
    elif generation["preview_note"]:
        lines.append(f"- No preview: {generation['preview_note']}")
    vote = vote_text(run, number, session)
    if vote:
        lines.append(f"- {vote[0].upper()}{vote[1:]}")
    for judgment in generation.get("judgments") or []:
        if judgment.get("mean"):
            scores = ", ".join(f"{k} {v}" for k, v in judgment["scores"].items())
            lines.append(f"- Judge `{judgment['judge']}`: {judgment['mean']:.2f} / 5 ({scores}). {judgment['notes']}")
    lines += ["", "## Steps", ""]
    turns = steps(events)
    if not turns:
        lines += ["No model turn was recorded for this round.", ""]
    for turn in turns:
        usage = turn.get("usage") or {}
        stop = f", stop: {turn['stop']}" if turn.get("stop") else ""
        lines += [f"### Turn {turn['n']} (at {turn['t']} s; {usage.get('input', 0)} in, "
                  f"{usage.get('output', 0)} out{stop})", ""]
        if turn.get("text"):
            lines += ["The model wrote:", "", fence(turn["text"]), ""]
        for call in turn["calls"]:
            lines.append(f"**Tool call {call['index']}: `{call['name']}`**")
            lines.append("")
            if call.get("arguments") is not None:
                lines += [fence(json.dumps(call["arguments"], indent=2, ensure_ascii=False), "json"), ""]
            if call.get("invalid"):
                lines += [f"The arguments were rejected: {call['invalid']}", ""]
            result = call.get("result")
            if result:
                label = "Error" if result["error"] else "Result"
                image = f" (+{result['images']} image{'s' if result['images'] > 1 else ''} shown to the model)" \
                    if result.get("images") else ""
                lines += [f"{label}{image}:", "", fence(result.get("output", "")), ""]
    notes = [e for e in events if e["kind"] in ("note", "error")]
    if notes:
        lines += ["## Notes", ""] + [f"- {e['text']}" for e in notes] + [""]
    lines += ["## Files after this round", ""]
    changes = {c["path"]: c["change"] for c in generation.get("changed") or []}
    for item in generation.get("files") or []:
        change = changes.get(item["path"])
        lines.append(f"- [`{item['path']}`](files/{item['path']}) ({item['size']} bytes)"
                     + (f", {change} this round" if change else ""))
    lines += [f"- `{path}`: removed this round" for path, change in changes.items() if change == "removed"]
    if not generation.get("files"):
        lines.append("None.")
    if generation.get("final"):
        lines += ["", "## The model's closing message", "", fence(generation["final"])]
    return "\n".join(lines) + "\n"


def run_markdown(run):
    spec = run["spec"]
    lines = [f"# Run {run['id']}", "", f"Started {time.strftime('%Y-%m-%d %H:%M', time.localtime(run['created']))}. "
             f"Arms: {', '.join(arm_label(a) for a in spec['arms'])}; {spec['repeats']} repeat(s).", "",
             f"Settings: {describe_settings(spec)}.", "", "## Rounds", ""]
    for item in run["rounds"]:
        lines += [f"### Round {item['round']}" + (" (the brief)" if item["round"] == 1 else " (follow-up)"), "",
                  fence(item["prompt"]), ""]
        lines += ["| Arm | Repeat | Status | Time | Turns | Tool calls (errors) | Tokens | Judge | Vote | Guide |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for session in run["sessions"]:
            generation = next((g for g in session["generations"] if g["round"] == item["round"]), None)
            if generation is None:
                continue
            m = generation["metrics"] or {}
            judged = [j["mean"] for j in generation.get("judgments") or [] if j.get("mean")]
            folder = f"{session['id']}/round-{item['round']}"
            lines.append(f"| {arm_label(session['arm'])} | {session['repeat'] + 1} | {generation['status']} | "
                         f"{m.get('seconds', 0)} s | {m.get('turns', 0)} | {m.get('tool_calls', 0)} "
                         f"({m.get('tool_errors', 0)}) | {fmt_tokens(m)} | "
                         f"{', '.join(f'{j:.2f}' for j in judged) or '–'} | "
                         f"{vote_text(run, item['round'], session) or '–'} | "
                         f"[steps]({folder}/how-it-was-made.md) · [preview]({folder}/preview.png) |")
        lines.append("")
    return "\n".join(lines)


def guide_markdown(runs, env, stats):
    lines = ["# Vixl Lab export", "",
             f"Exported {time.strftime('%Y-%m-%d %H:%M')} with Vixl {env['vixl']}, Python {env['python']} on "
             f"{env['platform']}. {len(runs)} run(s). Open `index.html` for the visual report.", "",
             "## How the runs were made", "",
             "Each run sends one brief to one model in separate sessions, one per arm and repeat. A session has its "
             "own empty workspace and its own conversation; nothing is shared between sessions except the model. "
             "Every arm gets the same opening system prompt; only the paragraph describing its tools differs.", ""]
    for name, arm in arms.ARMS.items():
        lines.append(f"- **{arm['label']}**: {arm['description']}")
    lines += ["",
              "Follow-up rounds send one more message to every session of a run. Each session continues its own "
              "conversation in its own workspace, so the arms are compared change by change. After each round the "
              "workspace is copied to `round-<n>/files/` and its main deliverable is rendered to `preview.png`.", "",
              f"The code arm's Python {'had no network' if env['network_isolation'] else 'had network access'}; "
              f"its libraries: {', '.join(env['python_libraries']) or 'standard library only'}. HTML and SVG "
              f"rendering was {'available' if env['html_rendering'] else 'not available'}.", "",
              "Blind votes were cast with the outputs shuffled and unlabelled. Judge scores use the six-part craft "
              "rubric (hierarchy, spacing, type, colour, motif, finish; 1-5 each) on the preview image and the brief, "
              "without knowing the arm.", "", "## How to read a generation", "",
              "`runs/<run>/<session>/round-<n>/how-it-was-made.md` lists what was asked, the session's tools, the "
              "result with timings and tokens, and then every step: what the model wrote, each tool call with its "
              "full arguments, and what the tool answered. `events.jsonl` beside it holds the same as data, and "
              "`python/` the scripts the code arm ran.", "", "## Results by model and arm", "",
              "| Model | Arm | Generations | Delivered | Blind wins | Judge | Median time | Median tokens | Mean cost |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in stats:
        lines.append(f"| {row['model']} | {arm_label(row['arm'])} | {row['generations']} | {row['delivered']} | "
                     f"{row['wins']} / {row['votes']} | "
                     f"{'–' if row['judge_mean'] is None else row['judge_mean']} | "
                     f"{'–' if row['median_seconds'] is None else str(row['median_seconds']) + ' s'} | "
                     f"{row['median_tokens'] if row['median_tokens'] is not None else '–'} | "
                     f"{'–' if row['mean_cost'] is None else '$' + format(row['mean_cost'], '.4f')} |")
    lines += ["", "## Runs", ""]
    for run in runs:
        rounds = len(run["rounds"])
        lines.append(f"- [{run['id']}](runs/{run['id']}/README.md): {provider_label(run['provider'])} "
                     f"`{run['model']}`, {rounds} round{'s' if rounds > 1 else ''}. "
                     f"{run['prompt'][:160]}{'…' if len(run['prompt']) > 160 else ''}")
    return "\n".join(lines) + "\n"


# --- HTML ---------------------------------------------------------------------------------------------------------

CSS = """
:root { --bg:#f6f5f2; --panel:#fff; --ink:#1c1b19; --muted:#6b6760; --line:#e3e0da; --soft:#efede8; --accent:#4b3fd6;
  --bad:#b3261e; --ok:#1f7a4d; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --bg:#141413; --panel:#1d1c1a; --ink:#ecebe7; --muted:#a29e95;
  --line:#34322e; --soft:#262522; --accent:#8f86ff; --bad:#f2867e; --ok:#5cc28f; color-scheme: dark; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1280px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:19px; margin:32px 0 8px; } h3 { font-size:16px; margin:20px 0 8px; }
p.meta, .muted { color:var(--muted); font-size:13px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin:12px 0; }
blockquote { margin:6px 0 12px; padding:8px 12px; background:var(--soft); border-radius:8px; white-space:pre-wrap; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; }
.card.winner { outline:2px solid var(--accent); }
.card header { padding:8px 12px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:8px; }
.card .shot { background:repeating-conic-gradient(var(--soft) 0 25%,var(--panel) 0 50%) 0 0/16px 16px; aspect-ratio:1/1;
  display:flex; align-items:center; justify-content:center; }
.card .shot img { max-width:100%; max-height:100%; object-fit:contain; }
.card .shot span { color:var(--muted); font-size:13px; padding:16px; text-align:center; }
.card .body { padding:10px 12px; font-size:13px; display:flex; flex-direction:column; gap:6px; }
.bad { color:var(--bad); } .ok { color:var(--ok); }
a { color:var(--accent); }
details { font-size:13px; } summary { cursor:pointer; color:var(--muted); }
pre { background:var(--soft); border-radius:6px; padding:8px; white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.45 ui-monospace,Menlo,monospace; margin:4px 0 8px; }
.step { border-top:1px solid var(--line); padding-top:6px; margin-top:6px; }
"""


def e(text):
    return html.escape(str(text if text is not None else ""))


def steps_html(turns):
    parts = []
    for turn in turns:
        usage = turn.get("usage") or {}
        parts.append(f"<div class='step'><b>Turn {turn['n']}</b> <span class='muted'>at {turn['t']} s · "
                     f"{usage.get('input', 0)} in, {usage.get('output', 0)} out</span>")
        if turn.get("text"):
            parts.append(f"<pre>{e(turn['text'])}</pre>")
        for call in turn["calls"]:
            arguments = json.dumps(call.get("arguments"), indent=2, ensure_ascii=False) \
                if call.get("arguments") is not None else ""
            parts.append(f"<div>→ <code>{e(call['name'])}</code></div>")
            if arguments:
                parts.append(f"<pre>{e(arguments[:6000])}{'…' if len(arguments) > 6000 else ''}</pre>")
            result = call.get("result")
            if result:
                output = result.get("output", "")
                shown = output[:INLINE_OUTPUT] + ("… (full text in how-it-was-made.md)"
                                                  if len(output) > INLINE_OUTPUT else "")
                status = "bad'>✗ error" if result["error"] else "ok'>✓ result"
                images = f" (+{result['images']} image)" if result.get("images") else ""
                parts.append(f"<div class='{status}{images}</div><pre>{e(shown)}</pre>")
        parts.append("</div>")
    return "".join(parts) or "<p class='muted'>No model turn was recorded.</p>"


def report_html(runs, env, stats, events):
    out = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Vixl Lab export</title>"
           f"<style>{CSS}</style></head><body><main>",
           "<h1>Vixl Lab export</h1>",
           f"<p class='meta'>Exported {e(time.strftime('%Y-%m-%d %H:%M'))} · Vixl {e(env['vixl'])} · Python "
           f"{e(env['python'])} · {e(env['platform'])} · {len(runs)} run(s). How everything was made: "
           "<a href='GUIDE.md'>GUIDE.md</a>; all data: <a href='data.json'>data.json</a>.</p>",
           "<div class='panel'><table><tr><th>Model</th><th>Arm</th><th>Generations</th><th>Delivered</th>"
           "<th>Blind wins</th><th>Judge</th><th>Median time</th><th>Median tokens</th><th>Mean cost</th></tr>"]
    for row in stats:
        out.append(f"<tr><td>{e(row['model'])}</td><td>{e(arm_label(row['arm']))}</td><td>{row['generations']}</td>"
                   f"<td>{row['delivered']}</td><td>{row['wins']} / {row['votes']}</td>"
                   f"<td>{'–' if row['judge_mean'] is None else row['judge_mean']}</td>"
                   f"<td>{'–' if row['median_seconds'] is None else str(row['median_seconds']) + ' s'}</td>"
                   f"<td>{'–' if row['median_tokens'] is None else row['median_tokens']}</td>"
                   f"<td>{'–' if row['mean_cost'] is None else '$' + format(row['mean_cost'], '.4f')}</td></tr>")
    out.append("</table></div><p class='muted'>Runs: " + " · ".join(
        f"<a href='#{e(run['id'])}'>{e(run['id'])}</a>" for run in runs) + "</p>")
    for run in runs:
        spec = run["spec"]
        out.append(f"<h2 id='{e(run['id'])}'>Run {e(run['id'])}</h2>"
                   f"<p class='meta'>{e(describe_settings(spec)).replace('`', '')}. "
                   f"<a href='runs/{e(run['id'])}/README.md'>Run guide</a></p>")
        for item in run["rounds"]:
            number = item["round"]
            out.append(f"<h3>Round {number}{' · the brief' if number == 1 else ' · follow-up'}</h3>"
                       f"<blockquote>{e(item['prompt'])}</blockquote>")
            for repeat in sorted({s["repeat"] for s in run["sessions"]}):
                if spec["repeats"] > 1:
                    out.append(f"<p class='muted'>Repeat {repeat + 1}</p>")
                out.append("<div class='cards'>")
                for session in [s for s in run["sessions"] if s["repeat"] == repeat]:
                    generation = next((g for g in session["generations"] if g["round"] == number), None)
                    if generation is None:
                        continue
                    folder = f"runs/{run['id']}/{session['id']}/round-{number}"
                    m = generation["metrics"] or {}
                    vote = vote_text(run, number, session)
                    shot = (f"<a href='{e(folder)}/preview.png'><img src='{e(folder)}/preview.png' "
                            f"alt='{e(arm_label(session['arm']))}, round {number}' loading='lazy'></a>"
                            if generation["preview"] else f"<span>{e(generation['preview_note'] or 'No preview')}</span>")
                    judged = "".join(
                        f"<div>Judge {e(j['judge'])}: <b>{j['mean']:.2f}</b> / 5 · {e(j['notes'])}</div>"
                        for j in generation.get("judgments") or [] if j.get("mean"))
                    changed = ", ".join(f"{e(c['path'])} ({e(c['change'])})" for c in generation.get("changed") or [])
                    files = " ".join(f"<a href='{e(folder)}/files/{e(f['path'])}'>{e(f['path'])}</a>"
                                     for f in generation.get("files") or [])
                    turns = steps(round_events(events.get(session["id"], []), number))
                    out.append(
                        f"<article class='card{' winner' if vote.startswith('picked') else ''}'>"
                        f"<header><b>{e(arm_label(session['arm']))}</b><span class='muted'>{e(generation['status'])}"
                        f"</span></header><div class='shot'>{shot}</div><div class='body'>"
                        f"<div class='muted'>{m.get('seconds', 0)} s · {m.get('turns', 0)} turns · "
                        f"{m.get('tool_calls', 0)} tool calls ({m.get('tool_errors', 0)} errors) · "
                        f"{fmt_tokens(m)} tokens"
                        + (f" · ${m['cost']:.4f}" if m.get("cost") is not None else "") + "</div>"
                        + (f"<div><b>{e(vote)}</b></div>" if vote else "")
                        + (f"<div class='bad'>{e(generation['error'])}</div>" if generation["error"] else "")
                        + judged
                        + (f"<div>Changed: {changed}</div>" if changed else "")
                        + (f"<div>Files: {files}</div>" if files else "")
                        + f"<div><a href='{e(folder)}/how-it-was-made.md'>How it was made</a></div>"
                        f"<details><summary>Steps ({len(turns)} turns)</summary>{steps_html(turns)}</details>"
                        "</div></article>")
                out.append("</div>")
    out.append("</main></body></html>")
    return "".join(out)


# --- archive ------------------------------------------------------------------------------------------------------

def build(lab, run_ids=None, out=None):
    """Write the export ZIP for ``run_ids`` (every run when None); return its path."""
    chosen = run_ids or [row["id"] for row in lab.store.runs()]
    runs = [run for run in (lab.store.run(run_id) for run_id in chosen) if run is not None]
    if not runs:
        raise ValueError("there is no run to export")
    if any(lab.busy(run["id"]) for run in runs):
        raise ValueError("wait for running rounds to finish before exporting")
    stamp = time.strftime("%Y%m%d-%H%M")
    top = f"vixl-lab-export-{stamp}"
    if out is None:
        handle, name = tempfile.mkstemp(prefix=f"{top}-", suffix=".zip")
        os.close(handle)  # an open handle would stop Windows from deleting the file once it has been sent
        out = name
    out = Path(out)
    env = environment()
    stats = lab.store.stats([run["id"] for run in runs])
    events = {s["id"]: lab.session_events(s["id"]) for run in runs for s in run["sessions"]}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        def add_text(name, text):
            archive.writestr(f"{top}/{name}", text)

        def add_tree(folder, prefix, skip=()):
            folder = Path(folder)
            if not folder.is_dir():
                return
            for path in sorted(folder.rglob("*")):
                relative = path.relative_to(folder)
                if path.is_file() and not path.is_symlink() and relative.parts[0] not in skip:
                    archive.write(path, f"{top}/{prefix}/{relative.as_posix()}")

        add_text("index.html", report_html(runs, env, stats, events))
        add_text("GUIDE.md", guide_markdown(runs, env, stats))
        add_text("data.json", json.dumps({"exported": time.strftime("%Y-%m-%dT%H:%M:%S"), "environment": env,
                                          "arms": arms.ARMS, "runs": runs}, indent=2, ensure_ascii=False))
        for run in runs:
            base = f"runs/{run['id']}"
            add_text(f"{base}/README.md", run_markdown(run))
            for session in run["sessions"]:
                source = lab.root / "runs" / run["id"] / session["id"]
                prefix = f"{base}/{session['id']}"
                for name in ("system-prompt.txt", "tools.json", "events.jsonl"):
                    if (source / name).is_file():
                        archive.write(source / name, f"{top}/{prefix}/{name}")
                add_tree(source / "python", f"{prefix}/python", skip=("home",))
                try:
                    tool_names = [t["name"] for t in json.loads((source / "tools.json").read_text(encoding="utf-8"))]
                except (OSError, ValueError):
                    tool_names = []
                for generation in session["generations"]:
                    number = generation["round"]
                    folder = source / "rounds" / str(number)
                    if (folder / "preview.png").is_file():
                        archive.write(folder / "preview.png", f"{top}/{prefix}/round-{number}/preview.png")
                    add_tree(folder / "files", f"{prefix}/round-{number}/files")
                    add_text(f"{prefix}/round-{number}/how-it-was-made.md", generation_markdown(
                        run, session, generation, round_events(events[session["id"]], number), tool_names))
    return out
