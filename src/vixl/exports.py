"""Bounded data-set and artboard exports without changing the source document."""

import csv
import io
import json
from pathlib import Path

from .assets import add_encoded, read_bounded
from .errors import require, VixlError


def export_screens(project, directory, *, scales=(1, 2), boards=None, **options):
    names = list(boards) if boards is not None else list(project.state.get("artboards", {}))
    require(names, "Create at least one artboard")
    require(1 <= len(scales) <= 8 and len(set(scales)) == len(scales), "Use 1–8 unique scales")
    from .model import finite

    for scale in scales:
        finite(scale, "scale", 0.01, 16)
    root = Path(directory)
    jobs = []
    for name in names:
        require(name in project.state.get("artboards", {}), f"Unknown artboard: {name}")
        for scale in scales:
            path = root / f"{name}@{scale:g}x.png"
            require(not path.exists(), f"Output already exists: {path}")
            jobs.append((name, scale, path))
    # Validate all renders before publishing any output; keep memory bounded to one image.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vixl-screens-") as staging:
        for i, (name, scale, _) in enumerate(jobs):
            project.export(Path(staging) / f"{i}.png", artboard=name, scale=scale, format="PNG", **options)
        root.mkdir(parents=True, exist_ok=True)
        for i, (_, _, path) in enumerate(jobs):
            with path.open("xb") as stream:
                stream.write((Path(staging) / f"{i}.png").read_bytes())
    return [{"artboard": name, "scale": scale, "output": str(path)} for name, scale, path in jobs]


def render_data(project, csv_path, directory, *, variables=None, check=True, **options):
    content = read_bounded(csv_path, 8 * 1024 * 1024).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
    headers = reader.fieldnames
    require(
        headers and len(set(headers)) == len(headers) and all(headers), "CSV requires unique nonempty headers"
    )
    rows = []
    try:
        for row in reader:
            require(len(rows) < 10000, "Data sets support at most 10000 rows", "resource_limit")
            require(
                None not in row and all(v is not None for v in row.values()),
                "CSV row has wrong number of fields",
            )
            rows.append(row)
    except csv.Error as exc:
        raise VixlError("invalid_data", str(exc)) from exc
    require(rows, "CSV contains no data rows")
    root = Path(directory)
    destinations = [root / f"{i + 1:04d}.png" for i in range(len(rows))]
    require(not any(p.exists() for p in destinations), "Data output exists; use an empty directory")
    image_variables = {
        item["asset_variable"] for item in project.state["layers"] if item.get("asset_variable")
    }
    import tempfile

    checks = []
    with tempfile.TemporaryDirectory(prefix="vixl-data-") as staging:
        for i, row in enumerate(rows):
            candidate = project.clone()
            values = {**row, **(variables or {})}
            for key in image_variables & values.keys():
                if values[key] not in candidate.assets:
                    path = Path(values[key])
                    if not path.is_absolute():
                        path = Path(csv_path).resolve().parent / path
                    values[key], _ = add_encoded(
                        candidate, read_bounded(path, candidate.limits.max_asset_bytes)
                    )
            candidate.export(Path(staging) / f"{i}.png", variables=values, format="PNG", **options)
            if check:
                # Each row can break the design differently (long copy, clashing colors).
                from .checks import check_design

                report = check_design(
                    candidate, variables=values, artboard=options.get("artboard"), comp=options.get("comp")
                )
                checks.append({k: report[k] for k in ("passed", "errors", "warnings", "issues")} if report["issues"] else None)
        root.mkdir(parents=True, exist_ok=True)
        for i, path in enumerate(destinations):
            with path.open("xb") as stream:
                stream.write((Path(staging) / f"{i}.png").read_bytes())
    results = [{"row": i + 1, "output": str(path)} for i, path in enumerate(destinations)]
    for result, report in zip(results, checks):
        if report:
            result["check"] = report
    return results


ICON_SETS = {
    "web": [
        ("favicon-16x16.png", 16),
        ("favicon-32x32.png", 32),
        ("favicon-48x48.png", 48),
        ("apple-touch-icon.png", 180),
        ("android-chrome-192x192.png", 192),
        ("android-chrome-512x512.png", 512),
    ],
    "apple": [(f"apple-icon-{size}.png", size) for size in (20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024)],
    "android": [
        ("mipmap-mdpi.png", 48),
        ("mipmap-hdpi.png", 72),
        ("mipmap-xhdpi.png", 96),
        ("mipmap-xxhdpi.png", 144),
        ("mipmap-xxxhdpi.png", 192),
        ("play-store-512.png", 512),
    ],
    "windows": [(f"windows-tile-{size}.png", size) for size in (44, 71, 150, 310)],
}


def has_raster(project):
    return any(layer["type"] in ("raster", "frame") for layer in project.state["layers"])


def export_icons(project, directory, *, icon_set="web", sampling="smooth"):
    """Render once, then write a standard icon set (PNG sizes, ICO and a web manifest)."""
    from PIL import Image

    require(icon_set in (*ICON_SETS, "all"), "Icon set must be web, apple, android, windows or all")
    require(sampling in ("smooth", "nearest"), "Sampling must be smooth or nearest")
    entries = [item for name in (ICON_SETS if icon_set == "all" else [icon_set]) for item in ICON_SETS[name]]
    root = Path(directory)
    extras = ["favicon.ico", "site.webmanifest"] if icon_set in ("web", "all") else []
    if icon_set == "windows":
        extras = ["favicon.ico"]
    names = [name for name, _ in entries] + extras
    require(not any((root / name).exists() for name in names), "Icon output already exists; choose an empty folder")
    def squared(image):
        side = max(image.size)
        square = Image.new("RGBA", (side, side))
        square.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
        return square

    square = squared(project.render())
    side = square.width
    resample = Image.Resampling.NEAREST if sampling == "nearest" else Image.Resampling.LANCZOS
    largest = max(size for _, size in entries)
    if largest > side and sampling == "smooth":
        # Large icons re-render the design at their size instead of enlarging pixels.
        from .timeline import render_scaled

        large = squared(render_scaled(project, largest / side))
    files = {}
    for name, size in entries:
        stream = io.BytesIO()
        (large if size > side and sampling == "smooth" else square).resize((size, size), resample).save(stream, format="PNG")
        files[name] = stream.getvalue()
    if "favicon.ico" in extras:
        stream = io.BytesIO()
        sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= side]
        square.resize((min(side, 256), min(side, 256)), resample).save(stream, format="ICO", sizes=sizes or [(16, 16)])
        files["favicon.ico"] = stream.getvalue()
    if "site.webmanifest" in extras:
        manifest = {
            "icons": [
                {"src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
            ]
        }
        files["site.webmanifest"] = json.dumps(manifest, indent=2).encode()
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        with (root / name).open("xb") as stream:
            stream.write(data)
    result = {"directory": str(root), "files": sorted(files), "source_size": side}
    upscaled = sorted({size for _, size in entries if size > side})
    if upscaled and (sampling == "nearest" or has_raster(project)):
        result["warnings"] = [
            f"{', '.join(f'{s}px' for s in upscaled)} icons enlarge the {side}px design's images and may look soft; "
            "design on a 1024px canvas (vixl new app-icon) for crisp large icons"
        ]
    return result
