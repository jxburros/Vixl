"""Render intro.html frame by frame with headless Chromium (Playwright), then encode with ffmpeg.

Usage: python3 render.py            -> frames/ + intro.mp4 + intro.gif + intro-last-frame.png
       python3 render.py 0.5 2.5 ...  -> only stills at those times (preview-*.png)
"""
import pathlib, shutil, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
FPS, DURATION, SIZE = 30, 8.0, 1080
N = int(round(FPS * DURATION))  # 240 frames, t = i/30


def main():
    stills = [float(a) for a in sys.argv[1:]]
    frames = HERE / "frames"
    if not stills:
        shutil.rmtree(frames, ignore_errors=True)
        frames.mkdir()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE}, device_scale_factor=1)
        page.goto((HERE / "intro.html").as_uri() + "?render=1")
        page.evaluate("document.fonts.ready")
        if stills:
            for t in stills:
                page.evaluate(f"renderAt({t})")
                page.screenshot(path=str(HERE / f"preview-{t:.2f}.png"))
        else:
            for i in range(N):
                page.evaluate(f"renderAt({i / FPS})")
                page.screenshot(path=str(frames / f"f{i:04d}.png"))
        browser.close()
    if stills:
        return

    shutil.copy(frames / f"f{N - 1:04d}.png", HERE / "intro-last-frame.png")
    run = lambda *a: subprocess.run(a, check=True)
    run("ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%04d.png"),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-movflags", "+faststart", str(HERE / "intro.mp4"))
    pal = HERE / "palette.png"
    vf = "scale=540:540:flags=lanczos"
    run("ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%04d.png"),
        "-vf", f"{vf},palettegen=max_colors=128:stats_mode=diff", str(pal))
    run("ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%04d.png"),
        "-i", str(pal), "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
        "-loop", "0", str(HERE / "intro.gif"))
    pal.unlink()


if __name__ == "__main__":
    main()
