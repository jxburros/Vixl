"""Named document sizes: print in physical units, screens/social/icons/logos in pixels.

Print sizes are stored in inches or millimetres with a sensible default resolution, an
optional bleed and a safe (live-area) margin. ``resolve`` turns a name into pixel dimensions
plus the metadata the canvas keeps (dpi, bleed and safe insets) for guides, checks and
print export.
"""

from difflib import get_close_matches

from .errors import VixlError, require

CATEGORIES = (
    "print",
    "stationery",
    "photo",
    "poster",
    "packaging",
    "social",
    "web",
    "ads",
    "email",
    "video",
    "slides",
    "screens",
    "app-store",
    "icons",
    "logos",
    "game",
)

MM = "mm"
IN = "in"
PX = "px"


def _print(w, h, unit, description, dpi=300, category="print", bleed=None, safe=None):
    bleed = bleed if bleed is not None else (0.125 if unit == IN else 3)
    # Most desktop printers cannot print within about a quarter inch of the page edge.
    safe = safe if safe is not None else (0.25 if unit == IN else 6)
    return {"category": category, "width": w, "height": h, "unit": unit, "dpi": dpi, "bleed": bleed, "safe": safe, "description": description}


def _px(w, h, category, description, safe=0):
    return {"category": category, "width": w, "height": h, "unit": PX, "safe": safe, "description": description}


# Platform UI covers the top and bottom of a story; the sides only need a normal margin.
STORY_SAFE = {"top": 250, "bottom": 250, "left": 60, "right": 60}

SIDES = ("left", "top", "right", "bottom")


def safe_sides(canvas):
    """The canvas safe area as (left, top, right, bottom) pixel insets from the trim edge."""
    safe = canvas.get("safe", 0)
    return tuple(safe.get(side, 0) for side in SIDES) if isinstance(safe, dict) else (safe,) * 4


