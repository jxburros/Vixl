"""Rebuild docs/assets/template-variants.webp with all recommended built-in combinations."""

from pathlib import Path

from PIL import Image, ImageDraw

from vixl.assets import add_image
from vixl.project import Project
from vixl.render import render
from vixl.proxy import scaled_project
from vixl.resources import CONTAINERS, TEMPLATES


def sample(project):
    image = Image.new("RGBA", (1200, 1200), "#bccbd0")
    draw = ImageDraw.Draw(image)
    draw.ellipse((330, 120, 870, 660), fill="#4b697a")
    draw.rounded_rectangle((160, 570, 1040, 1400), radius=240, fill="#2b4555")
    return add_image(project, image)


def build(output):
    names = [n for n, t in TEMPLATES.items() if t.get("combinations")]
    cellw, cellh = 360, 220
    sheet = Image.new("RGB", (cellw * 3, cellh * len(names) + 40), "#f0f2f4")
    draw = ImageDraw.Draw(sheet)
    for i, label in enumerate(("Minimal / light", "Bold / dark", "Warm / editorial")):
        draw.text((i * cellw + 16, 12), label, fill="#152535")
    reports = []
    for row, name in enumerate(names):
        item = TEMPLATES[name]
        for col, combo in enumerate(item["combinations"]):
            project = Project(item["width"], item["height"])
            asset = sample(project)
            variables = {}
            for i, resource in enumerate(item["grid"]["resources"]):
                variables[f"slot-{i + 1}"] = {
                    key: (
                        asset
                        if key == "photo"
                        else "#263545"
                        if key == "ink"
                        else "#7198b1"
                        if key == "accent"
                        else "42%"
                        if key == "value"
                        else "$29"
                        if key == "price"
                        else "Clear ideas, made visual"
                        if key in ("title", "quote")
                        else "Ada Chen"
                        if key == "name"
                        else "Get started"
                        if key == "button"
                        else "Thoughtfully designed"
                    )
                    for key in CONTAINERS[resource].get("defaults", {})
                }
            project.apply(
                {
                    "type": "template-apply",
                    "name": name,
                    "variables": variables,
                    "seed": 42,
                    "palette": combo["palette"],
                    "mode": combo["mode"],
                    "look": combo["look"],
                }
            )
            report = project.check_suite("container-layout")
            assert report["passed"], (name, combo, report)
            # Rendering a scaled copy keeps fonts and vector shapes crisp without allocating poster-sized images.
            preview = render(
                scaled_project(project, min((cellw - 24) / item["width"], (cellh - 40) / item["height"]))
                or project
            )
            preview.thumbnail((cellw - 24, cellh - 40))
            px = col * cellw + (cellw - preview.width) // 2
            py = row * cellh + 40 + 28
            sheet.paste(preview.convert("RGB"), (px, py))
            draw.text((col * cellw + 12, row * cellh + 46), name, fill="#152535")
            reports.append((name, combo["name"]))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=85)
    return reports


if __name__ == "__main__":
    result = build(Path(__file__).resolve().parents[1] / "docs/assets/template-variants.webp")
    print(f"Validated and rendered {len(result)} template variants")
