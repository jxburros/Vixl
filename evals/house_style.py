"""House-style eval: how varied and how sound are the designs Vixl makes from a sparse brief?

A sparse brief names what is being made and gives the copy, nothing else: no palette, fonts,
layout or look. Vixl fills the rest from its house style and a seeded roll. This eval rolls about
50 such briefs across the purposes (poster, social, slides, document, form, diagram, logo,
motion) at each variety level, applies every roll to a real document, and scores:

* **diversity**: the entropy in bits (0 = always the same choice, 1 = an even split between two,
  more for wider spreads) of the rolled palette, layout, mode, pairing, look and style, and the mean pairwise distance between small
  renders (0 = identical images, 1 = opposite colours everywhere);
* **quality**: the share of designs with no ``fix`` finding from ``check``, the share whose fonts
  are installed (the document typography, not the proofing fallback), the share that pass the
  contrast check, and the lowest ink contrast seen.

It runs offline: fonts come from a temporary cache filled with the bundled font under each
pairing's file names, as in the agent eval, so it measures font installation, not font design.

    python -m evals.house_style                  # every brief, levels low/medium/high
    python -m evals.house_style --limit 8        # a quick subset
    python -m evals.house_style --compare evals/house-style-baseline.json

A comparison fails (exit 1) when a quality share falls, or when the diversity of a level falls by
more than the tolerance stored in the baseline.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import itertools
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

LEVELS = ("low", "medium", "high")
DIMENSIONS = ("palette", "layout", "mode", "pairing", "look", "style")
BASELINE = Path(__file__).parent / "house-style-baseline.json"


def _copy(title, subtitle=None, label=None, cta=None):
    slots = {"title": title}
    if subtitle:
        slots["subtitle"] = subtitle
    if label:
        slots["label"] = label
    if cta:
        slots["cta"] = cta
    return slots


# (purpose, size, dpi for print sizes, copy). Print sizes render at a low dpi to keep the eval fast;
# layouts scale with the canvas, so the composition is the same.
BRIEFS = [
    ("poster", "poster-18x24", 40, _copy("Summer Night Market", "Food, music and late shopping", "June 21", "Free entry")),
    ("poster", "a3", 60, _copy("Open Studio Weekend", "Forty artists open their doors", "Oct 12–13")),
    ("poster", "instagram-portrait", None, _copy("Jazz on the Roof", "Every Friday at sunset", "Live", "Book a table")),
    ("poster", "poster-11x17", 50, _copy("Community Bake Sale", "All proceeds go to the library", "Saturday")),
    ("poster", "a3", 60, _copy("Film Club", "Classic cinema, every second Tuesday")),
    ("poster", "poster-24x36", 36, _copy("Marathon 2027", "Run the river route", "Register now", "Sign up")),
    ("social", "instagram-post", None, _copy("New season, new menu", "Twelve dishes from local farms", "Now open")),
    ("social", "story", None, _copy("48-hour flash sale", "Everything 30% off", "Ends Sunday", "Shop now")),
    ("social", "linkedin-post", None, _copy("We are hiring designers", "Remote, full time, three roles", "Careers")),
    ("social", "youtube-thumbnail", None, _copy("I tried every pen", "So you don't have to")),
    ("social", "instagram-square", None, _copy("Thank you, 10k", "To everyone who reads along")),
    ("social", "x-post", None, _copy("Release 4.0 is out", "Faster builds and a new CLI", "Changelog")),
    ("slides", "slide", None, _copy("Quarterly review", "Growth, costs and next steps", "Q3 2026")),
    ("slides", "slide", None, _copy("Why onboarding matters", "Three findings from user research")),
    ("slides", "slide-4x3", None, _copy("Project kickoff", "Goals, team and timeline")),
    ("slides", "slide", None, _copy("Thank you", "Questions welcome")),
    ("slides", "slide-16x10", None, _copy("Roadmap 2027", "What we build next and why")),
    ("slides", "slide", None, _copy("Design principles", "Clear, calm and honest")),
    ("document", "letter", 72, _copy("Annual report 2026", "A year of steady growth", "Report")),
    ("document", "a4", 72, _copy("Field notes on urban trees", "A survey of four city parks")),
    ("document", "letter", 72, _copy("Policy update", "Changes to the travel policy from January")),
    ("document", "a5", 100, _copy("A short guide to composting", "Turn kitchen scraps into soil")),
    ("document", "a4", 72, _copy("Research summary", "Sleep and memory in adults")),
    ("document", "letter", 72, _copy("Welcome pack", "Everything you need in your first week")),
    ("form", "letter", 72, _copy("Volunteer sign-up", "Tell us when you can help", "Form")),
    ("form", "a4", 72, _copy("Event registration", "One form per attendee")),
    ("form", "letter", 72, _copy("Feedback form", "Two minutes, five questions")),
    ("form", "a4", 72, _copy("Membership application", "Join the cycling club")),
    ("form", "letter", 72, _copy("Expense claim", "Attach receipts on page two")),
    ("form", "a5", 100, _copy("Booking request", "Studio hire by the hour")),
    ("diagram", "slide", None, _copy("94%", "of readers finish the guide", "Completion")),
    ("diagram", "instagram-post", None, _copy("3× faster", "Build times after the upgrade", "Benchmark")),
    ("diagram", "slide", None, _copy("How the pipeline works", "Ingest, clean, model, ship")),
    ("diagram", "a4", 72, _copy("Org overview", "Four teams, one roadmap")),
    ("diagram", "instagram-post", None, _copy("2.4M", "trees planted since 2019", "Impact")),
    ("diagram", "slide", None, _copy("Funnel review", "Visit, trial, purchase")),
    ("logo", "logo", None, _copy("Northwind", "Coffee roasters")),
    ("logo", "logo", None, _copy("Atlas Labs")),
    ("logo", "logo-stacked", None, _copy("Fernhill", "Garden studio")),
    ("logo", "logo", None, _copy("Kite & Co")),
    ("logo", "logo-horizontal", None, _copy("Brightline", "Data for good")),
    ("logo", "logo", None, _copy("Oro")),
    ("motion", "video-square", None, _copy("Launch day", "Watch the reveal", "Live")),
    ("motion", "video-1080p", None, _copy("Season two", "Streaming this Friday")),
    ("motion", "video-vertical", None, _copy("Behind the scenes", "How the album was made")),
    ("motion", "video-square", None, _copy("Countdown", "Three days to go")),
    ("motion", "video-1080p", None, _copy("Highlights", "The best of the festival")),
    ("motion", "video-vertical", None, _copy("Tip of the day", "Save time with shortcuts")),
]


def spread(values):
    """Shannon entropy of a list of labels in bits: 0 when every label is the same, 1 for an even
    split between two, log2(n) for n equally common labels."""
    counts = Counter(values)
    total = sum(counts.values())
    if total < 2:
        return 0.0
    return round(-sum(c / total * math.log2(c / total) for c in counts.values()), 3)


def thumbnail(image, size=48):
    import numpy as np
    from PIL import Image

    flat = Image.new("RGB", image.size, "white")
    flat.paste(image, mask=image.getchannel("A") if image.mode == "RGBA" else None)
    return np.asarray(flat.resize((size, size), Image.Resampling.BOX), dtype="float32") / 255.0


def pairwise_distance(thumbs):
    """Mean absolute difference over every pair of thumbnails (0-1): colour, lightness and layout together."""
    import numpy as np

    if len(thumbs) < 2:
        return 0.0
    stack = np.stack(thumbs)
    total, pairs = 0.0, 0
    for i, j in itertools.combinations(range(len(stack)), 2):
        total += float(np.abs(stack[i] - stack[j]).mean())
        pairs += 1
    return round(total / pairs, 4)


def structure_distance(thumbs):
    """Mean over every pair of 1 - correlation of the thumbnails' lightness maps (0 = same arrangement of
    light and dark, about 1 = unrelated, 2 = inverted). Each map is normalised first, so a light and a
    dark version of one composition count as the same layout and only the arrangement differs."""
    import numpy as np

    if len(thumbs) < 2:
        return 0.0
    maps = []
    for thumb in thumbs:
        gray = thumb @ np.array([0.2126, 0.7152, 0.0722], dtype="float32")
        gray = gray - gray.mean()
        norm = float(np.sqrt((gray * gray).sum()))
        maps.append((gray / norm).ravel() if norm > 1e-6 else gray.ravel())
    stack = np.stack(maps)
    similarity = stack @ stack.T
    upper = similarity[np.triu_indices(len(maps), k=1)]
    return round(float((1 - upper).mean()), 4)


@contextmanager
def offline_fonts():
    """A temporary font cache holding the bundled font under every pairing's file names."""
    from vixl import fonts
    from vixl.typefaces import pairings, slug

    with tempfile.TemporaryDirectory() as directory:
        cache = Path(directory)
        fixture = (Path(fonts.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
        for item in pairings():
            for role in ("heading", "body"):
                spec = item[role]
                (cache / f"{slug(spec['family'])}-{spec['weight']}.ttf").write_bytes(fixture)
        previous = os.environ.get("VIXL_FONT_CACHE")
        os.environ["VIXL_FONT_CACHE"] = str(cache)
        try:
            yield cache
        finally:
            if previous is None:
                os.environ.pop("VIXL_FONT_CACHE", None)
            else:
                os.environ["VIXL_FONT_CACHE"] = previous


def run_one(brief, seed, level, workspace, house_style_version=None):
    from vixl import Project
    from vixl.typefaces import roll_document

    purpose, size, dpi, slots = brief
    project = Project.sized(size, dpi=dpi) if dpi else Project.sized(size)
    result = roll_document(project, workspace=workspace, seed=seed, purpose=purpose, variety=level,
                           apply=True, slots=slots, house_style_version=house_style_version)
    report = project.check()
    issues = report.get("issues", [])
    fixes = [i for i in issues if i.get("action") == "fix"]
    typography = project.state.get("typography") or {}
    fonts_ok = bool(typography.get("heading") and typography.get("body"))
    contrast = [i for i in issues if i.get("check") == "contrast" and i.get("action") == "fix"]
    direction = result["direction"]
    from vixl.colors import contrast_ratio, parse

    swatches = project.state.get("swatches", {})
    ink_contrast = None
    if swatches.get("ink") and swatches.get("background"):
        ink_contrast = round(contrast_ratio(parse(swatches["ink"])[:3], parse(swatches["background"])[:3]), 2)
    return {
        "purpose": purpose, "size": size, "seed": seed, "level": level,
        "choices": {key: str(direction.get(key)) for key in DIMENSIONS},
        "tier": direction.get("tier"),
        "fix": [f"{i.get('check')}:{i.get('code', i.get('message', ''))[:60]}" for i in fixes],
        "fonts": fonts_ok,
        "contrast_ok": not contrast,
        "ink_contrast": ink_contrast,
        "thumb": thumbnail(project.render()),
    }


def evaluate(briefs=BRIEFS, levels=LEVELS, seed_base=1000, progress=None, house_style_version=None):
    """Roll, apply, check and render every brief at every level; return per-level scores. ``house_style_version``
    pins the house style (1 replays the 0.20-0.22 rolls, the "before" of the 0.23 changes)."""
    from vixl.variety import VARIETIES  # noqa: F401  (fails early on a broken install)

    scores = {}
    runs = []
    with offline_fonts(), tempfile.TemporaryDirectory() as workspace:
        for level in levels:
            rows = []
            for index, brief in enumerate(briefs):
                rows.append(run_one(brief, seed_base + index, level, workspace, house_style_version))
                if progress:
                    progress(level, index + 1, len(briefs))
            runs.extend(rows)
            diversity = {key: spread([row["choices"][key] for row in rows]) for key in DIMENSIONS}
            diversity["image_distance"] = pairwise_distance([row["thumb"] for row in rows])
            diversity["structure_distance"] = structure_distance([row["thumb"] for row in rows])
            # Light against dark dominates the raw distance, so the share of dark rolls (set per purpose)
            # moves it; the same-mode distance compares designs only with others in their own mode.
            groups = [[row["thumb"] for row in rows if row["choices"]["mode"] == mode] for mode in ("light", "dark")]
            pairs = [len(group) * (len(group) - 1) / 2 for group in groups]
            diversity["same_mode_distance"] = round(sum(pairwise_distance(group) * n for group, n in zip(groups, pairs))
                                                    / max(1, sum(pairs)), 4)
            diversity["mean"] = round(sum(diversity[key] for key in ("palette", "layout", "mode", "pairing")) / 4, 3)
            contrasts = [row["ink_contrast"] for row in rows if row["ink_contrast"] is not None]
            quality = {
                "no_fix_findings": round(sum(not row["fix"] for row in rows) / len(rows), 3),
                "fonts_installed": round(sum(row["fonts"] for row in rows) / len(rows), 3),
                "contrast_pass": round(sum(row["contrast_ok"] for row in rows) / len(rows), 3),
                "min_ink_contrast": min(contrasts) if contrasts else None,
            }
            tiers = Counter(row["tier"] for row in rows if row["tier"])
            scores[level] = {"diversity": diversity, "quality": quality,
                             **({"tiers": dict(sorted(tiers.items()))} if tiers else {}),
                             "fix_findings": sorted({f for row in rows for f in row["fix"]})}
    for row in runs:
        row.pop("thumb")
    return {"briefs": len(briefs), "levels": list(levels), "scores": scores}, runs


def compare(result, baseline):
    """Regressions of ``result`` against a stored baseline, as readable lines."""
    problems = []
    tolerance = baseline.get("diversity_tolerance", 0.05)
    for level, stored in baseline.get("scores", {}).items():
        current = result["scores"].get(level)
        if current is None:
            continue
        for key, value in stored["quality"].items():
            now = current["quality"].get(key)
            if key == "min_ink_contrast":
                if value is not None and (now is None or now < min(value, 7.0)):
                    problems.append(f"{level}: min ink contrast {now} < {min(value, 7.0)}")
            elif now is not None and now < value:
                problems.append(f"{level}: {key} fell from {value} to {now}")
        for key in ("mean", "image_distance", "structure_distance", "same_mode_distance"):
            if key in stored["diversity"] and current["diversity"][key] < stored["diversity"][key] - tolerance:
                problems.append(f"{level}: diversity {key} fell from {stored['diversity'][key]} to {current['diversity'][key]}")
    return problems


def markdown(result):
    version = result.get("house_style_version") or "current"
    lines = [f"House-style eval: {result['briefs']} sparse briefs per level, house style {version}", "",
             "Diversity is entropy in bits per dimension, then mean pairwise image and layout-structure distance; "
             "quality is the share of designs with no fix finding, with fonts installed and passing contrast.", "",
             "| Level | palette | layout | mode | pairing | look | style | image dist. | same-mode dist. | structure dist. "
             "| no fix | fonts | contrast |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for level, score in result["scores"].items():
        d, q = score["diversity"], score["quality"]
        lines.append(f"| {level} | {d['palette']} | {d['layout']} | {d['mode']} | {d['pairing']} | {d['look']} | {d['style']} "
                     f"| {d['image_distance']} | {d['same_mode_distance']} | {d['structure_distance']} "
                     f"| {q['no_fix_findings']} | {q['fonts_installed']} "
                     f"| {q['contrast_pass']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.house_style", description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="use only the first N briefs, spread across purposes")
    parser.add_argument("--levels", default=",".join(LEVELS))
    parser.add_argument("--out", help="write the scores and every run as JSON here")
    parser.add_argument("--compare", help="a stored baseline to compare against (exit 1 on a regression)")
    parser.add_argument("--house-style", type=int, dest="house_style",
                        help="pin a house-style version (1 replays the 0.20-0.22 rolls)")
    args = parser.parse_args(argv)
    briefs = BRIEFS
    if args.limit:
        briefs = BRIEFS[::max(1, len(BRIEFS) // args.limit)][:args.limit]
    started = time.time()
    result, runs = evaluate(briefs, tuple(args.levels.split(",")),
                            progress=lambda level, i, n: print(f"\r{level} {i}/{n}", end="", file=sys.stderr),
                            house_style_version=args.house_style)
    result["house_style_version"] = args.house_style
    print(file=sys.stderr)
    result["seconds"] = round(time.time() - started, 1)
    print(markdown(result))
    if args.out:
        Path(args.out).write_text(json.dumps({**result, "runs": runs}, indent=2), encoding="utf-8")
    if args.compare:
        problems = compare(result, json.loads(Path(args.compare).read_text(encoding="utf-8")))
        print("Regressions:\n- " + "\n- ".join(problems) if problems else "No regressions against the baseline.")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