SIZES = {
    # Paper (US and ISO)
    "letter": _print(8.5, 11, IN, "US Letter paper; letterheads, flyers, handouts"),
    "legal": _print(8.5, 14, IN, "US Legal paper"),
    "tabloid": _print(11, 17, IN, "US Tabloid/Ledger; small posters and spreads"),
    "executive": _print(7.25, 10.5, IN, "US Executive paper"),
    "half-letter": _print(5.5, 8.5, IN, "Half US Letter; booklets, programs, small flyers"),
    "a0": _print(841, 1189, MM, "ISO A0 poster", dpi=150, category="poster"),
    "a1": _print(594, 841, MM, "ISO A1 poster", dpi=150, category="poster"),
    "a2": _print(420, 594, MM, "ISO A2 poster", dpi=200, category="poster"),
    "a3": _print(297, 420, MM, "ISO A3; small posters and spreads"),
    "a4": _print(210, 297, MM, "ISO A4 paper; letterheads, flyers, documents"),
    "a5": _print(148, 210, MM, "ISO A5; booklets, notebooks, flyers"),
    "a6": _print(105, 148, MM, "ISO A6; postcards and pocket flyers"),
    "a7": _print(74, 105, MM, "ISO A7; tickets and small cards"),
    "b4": _print(250, 353, MM, "ISO B4"),
    "b5": _print(176, 250, MM, "ISO B5; books and journals"),
    # Stationery and small print
    "business-card": _print(3.5, 2, IN, "US business card", category="stationery", safe=0.1875),
    "business-card-eu": _print(85, 55, MM, "European business card", category="stationery", safe=4),
    "business-card-jp": _print(91, 55, MM, "Japanese business card", category="stationery", safe=4),
    "letterhead": _print(8.5, 11, IN, "US Letter letterhead", category="stationery", safe=0.5),
    "letterhead-a4": _print(210, 297, MM, "A4 letterhead", category="stationery", safe=15),
    "envelope-10": _print(9.5, 4.125, IN, "US #10 business envelope", category="stationery", bleed=0, safe=0.375),
    "envelope-dl": _print(220, 110, MM, "DL envelope", category="stationery", bleed=0, safe=10),
    "envelope-c5": _print(229, 162, MM, "C5 envelope (A5 contents)", category="stationery", bleed=0, safe=10),
    "postcard": _print(6, 4, IN, "US 4×6 postcard", category="stationery"),
    "postcard-5x7": _print(7, 5, IN, "5×7 postcard or announcement", category="stationery"),
    "invitation": _print(5, 7, IN, "5×7 invitation or greeting card", category="stationery"),
    "greeting-card": _print(5, 7, IN, "5×7 folded greeting card face", category="stationery"),
    "certificate": _print(11, 8.5, IN, "Landscape US Letter certificate", category="stationery", safe=0.5),
    "rack-card": _print(4, 9, IN, "4×9 rack card", category="stationery"),
    "door-hanger": _print(4.25, 11, IN, "4.25×11 door hanger", category="stationery"),
    "bookmark": _print(2, 6, IN, "2×6 bookmark", category="stationery"),
    "sticker": _print(3, 3, IN, "3-inch square sticker", category="stationery"),
    "label": _print(4, 6, IN, "4×6 shipping/product label", category="stationery", bleed=0),
    "ticket": _print(5.5, 2, IN, "Event ticket", category="stationery"),
    "menu": _print(8.5, 14, IN, "Legal-size restaurant menu", category="stationery", safe=0.375),
    "book-6x9": _print(6, 9, IN, "6×9 trade paperback page", category="stationery", safe=0.5),
    "book-5.5x8.5": _print(5.5, 8.5, IN, "Digest paperback page", category="stationery", safe=0.5),
    "magazine": _print(8.375, 10.875, IN, "US magazine page", category="stationery", safe=0.375),
    # Photos
    "photo-4x6": _print(4, 6, IN, "4×6 photo print", category="photo", bleed=0, safe=0.125),
    "photo-5x7": _print(5, 7, IN, "5×7 photo print", category="photo", bleed=0, safe=0.125),
    "photo-8x10": _print(8, 10, IN, "8×10 photo print", category="photo", bleed=0, safe=0.25),
    "photo-square": _print(8, 8, IN, "8×8 square photo print", category="photo", bleed=0, safe=0.25),
    # Posters
    "poster-11x17": _print(11, 17, IN, "11×17 poster", category="poster", dpi=300),
    "poster-18x24": _print(18, 24, IN, "18×24 poster", category="poster", dpi=150, safe=0.5),
    "poster-24x36": _print(24, 36, IN, "24×36 poster", category="poster", dpi=150, safe=0.75),
    "poster-27x40": _print(27, 40, IN, "27×40 one-sheet movie poster", category="poster", dpi=150, safe=0.75),
    # Packaging and merchandise
    "cd-cover": _print(4.75, 4.75, IN, "CD booklet cover", category="packaging"),
    "vinyl-cover": _print(12.375, 12.375, IN, "12-inch vinyl LP jacket", category="packaging"),
    "album-art": _px(3000, 3000, "packaging", "Streaming album artwork (3000×3000)", safe=150),
    "tshirt-print": _print(12, 16, IN, "T-shirt front print area", category="packaging", bleed=0, safe=0),
    "tote-print": _print(10, 10, IN, "Tote bag print area", category="packaging", bleed=0, safe=0),
    "mug-wrap": _print(8.5, 3.5, IN, "11 oz mug wrap", category="packaging", bleed=0, safe=0.25),
    # Social
    "instagram-square": _px(1080, 1080, "social", "Instagram square post", safe=60),
    "instagram-post": _px(1080, 1080, "social", "Instagram square post (alias)", safe=60),
    "instagram-portrait": _px(1080, 1350, "social", "Instagram 4:5 portrait post", safe=60),
    "instagram-landscape": _px(1080, 566, "social", "Instagram 1.91:1 landscape post", safe=40),
    "instagram-story": _px(1080, 1920, "social", "Instagram/Facebook story; keep text out of top/bottom 250px", safe=STORY_SAFE),
    "story": _px(1080, 1920, "social", "Vertical 9:16 story", safe=STORY_SAFE),
    "reel-cover": _px(1080, 1920, "social", "Reel/short cover; center 1080×1440 shows in grids", safe={"top": 240, "bottom": 240, "left": 60, "right": 60}),
    "facebook-post": _px(1200, 630, "social", "Facebook link/feed image", safe=40),
    "facebook-cover": _px(1640, 624, "social", "Facebook page cover (high resolution)", safe=80),
    "facebook-event": _px(1920, 1005, "social", "Facebook event cover", safe=60),
    "x-post": _px(1600, 900, "social", "X/Twitter in-feed image", safe=50),
    "x-header": _px(1500, 500, "social", "X/Twitter profile header", safe=60),
    "linkedin-post": _px(1200, 627, "social", "LinkedIn shared image", safe=40),
    "linkedin-banner": _px(1584, 396, "social", "LinkedIn personal profile banner", safe=40),
    "linkedin-cover": _px(1128, 191, "social", "LinkedIn company page cover", safe=20),
    "youtube-thumbnail": _px(1280, 720, "social", "YouTube video thumbnail; timestamp covers bottom-right", safe=40),
    "youtube-banner": _px(2560, 1440, "social", "YouTube channel art; keep logos/text in center 1546×423", safe=0),
    "youtube-profile": _px(800, 800, "social", "YouTube profile picture (shown as a circle)", safe=120),
    "pinterest-pin": _px(1000, 1500, "social", "Pinterest 2:3 pin", safe=60),
    "pinterest-long": _px(1000, 2100, "social", "Pinterest long pin", safe=60),
    "tiktok": _px(1080, 1920, "social", "TikTok vertical video/cover; UI overlays the right and bottom", safe=160),
    "twitch-banner": _px(1200, 480, "social", "Twitch profile banner", safe=40),
    "twitch-panel": _px(320, 160, "social", "Twitch channel panel", safe=10),
    "twitch-offline": _px(1920, 1080, "social", "Twitch offline screen", safe=80),
    "discord": _px(512, 512, "social", "Discord server icon", safe=40),
    "discord-banner": _px(960, 540, "social", "Discord server banner", safe=40),
    "discord-emoji": _px(128, 128, "social", "Discord custom emoji", safe=4),
    "profile-picture": _px(800, 800, "social", "Generic avatar (often cropped to a circle)", safe=120),
    # Web
    "og-image": _px(1200, 630, "web", "Open Graph / link-preview image", safe=60),
    "web-hero": _px(1920, 1080, "web", "Full-width website hero", safe=120),
    "web-hero-wide": _px(2560, 1080, "web", "Ultra-wide website hero", safe=160),
    "blog-featured": _px(1200, 628, "web", "Blog featured image", safe=40),
    "web-banner": _px(1920, 600, "web", "Website section banner", safe=80),
    # Display advertising (IAB)
    "medium-rectangle": _px(300, 250, "ads", "IAB medium rectangle ad", safe=8),
    "large-rectangle": _px(336, 280, "ads", "IAB large rectangle ad", safe=8),
    "leaderboard": _px(728, 90, "ads", "IAB leaderboard ad", safe=6),
    "billboard": _px(970, 250, "ads", "IAB billboard ad", safe=10),
    "half-page": _px(300, 600, "ads", "IAB half-page ad", safe=10),
    "wide-skyscraper": _px(160, 600, "ads", "IAB wide skyscraper ad", safe=8),
    "mobile-banner": _px(320, 50, "ads", "IAB mobile banner ad", safe=4),
    "mobile-interstitial": _px(320, 480, "ads", "Mobile interstitial ad", safe=12),
    # Email
    "email-header": _px(600, 200, "email", "Email newsletter header (600px wide)", safe=20),
    "email-banner": _px(600, 300, "email", "Email body banner", safe=20),
    "email-signature": _px(600, 150, "email", "Email signature banner", safe=10),
    # Video
    "video-720p": _px(1280, 720, "video", "HD 720p frame", safe=64),
    "video-1080p": _px(1920, 1080, "video", "Full HD 1080p frame; title safe 10%", safe=96),
    "video-4k": _px(3840, 2160, "video", "UHD 4K frame", safe=192),
    "video-vertical": _px(1080, 1920, "video", "Vertical 9:16 video frame", safe=160),
    "video-square": _px(1080, 1080, "video", "Square video frame", safe=60),
    # Slides
    "slide": _px(1920, 1080, "slides", "16:9 presentation slide", safe=96),
    "slide-4x3": _px(1024, 768, "slides", "4:3 presentation slide", safe=48),
    "slide-16x10": _px(1920, 1200, "slides", "16:10 presentation slide", safe=96),
    # Screens and wallpapers
    "desktop-hd": _px(1920, 1080, "screens", "1080p desktop wallpaper", safe=0),
    "desktop-qhd": _px(2560, 1440, "screens", "1440p desktop wallpaper", safe=0),
    "desktop-4k": _px(3840, 2160, "screens", "4K desktop wallpaper", safe=0),
    "phone-wallpaper": _px(1290, 2796, "screens", "Modern phone lock/home screen", safe=240),
    "tablet-wallpaper": _px(2048, 2732, "screens", "Tablet wallpaper", safe=160),
    # App stores
    "iphone-screenshot": _px(1290, 2796, "app-store", "App Store 6.7-inch iPhone screenshot", safe=80),
    "iphone-screenshot-6.9": _px(1320, 2868, "app-store", "App Store 6.9-inch iPhone screenshot", safe=80),
    "ipad-screenshot": _px(2064, 2752, "app-store", "App Store 13-inch iPad screenshot", safe=100),
    "android-screenshot": _px(1080, 1920, "app-store", "Google Play phone screenshot", safe=60),
    "play-feature-graphic": _px(1024, 500, "app-store", "Google Play feature graphic", safe=40),
    # Icons (square masters; export an icon set or ICO for small sizes)
    "favicon": _px(512, 512, "icons", "Favicon master; export ICO 16–256 and PNG 32/180/192/512", safe=32),
    "favicon-16": _px(16, 16, "icons", "16px favicon", safe=0),
    "favicon-32": _px(32, 32, "icons", "32px favicon", safe=0),
    "favicon-48": _px(48, 48, "icons", "48px favicon", safe=1),
    "apple-touch-icon": _px(180, 180, "icons", "iOS home-screen web icon", safe=12),
    "android-chrome-192": _px(192, 192, "icons", "Android/PWA icon", safe=12),
    "android-chrome-512": _px(512, 512, "icons", "Android/PWA large icon", safe=32),
    "pwa-maskable": _px(512, 512, "icons", "PWA maskable icon; keep content inside the central 80% circle", safe=52),
    "android-adaptive-icon": _px(432, 432, "icons", "Android adaptive icon layer; safe zone is the central 66/108", safe=84),
    "ios-app-icon": _px(1024, 1024, "icons", "iOS/iPadOS App Store icon (system applies the rounded mask)", safe=80),
    "macos-app-icon": _px(1024, 1024, "icons", "macOS app icon; artwork in the 824px rounded square", safe=100),
    "windows-tile": _px(310, 310, "icons", "Windows large tile", safe=24),
    "app-icon": _px(1024, 1024, "icons", "Generic app icon master", safe=80),
    "icon-16": _px(16, 16, "icons", "16px UI icon", safe=1),
    "icon-24": _px(24, 24, "icons", "24px UI icon on a 2px keyline", safe=2),
    "icon-32": _px(32, 32, "icons", "32px UI icon", safe=2),
    "icon-48": _px(48, 48, "icons", "48px UI icon", safe=4),
    "icon-64": _px(64, 64, "icons", "64px UI icon", safe=4),
    "icon-128": _px(128, 128, "icons", "128px icon", safe=8),
    "icon-256": _px(256, 256, "icons", "256px icon", safe=16),
    # Logos
    "logo": _px(1000, 1000, "logos", "Square logo master (mark or stacked lockup)", safe=100),
    "logo-mark": _px(512, 512, "logos", "Symbol/mark only", safe=48),
    "logo-horizontal": _px(1600, 600, "logos", "Horizontal lockup: mark beside wordmark", safe=60),
    "logo-stacked": _px(1000, 1200, "logos", "Stacked lockup: mark above wordmark", safe=80),
    "wordmark": _px(1600, 400, "logos", "Wordmark/logotype only", safe=40),
    "logo-wide": _px(2000, 500, "logos", "Wide banner logo", safe=50),
    "logo-badge": _px(1000, 1000, "logos", "Emblem/badge logo (circular or shield)", safe=60),
    "logo-avatar": _px(800, 800, "logos", "Logo for circular social avatars", safe=140),
    "email-logo": _px(400, 120, "logos", "Email/signature logo (display at 200×60)", safe=8),
    # Games and pixel art
    "sprite-16": _px(16, 16, "game", "16×16 sprite", safe=0),
    "sprite-32": _px(32, 32, "game", "32×32 sprite", safe=0),
    "sprite-64": _px(64, 64, "game", "64×64 sprite", safe=0),
    "tile-16": _px(16, 16, "game", "16×16 tile", safe=0),
    "tile-32": _px(32, 32, "game", "32×32 tile", safe=0),
    "game-cover": _px(630, 500, "game", "Indie storefront cover image", safe=30),
    "game-banner": _px(1920, 620, "game", "Game page banner", safe=80),
}
ALIASES = {
    "us-letter": "letter",
    "a4-paper": "a4",
    "flyer": "letter",
    "flyer-a4": "a4",
    "half-page-flyer": "half-letter",
    "ledger": "tabloid",
    "postcard-4x6": "postcard",
    "postcard-a6": "a6",
    "business-card-us": "business-card",
    "youtube": "youtube-thumbnail",
    "thumbnail": "youtube-thumbnail",
    "twitter-post": "x-post",
    "twitter-header": "x-header",
    "open-graph": "og-image",
    "instagram-reel": "story",
    "reel": "story",
    "presentation": "slide",
    "slide-16x9": "slide",
    "hd": "video-1080p",
    "1080p": "video-1080p",
    "4k": "video-4k",
    "app-icon-ios": "ios-app-icon",
    "logo-square": "logo",
    "logo-vertical": "logo-stacked",
    "logotype": "wordmark",
    "avatar": "profile-picture",
}
UNIT_INCHES = {IN: 1.0, MM: 1 / 25.4, "cm": 1 / 2.54, "pt": 1 / 72}


