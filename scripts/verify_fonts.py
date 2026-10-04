#!/usr/bin/env python3
"""Verify Google Fonts families/weights/italics against the Google Fonts CSS2 API.

Usage:
  python3 verify_fonts.py "Inter" "Playfair Display" ...      # probe families, print JSON
  python3 verify_fonts.py --check fonts.json [pairings.json]   # validate catalog + pairings

Method: for each weight 100..900 request
  https://fonts.googleapis.com/css2?family=<Name>:wght@<w>
and for italics
  https://fonts.googleapis.com/css2?family=<Name>:ital,wght@1,<w>
HTTP 200 with a fonts.gstatic.com/s/ URL => exists; HTTP 400 => the family or
that weight does not exist. Some non-catalog names (e.g. "Helvetica Neue") return
200 with a fonts.gstatic.com/l/font?kit= URL; these are treated as NOT existing.
(A family with no wght axis / only one static weight still answers wght@400.)
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://fonts.googleapis.com/css2?family={}"
WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]


def _ok(spec: str) -> bool:
    url = API.format(urllib.parse.quote(spec, safe=":@;,+"))
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
                # Public catalog fonts are served from fonts.gstatic.com/s/<slug>/.
                # Non-catalog names (e.g. "Helvetica Neue") can still return 200
                # but via fonts.gstatic.com/l/font?kit=..., so reject those.
                return r.status == 200 and "fonts.gstatic.com/s/" in body
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return False
        except Exception:
            continue
    raise RuntimeError(f"network failure for {spec}")


def probe(family: str) -> dict:
    name = family.replace(" ", "+")
    with ThreadPoolExecutor(9) as ex:
        up = list(ex.map(lambda w: _ok(f"{name}:wght@{w}"), WEIGHTS))
        it = list(ex.map(lambda w: _ok(f"{name}:ital,wght@1,{w}"), WEIGHTS))
    weights = [w for w, ok in zip(WEIGHTS, up) if ok]
    italic_weights = [w for w, ok in zip(WEIGHTS, it) if ok]
    return {"family": family, "exists": bool(weights), "weights": weights,
            "italic": bool(italic_weights), "italic_weights": italic_weights}


def check(fonts_path: str, pairings_path: str | None) -> int:
    fonts = json.load(open(fonts_path))
    errors = 0
    by_name = {}
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda f: probe(f["family"]), fonts))
    for f, r in zip(fonts, results):
        by_name[f["family"]] = f
        if not r["exists"]:
            print(f"FAIL family missing: {f['family']}")
            errors += 1
            continue
        if sorted(f["weights"]) != r["weights"]:
            print(f"FAIL weights {f['family']}: catalog {f['weights']} api {r['weights']}")
            errors += 1
        if f["italic"] != r["italic"]:
            print(f"FAIL italic {f['family']}: catalog {f['italic']} api {r['italic']}")
            errors += 1
    if pairings_path:
        for p in json.load(open(pairings_path)):
            for role in ("heading", "body"):
                fam, w = p[role]["family"], p[role]["weight"]
                if fam not in by_name:
                    print(f"FAIL pairing {p['name']}: {fam} not in catalog")
                    errors += 1
                elif w not in by_name[fam]["weights"]:
                    print(f"FAIL pairing {p['name']}: {fam} has no weight {w}")
                    errors += 1
    print(f"{len(fonts)} families checked, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    out = [probe(f) for f in sys.argv[1:]]
    print(json.dumps(out, indent=1))
