"""Measure the MCP tool surface and keep it from growing: a ratchet on tests/mcp_surface_baseline.json.

    python -m scripts.mcp_surface                 # print the current sizes and how they compare with the baseline
    python -m scripts.mcp_surface --update        # lower the baseline to the current sizes (never raises it)
    python -m scripts.mcp_surface --update --allow-growth   # accept a larger surface deliberately

tests/test_mcp_surface.py fails when any tool, the total or the instructions grow beyond the baseline, or a tool
exceeds the per-tool cap. Shrink something and run --update to lock the gain in.
"""

import argparse
import json
from pathlib import Path
import sys

BASELINE = Path(__file__).resolve().parent.parent / "tests" / "mcp_surface_baseline.json"
SERVERS = ("default", "ai")


def measure():
    from vixl.mcp_tools import surface

    return {name: surface(name) for name in SERVERS}


def growth(current, baseline):
    """Every way ``current`` is larger than ``baseline``: (server, what, was, now)."""
    found = []
    for server, now in current.items():
        was = baseline.get("servers", {}).get(server)
        if was is None:
            found.append((server, "server", None, now["total_chars"]))
            continue
        for key in ("total_chars", "instructions_chars"):
            if now[key] > was[key]:
                found.append((server, key, was[key], now[key]))
        for tool, size in now["tools"].items():
            if size > was["tools"].get(tool, 0):
                found.append((server, tool, was["tools"].get(tool), size))
    return found


def over_cap(current, cap):
    return [(server, tool, size) for server, now in current.items() for tool, size in now["tools"].items()
            if size > cap]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="Rewrite the baseline with the current sizes")
    parser.add_argument("--allow-growth", action="store_true", help="With --update: accept a larger surface")
    a = parser.parse_args(argv)
    from vixl.mcp_tools import TOOL_CAP

    current = measure()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"servers": {}}
    for server, now in current.items():
        was = baseline.get("servers", {}).get(server, {})
        print(f"{server}: {len(now['tools'])} tools, {now['total_chars']} chars (~{now['total_tokens']} tokens), "
              f"instructions {now['instructions_chars']} chars; baseline {was.get('total_chars', '-')}")
        for tool, size in sorted(now["tools"].items(), key=lambda item: -item[1]):
            print(f"  {size:6d}  {tool}  (baseline {was.get('tools', {}).get(tool, '-')})")
    grown, capped = growth(current, baseline), over_cap(current, TOOL_CAP)
    for server, what, was, now in grown:
        print(f"GROWTH {server} {what}: {was} -> {now}")
    for server, tool, size in capped:
        print(f"OVER CAP {server} {tool}: {size} > {TOOL_CAP}")
    if not a.update:
        return 1 if grown or capped else 0
    if (grown or capped) and not a.allow_growth:
        print("Refusing to raise the baseline; pass --allow-growth to accept a larger surface.", file=sys.stderr)
        return 1
    BASELINE.write_text(json.dumps({"per_tool_cap": TOOL_CAP, "servers": current}, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {BASELINE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