def canonical(name):
    require(isinstance(name, str) and name, "Size name must be a string")
    key = name.strip().lower().replace("_", "-").replace(" ", "-")
    key = ALIASES.get(key, key)
    if key not in SIZES:
        close = get_close_matches(key, list(SIZES) + list(ALIASES), 3, 0.6)
        raise VixlError(
            "unknown_size",
            f"Unknown size {name!r}" + (f"; did you mean {', '.join(close)}?" if close else "; run vixl sizes"),
            field="size",
            suggestions=close,
        )
    return key


def to_pixels(value, unit, dpi):
    if unit == PX:
        return value
    return value * UNIT_INCHES[unit] * dpi


def resolve(name, *, dpi=None, orientation=None, bleed=False):
    """Pixel dimensions and print metadata for a named size.

    ``bleed`` adds the entry's standard bleed on every side (True) or a custom amount in the
    entry's unit. The canvas then measures trim + 2 × bleed, and ``safe`` is measured from
    the trim edge inward.
    """
    key = canonical(name)
    entry = SIZES[key]
    unit = entry["unit"]
    physical = unit != PX
    if dpi is not None:
        require(physical, f"{key} is a pixel size; dpi applies to print sizes", field="dpi")
        require(isinstance(dpi, (int, float)) and 36 <= dpi <= 2400, "dpi must be 36–2400", field="dpi")
    dpi = dpi or entry.get("dpi")
    w, h = entry["width"], entry["height"]
    require(orientation in (None, "portrait", "landscape", "square"), "orientation must be portrait or landscape")
    if orientation == "portrait" and w > h or orientation == "landscape" and h > w:
        w, h = h, w
    if bleed is True:
        require(physical, "Bleed applies to print sizes", field="bleed")
        bleed_amount = entry.get("bleed", 0)
    elif bleed:
        require(isinstance(bleed, (int, float)) and 0 <= bleed, "bleed must be a nonnegative number", field="bleed")
        bleed_amount = bleed
    else:
        bleed_amount = 0
    trim_w = round(to_pixels(w, unit, dpi or 1))
    trim_h = round(to_pixels(h, unit, dpi or 1))
    bleed_px = round(to_pixels(bleed_amount, unit, dpi or 1))
    safe = entry.get("safe", 0)
    safe_px = ({side: round(to_pixels(safe.get(side, 0), unit, dpi or 1)) for side in SIDES}
               if isinstance(safe, dict) else round(to_pixels(safe, unit, dpi or 1)))
    result = {
        "size": key,
        "category": entry["category"],
        "description": entry["description"],
        "width": trim_w + 2 * bleed_px,
        "height": trim_h + 2 * bleed_px,
        "trim": [trim_w, trim_h],
        "bleed": bleed_px,
        "safe": safe_px,
    }
    if physical:
        result.update(dpi=dpi, physical={"width": w, "height": h, "unit": unit, "bleed": bleed_amount})
    return result


