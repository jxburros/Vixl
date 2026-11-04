"""Capture the token baseline of roadmap 4.1: per-brief cost figures for a representative set of briefs.

    python -m evals.token_baseline                 # replay (no API key): payload sizes and images, tokens null
    python -m evals.token_baseline --agent claude  # live: also tokens_total and cache reads

Writes ``evals/token-baseline.json``. Eight briefs are eval tasks (``evals/tasks``); the pattern and sprite
briefs have no eval task yet, so they are scripted here in the same reference format. A replay records what
the harness can measure offline: tool calls, images the tools returned and the character counts of the
payloads sent (``tool_input_chars``) and received (``tool_result_chars``), the proxy for tokens until a live
run fills ``tokens_total`` and ``cache_read_tokens`` (both null in a replay).
"""

import argparse
import json
from pathlib import Path
import sys

from evals.harness import ClaudeAgent, ReferenceAgent, load_tasks, run_task

OUT = Path(__file__).parent / "token-baseline.json"
# Representative briefs (roadmap 4.1 step 2) and the eval task that stands for each.
BRIEFS = {
    "graphic": "youtube-thumbnail",
    "chart": "chart-fix-value",
    "deck": "deck-pptx",
    "form": "form-registration",
    "illustration": "organic-flower",
    "pattern": "pattern-tile",
    "variants": "variable-variants",
    "sprite": "sprite-coin",
    "animation": "seamless-spinner",
    "follow-up edit": "fix-layout",
}
SCRIPTED = [
    {
        "id": "pattern-tile",
        "prompt": "Create tile.vixl, a 400x400 seamless pattern tile on a cream background scattered with a dozen "
                  "small orange stars, and export it as tile.png.",
        "checks": [{"type": "file", "path": "tile.png", "image_size": [400, 400]}],
        "reference": [
            {"tool": "vixl_document", "arguments": {"action": "create", "path": "tile.vixl", "width": 400,
                                                   "height": 400, "background": "#fef3c7"}},
            {"tool": "vixl_apply", "arguments": {"operations": [
                {"type": "shape", "shape": "star", "sides": 5, "name": "star", "x": 0, "y": 0, "width": 40,
                 "height": 40, "fill": "#f97316"},
                {"type": "pattern-scatter", "source": ["star"], "width": 400, "height": 400, "count": 12, "seed": 5,
                 "scale_jitter": 0.3, "rotation_jitter": 180, "name": "star-tile"},
                {"type": "hide", "target": "star"}], "check": True}},
            {"tool": "vixl_render", "arguments": {"max_width": 512}},
            {"tool": "vixl_export", "arguments": {"path": "tile.png"}},
        ],
    },
    {
        "id": "sprite-coin",
        "prompt": "Create coin.vixl, a 16x16 pixel-art gold coin with a brown rim, and a two-frame idle/glint "
                  "animation exported as coin.gif at 8x.",
        "checks": [{"type": "file", "path": "coin.gif"}],
        "reference": [
            {"tool": "vixl_document", "arguments": {"action": "create", "path": "coin.vixl", "width": 16,
                                                   "height": 16, "background": "transparent"}},
            {"tool": "vixl_apply", "arguments": {"operations": [
                {"type": "pixel-art", "name": "coin", "width": 16, "height": 16,
                 "palette": {".": "transparent", "g": "#ffc44d", "s": "#9c5f22", "w": "#fff3bd"}},
                {"type": "pixel-draw", "target": "coin", "tool": "rect", "x": 4, "y": 3, "width": 8, "height": 10,
                 "color": "s"},
                {"type": "pixel-draw", "target": "coin", "tool": "rect", "x": 5, "y": 4, "width": 6, "height": 8,
                 "color": "g"},
                {"type": "frame-save", "name": "idle", "duration": 150},
                {"type": "pixel-draw", "target": "coin", "tool": "line", "x": 6, "y": 5, "x2": 9, "y2": 5,
                 "color": "w"},
                {"type": "frame-save", "name": "glint", "duration": 100},
                {"type": "animation-set", "order": ["idle", "glint"], "loop": 0}]}},
            {"tool": "vixl_check", "arguments": {"action": "pixels", "target": "coin"}},
            {"tool": "vixl_export", "arguments": {"kind": "animation", "path": "coin.gif", "format": "gif",
                                                 "scale": 8}},
        ],
    },
]
FIELDS = ("passed", "tool_calls", "tool_errors", "round_trips", "images", "tool_input_chars", "tool_result_chars",
          "tool_result_tokens_estimate", "tokens_total", "cache_read_tokens", "usage")


def briefs():
    tasks = {task["id"]: task for task in load_tasks()}
    tasks.update({task["id"]: task for task in SCRIPTED})
    return {brief: tasks[name] for brief, name in BRIEFS.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.token_baseline", description=__doc__.splitlines()[0])
    parser.add_argument("--agent", choices=["reference", "claude"], default="reference")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    agent = ClaudeAgent(args.model, args.effort) if args.agent == "claude" else ReferenceAgent()
    from vixl import __version__

    results = {}
    for brief, task in briefs().items():
        result = run_task(task, agent)
        results[brief] = {"task": task["id"], **{key: result.get(key) for key in FIELDS}}
        print(f"{brief:15} {task['id']:20} calls {result['tool_calls']:2}  images {result['images']}  "
              f"sent {result['tool_input_chars']:6} chars  received {result['tool_result_chars']:6} chars  "
              f"tokens {result['tokens_total']}")
    live = args.agent == "claude"
    document = {
        "description": (
            "Roadmap 4.1 token baseline: one representative brief per kind of work, produced by "
            "`python -m evals.token_baseline`"
            + (f" --agent claude --model {args.model}" + (f" --effort {args.effort}" if args.effort else "")
               if live else "")
            + ". "
            + ("Live run: tokens_total and cache_read_tokens come from the API's usage."
               if live else
               "Replay of the scripted reference solutions (no API key): tokens_total and cache_read_tokens are "
               "null because no model was called; tool_input_chars (the JSON an agent writes) and "
               "tool_result_chars (what the tools send back, about 4 characters per token) are the proxy, and "
               "images counts the previews returned (about 300 tokens each at 512 px). Not measured offline: what a "
               "model reads from vixl_reference, its own reasoning and retries, and the tool list it is sent.")
        ),
        "vixl_version": __version__,
        "agent": args.agent,
        **({"model": args.model, "effort": args.effort} if live else {}),
        "briefs": results,
        "totals": {
            "tool_calls": sum(r["tool_calls"] for r in results.values()),
            "images": sum(r["images"] for r in results.values()),
            "tool_input_chars": sum(r["tool_input_chars"] for r in results.values()),
            "tool_result_chars": sum(r["tool_result_chars"] for r in results.values()),
            "tokens_total": sum(r["tokens_total"] for r in results.values()) if live else None,
            "cache_read_tokens": sum(r["cache_read_tokens"] for r in results.values()) if live else None,
        },
    }
    Path(args.out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