def summary(key):
    entry = SIZES[key]
    item = {"name": key, "category": entry["category"], "description": entry["description"]}
    if entry["unit"] == PX:
        item["pixels"] = [entry["width"], entry["height"]]
    else:
        info = resolve(key)
        item.update(
            physical=f"{entry['width']}×{entry['height']} {entry['unit']}",
            dpi=entry["dpi"],
            pixels=info["trim"],
        )
    return item


def catalog(category=None, search=None):
    require(category is None or category in CATEGORIES, f"Unknown size category; use {', '.join(CATEGORIES)}")
    items = []
    for key, entry in SIZES.items():
        if category and entry["category"] != category:
            continue
        if search and search.lower() not in (key + " " + entry["description"]).lower():
            continue
        items.append(summary(key))
    return {"categories": list(CATEGORIES), "sizes": items, "aliases": ALIASES}


def size_guides(info):
    """Generated trim/safe guides for a resolved size (positions include any bleed)."""
    guides = {}
    w, h, bleed, safe = info["width"], info["height"], info["bleed"], info["safe"]
    if bleed:
        for name, axis, position in (
            ("trim-left", "x", bleed),
            ("trim-right", "x", w - bleed),
            ("trim-top", "y", bleed),
            ("trim-bottom", "y", h - bleed),
        ):
            guides[name] = {"axis": axis, "position": position, "generated": "size"}
    if safe:
        sides = safe_sides({"safe": safe})
        left, top, right, bottom = (bleed + v for v in sides)
        if left + right < w and top + bottom < h:
            for (name, axis, position), side in zip((
                ("safe-left", "x", left),
                ("safe-top", "y", top),
                ("safe-right", "x", w - right),
                ("safe-bottom", "y", h - bottom),
            ), sides):
                if side:
                    guides[name] = {"axis": axis, "position": position, "generated": "size"}
    return guides


def replace_generated_guides(state, new_guides):
    """Swap the size-generated trim/safe guides; any a layer is constrained to are kept as plain guides."""
    guides = state.setdefault("guides", {})
    referenced = {
        expression.split(".")[0][6:]
        for layer in state["layers"]
        for expression in layer.get("constraints", {}).values()
        if isinstance(expression, str) and expression.startswith("guide:")
    }
    for key in [k for k, v in guides.items() if v.get("generated") == "size"]:
        if key in referenced and key not in new_guides:
            guides[key] = {k: v for k, v in guides[key].items() if k != "generated"}
        else:
            del guides[key]
    guides.update(new_guides)
    if not guides:
        state.pop("guides")


def apply_size(project, op):
    """Execute ``canvas`` with ``size``/``preset``: resize and record print metadata."""
    from .render import color
    from .design import resolve_color

    name = op.get("size", op.get("preset"))
    info = resolve(name, dpi=op.get("dpi"), orientation=op.get("orientation"), bleed=op.get("bleed", False))
    project.limits.size(info["width"], info["height"])
    c = project.state["canvas"]
    background = op.get("background", c["background"])
    color(resolve_color(background, project.state))
    for key in ("size", "dpi", "bleed", "safe", "physical"):
        c.pop(key, None)
    c.update(width=info["width"], height=info["height"], background=background, size=info["size"])
    for key in ("dpi", "physical"):
        if key in info:
            c[key] = info[key]
    if info["bleed"]:
        c["bleed"] = info["bleed"]
    if info["safe"]:
        c["safe"] = info["safe"]
    replace_generated_guides(project.state, size_guides(info))
    return info


CANVAS_KEYS = {"width", "height", "background", "color_mode", "size", "dpi", "bleed", "safe", "physical"}


def validate_canvas(canvas):
    from .model import finite

    require(set(canvas) <= CANVAS_KEYS, "Unknown canvas field", "invalid_project")
    if "size" in canvas:
        canonical(canvas["size"])
    if "dpi" in canvas:
        finite(canvas["dpi"], "dpi", 36, 2400)
    for key in ("bleed", "safe"):
        if key in canvas:
            value = canvas[key]
            limit = min(canvas["width"], canvas["height"])
            if key == "safe" and isinstance(value, dict):
                require(set(value) <= set(SIDES) and all(isinstance(v, int) and 0 <= v < limit for v in value.values()),
                        "Invalid canvas safe", "invalid_project")
            else:
                require(isinstance(value, int) and 0 <= value < limit, f"Invalid canvas {key}", "invalid_project")
    if "physical" in canvas:
        physical = canvas["physical"]
        require(isinstance(physical, dict) and set(physical) <= {"width", "height", "unit", "bleed"} and physical.get("unit") in UNIT_INCHES, "Invalid physical canvas size", "invalid_project")
