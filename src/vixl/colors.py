"""Color language: CSS Color 4/5 notations, print/device spaces, color functions and harmonies.

Every color string in Vixl goes through :func:`parse`. It accepts what designers and models
write: CSS names, ``#rgb[a]``/``#rrggbb[aa]``, ``rgb()``/``hsl()``/``hwb()``/``lab()``/``lch()``/
``oklab()``/``oklch()``, ``color(display-p3 …)``, ``cmyk()``/``device-cmyk()``, ``gray()``,
``kelvin()``, CSS ``color-mix()``, and modifiers such as ``lighten(@brand, 10%)``. Results are
gamut-mapped to sRGB (chroma reduction in OKLCH), because documents stay RGBA8. Print output is
converted at export time (see :func:`cmyk_image`).
"""

import contextvars
from functools import lru_cache
import json
import math
from pathlib import Path
import re

from .errors import VixlError, require

# Transfer functions and matrices use the CSS Color 4 reference values.

SRGB_TO_XYZ = (
    (0.41239079926595934, 0.357584339383878, 0.1804807884018343),
    (0.21263900587151027, 0.715168678767756, 0.07219231536073371),
    (0.01933081871559182, 0.11919477979462598, 0.9505321522496607),
)
XYZ_TO_SRGB = (
    (3.2409699419045226, -1.537383177570094, -0.4986107602930034),
    (-0.9692436362808796, 1.8759675015077202, 0.04155505740717559),
    (0.05563007969699366, -0.20397695888897652, 1.0569715142428786),
)
P3_TO_XYZ = (
    (0.4865709486482162, 0.26566769316909306, 0.1982172852343625),
    (0.2289745640697488, 0.6917385218365064, 0.079286914093745),
    (0.0, 0.04511338185890264, 1.043944368900976),
)
REC2020_TO_XYZ = (
    (0.6369580483012914, 0.14461690358620832, 0.1688809751641721),
    (0.2627002120112671, 0.6779980715188708, 0.05930171646986196),
    (0.0, 0.028072693049087428, 1.060985057710791),
)
D65_TO_D50 = (
    (1.0479298208405488, 0.022946793341019088, -0.05019222954313557),
    (0.029627815688159344, 0.990434484573249, -0.01707382502938514),
    (-0.009243058152591178, 0.015055144896577895, 0.7518742899580008),
)
D50_TO_D65 = (
    (0.9554734527042182, -0.023098536874261423, 0.0632593086610217),
    (-0.028369706963208136, 1.0099954580058226, 0.021041398966943008),
    (0.012314001688319899, -0.020507696433477912, 1.3303659366080753),
)
D50_WHITE = (0.3457 / 0.3585, 1.0, (1 - 0.3457 - 0.3585) / 0.3585)
LAB_E, LAB_K = 216 / 24389, 24389 / 27

SPACES = (
    "srgb",
    "srgb-linear",
    "display-p3",
    "rec2020",
    "xyz",
    "xyz-d65",
    "xyz-d50",
    "lab",
    "lch",
    "oklab",
    "oklch",
    "hsl",
    "hsv",
    "hwb",
    "cmyk",
)
HARMONIES = (
    "complementary",
    "analogous",
    "triadic",
    "split-complementary",
    "tetradic",
    "square",
    "monochromatic",
    "tints",
    "shades",
    "tones",
)
VISION = ("protanopia", "deuteranopia", "tritanopia", "achromatopsia")
# Machado, Oliveira & Fernandes (2009), severity 1.0, applied to linear RGB.
CVD = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def _mul(matrix, vector):
    return tuple(sum(m * v for m, v in zip(row, vector)) for row in matrix)


def to_linear(c):
    sign = -1 if c < 0 else 1
    c = abs(c)
    return sign * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)


def from_linear(c):
    sign = -1 if c < 0 else 1
    c = abs(c)
    return sign * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def _rec2020_linear(v):
    a, b = 1.09929682680944, 0.018053968510807
    sign = -1 if v < 0 else 1
    v = abs(v)
    return sign * (v / 4.5 if v < b * 4.5 else ((v + a - 1) / a) ** (1 / 0.45))


def _cbrt(v):
    return math.copysign(abs(v) ** (1 / 3), v)


def linear_to_oklab(rgb):
    r, g, b = rgb
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (_cbrt(v) for v in lms)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_linear(lab):
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    long_, medium, short = l_**3, m_**3, s_**3
    return (
        4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short,
    )


def xyz50_to_lab(xyz):
    f = [_cbrt(v / w) if v / w > LAB_E else (LAB_K * v / w + 16) / 116 for v, w in zip(xyz, D50_WHITE)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def lab_to_xyz50(lab):
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    x = fx**3 if fx**3 > LAB_E else (116 * fx - 16) / LAB_K
    y = ((L + 16) / 116) ** 3 if L > LAB_K * LAB_E else L / LAB_K
    z = fz**3 if fz**3 > LAB_E else (116 * fz - 16) / LAB_K
    return x * D50_WHITE[0], y * D50_WHITE[1], z * D50_WHITE[2]


def to_polar(lab):
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_polar(lch):
    L, C, H = lch
    return L, C * math.cos(math.radians(H)), C * math.sin(math.radians(H))


# Encoded sRGB floats (0–1) are the canonical internal form.


def srgb_to_linear(rgb):
    return tuple(to_linear(c) for c in rgb)


def linear_to_srgb(rgb):
    return tuple(from_linear(c) for c in rgb)


def srgb_to_oklab(rgb):
    return linear_to_oklab(srgb_to_linear(rgb))


def oklab_to_srgb(lab):
    return linear_to_srgb(oklab_to_linear(lab))


def srgb_to_lab(rgb):
    return xyz50_to_lab(_mul(D65_TO_D50, _mul(SRGB_TO_XYZ, srgb_to_linear(rgb))))


def lab_to_srgb(lab):
    return linear_to_srgb(_mul(XYZ_TO_SRGB, _mul(D50_TO_D65, lab_to_xyz50(lab))))


def srgb_to_hsl(rgb):
    r, g, b = rgb
    high, low = max(rgb), min(rgb)
    lightness = (high + low) / 2
    delta = high - low
    if delta < 1e-12:
        return 0.0, 0.0, lightness
    saturation = delta / (1 - abs(2 * lightness - 1)) if 0 < lightness < 1 else 0
    return _hue(r, g, b, high, delta), saturation, lightness


def srgb_to_hsv(rgb):
    r, g, b = rgb
    high, low = max(rgb), min(rgb)
    delta = high - low
    return (_hue(r, g, b, high, delta) if delta > 1e-12 else 0.0), (delta / high if high else 0.0), high


def _hue(r, g, b, high, delta):
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60 % 360


def hsl_to_srgb(h, s, light):
    s = min(max(s, 0), 1)
    light = min(max(light, 0), 1)

    def f(n):
        k = (n + h / 30) % 12
        return light - s * min(light, 1 - light) * max(-1, min(k - 3, 9 - k, 1))

    return f(0), f(8), f(4)


def hsv_to_srgb(h, s, v):
    s = min(max(s, 0), 1)
    v = min(max(v, 0), 1)

    def f(n):
        k = (n + h / 60) % 6
        return v - v * s * max(0, min(k, 4 - k, 1))

    return f(5), f(3), f(1)


def hwb_to_srgb(h, w, b):
    if w + b >= 1:
        gray = w / (w + b)
        return gray, gray, gray
    return tuple(c * (1 - w - b) + w for c in hsl_to_srgb(h, 1, 0.5))


def srgb_to_hwb(rgb):
    h, _, v = srgb_to_hsv(rgb)
    return h, min(rgb), 1 - v


def cmyk_to_srgb(c, m, y, k):
    return (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)


def srgb_to_cmyk(rgb, black=1.0, ink_limit=None):
    """Device-naive CMYK with gray-component replacement; ``black`` is the GCR fraction (0–1).

    ``ink_limit`` caps total area coverage (for example 3.0 for 300%) by reducing CMY first.
    This is a predictable approximation for proofing and press-ready plates when no ICC
    profile is supplied; supply the printer's CMYK profile for accurate separations.
    """
    r, g, b = (min(max(v, 0.0), 1.0) for v in rgb)
    c, m, y = 1 - r, 1 - g, 1 - b
    k = min(c, m, y) * black
    if k >= 1 - 1e-9:
        return 0.0, 0.0, 0.0, 1.0
    c, m, y = ((v - k) / (1 - k) for v in (c, m, y))
    if ink_limit is not None and c + m + y + k > ink_limit:
        room = max(0.0, ink_limit - k)
        total = c + m + y
        if total > 0:
            c, m, y = (v * room / total for v in (c, m, y))
    return c, m, y, k


def relative_luminance(rgb):
    r, g, b = srgb_to_linear(rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def in_gamut(rgb, epsilon=1e-4):
    return all(-epsilon <= c <= 1 + epsilon for c in rgb)


# While ``clipped`` parses a colour, the ways it was brought into sRGB.
_GAMUT = contextvars.ContextVar("vixl_gamut", default=None)


def _gamut_event(kind):
    events = _GAMUT.get()
    if events is not None:
        events.append(kind)


def gamut_map(oklab):
    """Map an OKLab color into sRGB by reducing chroma at constant lightness and hue."""
    rgb = oklab_to_srgb(oklab)
    if in_gamut(rgb):
        return tuple(min(max(c, 0.0), 1.0) for c in rgb)
    _gamut_event("chroma")
    L, C, H = to_polar(oklab)
    if L >= 1:
        return 1.0, 1.0, 1.0
    if L <= 0:
        return 0.0, 0.0, 0.0
    low, high = 0.0, C
    for _ in range(24):
        middle = (low + high) / 2
        if in_gamut(oklab_to_srgb(from_polar((L, middle, H)))):
            low = middle
        else:
            high = middle
    return tuple(min(max(c, 0.0), 1.0) for c in oklab_to_srgb(from_polar((L, low, H))))


def from_linear_space(linear, matrix):
    """Wide-gamut linear RGB → gamut-mapped encoded sRGB."""
    srgb_linear = _mul(XYZ_TO_SRGB, _mul(matrix, linear))
    return gamut_map(linear_to_oklab(srgb_linear))


def kelvin_to_srgb(kelvin):
    """Blackbody color temperature (1000–40000 K), Tanner Helland's fit."""
    t = kelvin / 100
    if t <= 66:
        r = 255
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
        b = 255
    return tuple(min(max(v, 0), 255) / 255 for v in (r, g, b))


@lru_cache(maxsize=1)
def _css_names():
    """CSS color names as hex. Pillow replaces its own table entries with parsed tuples after first
    use, so both forms are accepted (and the table is never mutated here)."""
    from PIL import ImageColor

    result = {}
    for name, value in ImageColor.colormap.items():
        if isinstance(value, str):
            result[name] = value.lower()
        elif isinstance(value, tuple) and len(value) >= 3:
            result[name] = "#{:02x}{:02x}{:02x}".format(*value[:3])
    return result


@lru_cache(maxsize=1)
def named_colors():
    """CSS names (authoritative) plus the CC0 xkcd survey names (``xkcd:`` or plain if free)."""
    css = _css_names()
    data = json.loads((Path(__file__).parent / "data" / "xkcd-colors.json").read_text("utf-8"))["colors"]
    names = {}
    for name, value in data.items():
        names["xkcd:" + name] = value
        names.setdefault(name, value)
    for name, value in data.items():
        names.setdefault(name.replace("-", ""), value)  # "dustyrose" as well as "dusty rose".
    names.update(css)
    return names


def _name_key(text):
    text = text.strip().lower()
    prefix = ""
    if text.startswith("xkcd:"):
        prefix, text = "xkcd:", text[5:]
    return prefix + re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def lookup_name(text):
    names = named_colors()
    key = _name_key(text)
    if key in names:
        return names[key]
    compact = key.replace("-", "")
    if compact in names:  # CSS names have no hyphens: "dark-slate-blue" → "darkslateblue".
        return names[compact]
    return None


@lru_cache(maxsize=1)
def _canonical_names():
    """CSS names plus hyphenated xkcd names, without the prefixed and compact duplicates."""
    names = _css_names()
    data = json.loads((Path(__file__).parent / "data" / "xkcd-colors.json").read_text("utf-8"))["colors"]
    for name, value in data.items():
        names.setdefault(name, value)
    return names


@lru_cache(maxsize=1)
def _name_index():
    return [(name, value, srgb_to_oklab(_hex(value)[:3])) for name, value in _canonical_names().items()]


def nearest_names(rgb, count=3):
    target = srgb_to_oklab(rgb[:3])
    scored = sorted(
        (math.dist(target, lab), name, value) for name, value, lab in _name_index()
    )
    return [{"name": name, "hex": value, "distance": round(distance, 4)} for distance, name, value in scored[:count]]


TOKEN = re.compile(
    r"\s*(?:(?P<hex>#[0-9a-fA-F]+)|(?P<num>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)(?P<unit>%|deg|grad|rad|turn)?"
    r"|(?P<ident>[A-Za-z_][\w:-]*)|(?P<punct>[(),/]))"
)
MAX_DEPTH = 8


class _Tokens:
    def __init__(self, text):
        self.items, position = [], 0
        while position < len(text):
            if text[position:].strip() == "":
                break
            match = TOKEN.match(text, position)
            require(match and match.end() > position, f"Invalid color syntax near {text[position:position + 12]!r}", "invalid_color")
            kind = next(k for k in ("hex", "num", "ident", "punct") if match[k] is not None)
            value = match[kind]
            if kind == "num":
                value = (float(value), match["unit"] or "")
            self.items.append((kind, value))
            position = match.end()
        self.index = 0

    def peek(self):
        return self.items[self.index] if self.index < len(self.items) else (None, None)

    def take(self):
        item = self.peek()
        self.index += 1
        return item


def _hex(text):
    digits = text.lstrip("#")
    require(len(digits) in (3, 4, 6, 8), f"Invalid hex color {text!r}", "invalid_color")
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    values = [int(digits[i : i + 2], 16) / 255 for i in range(0, len(digits), 2)]
    return tuple(values + [1.0] * (4 - len(values)))


def _argument_groups(tokens, depth):
    """Read a parenthesized argument list into comma groups of values; '/' introduces alpha."""
    kind, value = tokens.take()
    require(value == "(", "Expected '(' after color function", "invalid_color")
    groups, current, alpha = [], [], None
    while True:
        kind, value = tokens.peek()
        require(kind is not None, "Unclosed color function", "invalid_color")
        if value == ")":
            tokens.take()
            break
        if value == ",":
            tokens.take()
            groups.append(current)
            current = []
            continue
        if value == "/":
            tokens.take()
            alpha = _value(tokens, depth)
            continue
        current.append(_value(tokens, depth))
    if current or groups:
        groups.append(current)
    return groups, alpha


def _value(tokens, depth):
    kind, value = tokens.peek()
    if kind == "num":
        tokens.take()
        return ("num", value)
    if kind in ("hex", "ident"):
        return ("color", _expression(tokens, depth + 1)) if kind == "hex" or _is_color_start(tokens) else ("word", tokens.take()[1].lower())
    raise VixlError("invalid_color", f"Unexpected {value!r} in color")


def _is_color_start(tokens):
    kind, value = tokens.peek()
    following = tokens.items[tokens.index + 1] if tokens.index + 1 < len(tokens.items) else (None, None)
    if following[1] == "(":
        return True
    return value.lower() == "transparent" or lookup_name(value) is not None and value.lower() not in _KEYWORDS


_KEYWORDS = {"in", "srgb", "srgb-linear", "display-p3", "rec2020", "xyz", "xyz-d65", "xyz-d50", "lab", "lch", "oklab", "oklch", "hsl", "hwb", "shorter", "longer", "increasing", "decreasing", "hue"}


def _flat(groups):
    return [item for group in groups for item in group]


def _number(item, scale=1.0, percent_scale=None, name="value"):
    require(item and item[0] == "num", f"{name} must be a number", "invalid_color")
    number, unit = item[1]
    require(math.isfinite(number), f"{name} must be finite", "invalid_color")
    if unit == "%":
        return number / 100 * (percent_scale if percent_scale is not None else scale)
    require(unit == "", f"{name} does not accept {unit}", "invalid_color")
    return number


def _angle(item):
    require(item and item[0] == "num", "Hue must be a number or angle", "invalid_color")
    number, unit = item[1]
    return {"": 1, "deg": 1, "grad": 0.9, "rad": 180 / math.pi, "turn": 360}.get(unit, 1) * number % 360 if unit != "%" else number * 3.6 % 360


def _alpha(item, default=1.0):
    if item is None:
        return default
    if item[0] == "word" and item[1] == "none":
        return 0.0
    value = _number(item, 1, 1, "alpha")
    return min(max(value if value <= 1 or item[1][1] == "%" else value / 255, 0.0), 1.0)


def _channels(items, count, name):
    require(len(items) in (count, count + 1), f"{name}() takes {count} channels plus optional alpha", "invalid_color")
    return items[:count], items[count] if len(items) > count else None


def _expression(tokens, depth=0):
    require(depth <= MAX_DEPTH, "Color expression is nested too deeply", "invalid_color")
    kind, value = tokens.take()
    if kind == "hex":
        return _hex(value)
    require(kind == "ident", f"Expected a color, got {value!r}", "invalid_color")
    name = value.lower()
    if tokens.peek()[1] != "(":
        if name == "transparent":
            return (0.0, 0.0, 0.0, 0.0)
        found = lookup_name(value)
        if found is None:
            import difflib

            close = difflib.get_close_matches(_name_key(value), [n for n in named_colors() if not n.startswith("xkcd:")], 3, 0.75)
            raise VixlError(
                "invalid_color",
                f"Unknown color name {value!r}" + (f"; did you mean {', '.join(close)}?" if close else ""),
                requested=value,
                suggestions=close,
            )
        return _hex(found)
    return _function(name, tokens, depth)


def _function(name, tokens, depth):
    groups, slash_alpha = _argument_groups(tokens, depth)
    items = _flat(groups)
    if name in ("rgb", "rgba"):
        (r, g, b), alpha = _channels(items, 3, name)
        rgb = tuple(_number(v, 1, 255, name) / 255 for v in (r, g, b))
        if not in_gamut(rgb, 0.5 / 255):
            _gamut_event("clamp")
        return (*(min(max(c, 0.0), 1.0) for c in rgb), _alpha(slash_alpha or alpha))
    if name in ("hsl", "hsla", "hsv", "hsb", "hwb"):
        (h, s, x), alpha = _channels(items, 3, name)
        hue = _angle(h)
        s, x = (_number(v, 1, 1, name) / (100 if v[1][1] != "%" and _number(v, 1, 1, name) > 1 else 1) for v in (s, x))
        rgb = {"hsl": hsl_to_srgb, "hsla": hsl_to_srgb, "hwb": hwb_to_srgb}.get(name, hsv_to_srgb)(hue, s, x)
        return (*rgb, _alpha(slash_alpha or alpha))
    if name in ("lab", "lch", "oklab", "oklch"):
        (a, b, c), alpha = _channels(items, 3, name)
        ok = name.startswith("ok")
        L = _number(a, 1, 1 if ok else 100, "lightness")
        if ok and a[1][1] != "%" and L > 1:
            L /= 100
        if name.endswith("lab"):
            span = 0.4 if ok else 125
            second, third = _number(b, 1, span, name), _number(c, 1, span, name)
            lab = (L, second, third)
        else:
            chroma = _number(b, 1, 0.4 if ok else 150, "chroma")
            lab = from_polar((L, max(chroma, 0), _angle(c)))
        if ok:
            rgb = gamut_map(lab)
        else:
            rgb = gamut_map(linear_to_oklab(_mul(XYZ_TO_SRGB, _mul(D50_TO_D65, lab_to_xyz50(lab)))))
        return (*rgb, _alpha(slash_alpha or alpha))
    if name in ("cmyk", "device-cmyk"):
        (c, m, y, k), alpha = _channels(items, 4, name)
        values = [_number(v, 1, 1, name) for v in (c, m, y, k)]
        if any(v[1][1] != "%" for v in (c, m, y, k)) and max(values) > 1:
            values = [v / 100 for v in values]  # cmyk(0, 100, 100, 0) reads as percentages.
        values = [min(max(v, 0.0), 1.0) for v in values]
        return (*cmyk_to_srgb(*values), _alpha(slash_alpha or alpha))
    if name in ("gray", "grey"):
        require(len(items) in (1, 2), "gray() takes a lightness and optional alpha", "invalid_color")
        value = _number(items[0], 1, 1, "gray")
        value = value if items[0][1][1] == "%" else value / 255 if value > 1 else value
        return (value, value, value, _alpha(slash_alpha or (items[1] if len(items) > 1 else None)))
    if name in ("kelvin", "temperature"):
        require(len(items) == 1, "kelvin() takes one temperature", "invalid_color")
        kelvin = _number(items[0], name="temperature")
        require(1000 <= kelvin <= 40000, "Color temperature must be 1000–40000 K", "invalid_color")
        return (*kelvin_to_srgb(kelvin), 1.0)
    if name == "color":
        require(items and items[0][0] == "word", "color() needs a color space", "invalid_color")
        space = items[0][1]
        (r, g, b), alpha = _channels(items[1:], 3, "color")
        values = tuple(_number(v, 1, 1, "channel") for v in (r, g, b))
        if space == "srgb":
            rgb = values
            rgb = rgb if in_gamut(rgb) else gamut_map(srgb_to_oklab(rgb))
        elif space == "srgb-linear":
            rgb = gamut_map(linear_to_oklab(values))
        elif space == "display-p3":
            rgb = from_linear_space(srgb_to_linear(values), P3_TO_XYZ)
        elif space == "rec2020":
            rgb = from_linear_space(tuple(_rec2020_linear(v) for v in values), REC2020_TO_XYZ)
        elif space in ("xyz", "xyz-d65"):
            rgb = gamut_map(linear_to_oklab(_mul(XYZ_TO_SRGB, values)))
        elif space == "xyz-d50":
            rgb = gamut_map(linear_to_oklab(_mul(XYZ_TO_SRGB, _mul(D50_TO_D65, values))))
        else:
            raise VixlError("invalid_color", f"Unsupported color() space {space!r}; use srgb, srgb-linear, display-p3, rec2020, xyz-d65 or xyz-d50")
        return (*(min(max(c, 0.0), 1.0) for c in rgb), _alpha(slash_alpha or alpha))
    if name == "color-mix":
        return _color_mix(groups)
    return _modifier(name, items, slash_alpha)


def _color_mix(groups):
    require(len(groups) == 3, "Use color-mix(in SPACE, COLOR [P%], COLOR [P%])", "invalid_color")
    words = [item[1] for item in groups[0] if item[0] == "word"]
    require(words[:1] == ["in"] and len(words) >= 2, "color-mix() starts with 'in SPACE'", "invalid_color")
    space = words[1]
    parts = []
    for group in groups[1:]:
        colors = [item[1] for item in group if item[0] == "color"]
        numbers = [item for item in group if item[0] == "num"]
        require(len(colors) == 1 and len(numbers) <= 1, "Each color-mix() part is a color and optional percentage", "invalid_color")
        parts.append((colors[0], _number(numbers[0], 1, 1, "percentage") if numbers else None))
    (a, pa), (b, pb) = parts
    if pa is None and pb is None:
        pa = pb = 0.5
    elif pa is None:
        pa = 1 - pb
    elif pb is None:
        pb = 1 - pa
    total = pa + pb
    require(total > 0, "color-mix() percentages cannot both be zero", "invalid_color")
    result = mix(a, b, pb / total, space)
    if total < 1:
        result = (*result[:3], result[3] * total)
    return result


def mix(a, b, amount=0.5, space="oklab"):
    """Mix ``amount`` of ``b`` into ``a`` (premultiplied alpha), interpolating in ``space``."""
    require(space in ("srgb", "srgb-linear", "oklab", "oklch", "lab", "lch", "hsl", "hwb", "xyz", "xyz-d65", "xyz-d50"), f"Unsupported mix space {space!r}", "invalid_color")
    alpha = a[3] * (1 - amount) + b[3] * amount
    ca, cb = to_space(a[:3], space), to_space(b[:3], space)
    polar = space in ("oklch", "lch", "hsl", "hwb")
    hue_index = 2 if space in ("oklch", "lch") else 0
    mixed = []
    for i, (x, y) in enumerate(zip(ca, cb)):
        if polar and i == hue_index:
            # Shorter-arc hue interpolation; achromatic endpoints adopt the other hue.
            chroma_index = 1
            if ca[chroma_index] < 1e-6:
                x = y
            if cb[chroma_index] < 1e-6:
                y = x
            delta = (y - x + 180) % 360 - 180
            mixed.append((x + delta * amount) % 360)
            continue
        if alpha > 0 and not (polar and i == hue_index):
            mixed.append((x * a[3] * (1 - amount) + y * b[3] * amount) / alpha)
        else:
            mixed.append(x * (1 - amount) + y * amount)
    return (*from_space(mixed, space), alpha)


def to_space(rgb, space):
    if space == "srgb":
        return tuple(rgb)
    if space == "srgb-linear":
        return srgb_to_linear(rgb)
    if space == "oklab":
        return srgb_to_oklab(rgb)
    if space == "oklch":
        return to_polar(srgb_to_oklab(rgb))
    if space == "lab":
        return srgb_to_lab(rgb)
    if space == "lch":
        return to_polar(srgb_to_lab(rgb))
    if space == "hsl":
        return srgb_to_hsl(rgb)
    if space == "hsv":
        return srgb_to_hsv(rgb)
    if space == "hwb":
        return srgb_to_hwb(rgb)
    if space in ("xyz", "xyz-d65"):
        return _mul(SRGB_TO_XYZ, srgb_to_linear(rgb))
    if space == "xyz-d50":
        return _mul(D65_TO_D50, _mul(SRGB_TO_XYZ, srgb_to_linear(rgb)))
    if space == "cmyk":
        return srgb_to_cmyk(rgb)
    raise VixlError("invalid_color", f"Unknown color space {space!r}")


def from_space(values, space):
    if space == "srgb":
        return tuple(min(max(v, 0.0), 1.0) for v in values)
    if space == "srgb-linear":
        return gamut_map(linear_to_oklab(values))
    if space == "oklab":
        return gamut_map(tuple(values))
    if space == "oklch":
        return gamut_map(from_polar(values))
    if space == "lab":
        return gamut_map(srgb_to_oklab(lab_to_srgb(values)))
    if space == "lch":
        return gamut_map(srgb_to_oklab(lab_to_srgb(from_polar(values))))
    if space == "hsl":
        return hsl_to_srgb(*values)
    if space == "hsv":
        return hsv_to_srgb(*values)
    if space == "hwb":
        return hwb_to_srgb(*values)
    if space in ("xyz", "xyz-d65"):
        return gamut_map(linear_to_oklab(_mul(XYZ_TO_SRGB, values)))
    if space == "xyz-d50":
        return gamut_map(linear_to_oklab(_mul(XYZ_TO_SRGB, _mul(D50_TO_D65, values))))
    if space == "cmyk":
        return cmyk_to_srgb(*values)
    raise VixlError("invalid_color", f"Unknown color space {space!r}")


MODIFIERS = (
    "mix",
    "lighten",
    "darken",
    "saturate",
    "desaturate",
    "tint",
    "shade",
    "tone",
    "alpha",
    "fade",
    "opacity",
    "rotate",
    "spin",
    "hue-rotate",
    "complement",
    "invert",
    "grayscale",
    "greyscale",
    "readable",
    "contrast",
)


def _modifier(name, items, slash_alpha):
    require(name in MODIFIERS, f"Unknown color function {name}(); see vixl color --help", "invalid_color")
    colors = [item[1] for item in items if item[0] == "color"]
    numbers = [item for item in items if item[0] == "num"]
    require(colors, f"{name}() needs a color argument", "invalid_color")
    base = colors[0]
    if name in ("rotate", "spin", "hue-rotate"):
        require(numbers, f"{name}() needs an angle", "invalid_color")
        L, C, H = to_polar(srgb_to_oklab(base[:3]))
        return (*gamut_map(from_polar((L, C, (H + _angle(numbers[0])) % 360))), base[3])
    amount = _number(numbers[0], 1, 1, "amount") if numbers else None
    if name == "mix":
        require(len(colors) == 2, "mix() takes two colors and an optional weight of the second", "invalid_color")
        weight = 0.5 if amount is None else amount if numbers[0][1][1] == "%" or amount <= 1 else amount / 100
        words = [item[1] for item in items if item[0] == "word"]
        return mix(colors[0], colors[1], min(max(weight, 0.0), 1.0), words[0] if words else "oklab")
    if name in ("readable", "contrast"):
        candidates = colors[1:] or [(0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)]
        return max(candidates, key=lambda c: contrast_ratio(base, c))
    if name in ("complement", "invert", "grayscale", "greyscale"):
        if name == "invert":
            return (1 - base[0], 1 - base[1], 1 - base[2], base[3])
        L, C, H = to_polar(srgb_to_oklab(base[:3]))
        result = from_polar((L, C, (H + 180) % 360)) if name == "complement" else (L, 0.0, 0.0)
        return (*gamut_map(result), base[3])
    require(amount is not None, f"{name}() needs an amount", "invalid_color")
    fraction = amount if numbers[0][1][1] == "%" or abs(amount) <= 1 else amount / 100
    if name in ("alpha", "fade", "opacity"):
        return (*base[:3], min(max(fraction, 0.0), 1.0))
    if name in ("tint", "shade", "tone"):
        other = {"tint": (1.0, 1.0, 1.0, base[3]), "shade": (0.0, 0.0, 0.0, base[3]), "tone": (0.5, 0.5, 0.5, base[3])}[name]
        return mix(base, other, min(max(fraction, 0.0), 1.0), "oklab")
    L, C, H = to_polar(srgb_to_oklab(base[:3]))
    if name in ("lighten", "darken"):
        L = min(max(L + (fraction if name == "lighten" else -fraction), 0.0), 1.0)
    else:
        C = max(0.0, C * (1 + fraction) if name == "saturate" else C * (1 - min(fraction, 1)))
        if name == "saturate" and C < 1e-6:
            C = 0.0
    return (*gamut_map(from_polar((L, C, H))), base[3])


@lru_cache(maxsize=4096)
def parse(value):
    """Parse a color string into encoded sRGB floats ``(r, g, b, a)`` in 0–1."""
    require(isinstance(value, str), f"Invalid color {value!r}", "invalid_color")
    text = value.strip()
    require(0 < len(text) <= 2048, "Color text must be 1–2048 characters", "invalid_color")
    if "(" not in text and not text.startswith("#"):
        found = lookup_name(text)
        if text.lower() in ("transparent", "none"):
            return (0.0, 0.0, 0.0, 0.0)
        if found is not None:
            return _hex(found)
    tokens = _Tokens(text)
    result = _expression(tokens)
    require(tokens.peek()[0] is None, f"Unexpected trailing text in color {value!r}", "invalid_color")
    return tuple(float(min(max(c, 0.0), 1.0)) for c in result)


def clipped(value):
    """How ``value`` was brought into sRGB, or None when it was already inside: ``{"how", "to"}``, where ``how`` is
    ``chroma`` (an oklch/lab colour beyond the gamut, its chroma reduced at the same lightness and hue) or ``clamp``
    (``rgb(300 0 0)``: channels outside 0–255 clamped as CSS does)."""
    token = _GAMUT.set([])
    try:
        rgba = parse.__wrapped__(value)  # uncached, so the parse runs and records what it did
        events = _GAMUT.get()
    finally:
        _GAMUT.reset(token)
    if not events:
        return None
    return {"how": "clamp" if "clamp" in events else "chroma", "to": hex_of(rgba)}


def to_rgba8(value):
    r, g, b, a = parse(value)
    return tuple(int(round(c * 255)) for c in (r, g, b, a))


def hex_of(rgba):
    r, g, b, a = (int(round(min(max(c, 0.0), 1.0) * 255)) for c in rgba)
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")


def _round(values, digits=4):
    return [round(v, digits) for v in values]


def describe(value, *, ink_limit=None, black=1.0):
    """Every representation an agent might need, plus names and contrast."""
    rgba = parse(value)
    rgb = rgba[:3]
    h, s, light = srgb_to_hsl(rgb)
    hv, sv, v = srgb_to_hsv(rgb)
    lab = srgb_to_lab(rgb)
    oklab = srgb_to_oklab(rgb)
    c, m, y, k = srgb_to_cmyk(rgb, black, ink_limit)
    white, dark = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    clip = clipped(value)
    return {
        "input": value,
        **({"clipped": clip, "warnings": [gamut_warning(value, clip)]} if clip else {}),
        "hex": hex_of(rgba),
        "rgb": [round(x * 255) for x in rgb],
        "alpha": round(rgba[3], 4),
        "hsl": [round(h, 2), round(s * 100, 2), round(light * 100, 2)],
        "hsv": [round(hv, 2), round(sv * 100, 2), round(v * 100, 2)],
        "hwb": [round(srgb_to_hwb(rgb)[0], 2), round(min(rgb) * 100, 2), round((1 - max(rgb)) * 100, 2)],
        "cmyk": [round(x * 100, 2) for x in (c, m, y, k)],
        "cmyk_note": "Device-naive conversion with full gray-component replacement; export with an ICC profile for press accuracy.",
        "lab": _round(lab, 3),
        "lch": _round(to_polar(lab), 3),
        "oklab": _round(oklab),
        "oklch": _round(to_polar(oklab)),
        "css": {
            "rgb": "rgb({} {} {}{})".format(*(round(x * 255) for x in rgb), f" / {round(rgba[3], 3)}" if rgba[3] < 1 else ""),
            "hsl": f"hsl({h:.1f} {s * 100:.1f}% {light * 100:.1f}%)",
            "oklch": "oklch({:.3f} {:.3f} {:.1f})".format(*to_polar(oklab)),
            "cmyk": "cmyk({:.0f}% {:.0f}% {:.0f}% {:.0f}%)".format(*(x * 100 for x in (c, m, y, k))),
        },
        "luminance": round(relative_luminance(rgb), 5),
        "contrast": {"white": round(contrast_ratio(rgb, white), 2), "black": round(contrast_ratio(rgb, dark), 2)},
        "readable_text": "white" if contrast_ratio(rgb, white) >= contrast_ratio(rgb, dark) else "black",
        "temperature": "warm" if (oklab[2] > 0.02 and oklab[1] > -0.05) else "cool" if oklab[2] < -0.02 else "neutral",
        "names": nearest_names(rgb),
    }


def gamut_warning(value, clip):
    if clip["how"] == "clamp":
        return f"{value} has channels outside 0–255; clamped to {clip['to']}"
    return (f"{value} is outside the sRGB gamut; shown as {clip['to']}, its chroma reduced at the same lightness and hue "
            "(lower the chroma for a colour that displays as written)")


def harmony(value, scheme="complementary", count=None):
    """Return hex colors for a classic harmony, rotated in OKLCH so lightness stays even."""
    require(scheme in HARMONIES, f"Unknown harmony {scheme!r}; use {', '.join(HARMONIES)}", "invalid_color")
    base = parse(value)
    L, C, H = to_polar(srgb_to_oklab(base[:3]))
    offsets = {
        "complementary": (0, 180),
        "analogous": (-30, 0, 30),
        "triadic": (0, 120, 240),
        "split-complementary": (0, 150, 210),
        "tetradic": (0, 60, 180, 240),
        "square": (0, 90, 180, 270),
    }
    if scheme in offsets:
        colors = [(*gamut_map(from_polar((L, C, (H + o) % 360))), base[3]) for o in offsets[scheme]]
    else:
        count = count or 5
        require(isinstance(count, int) and 2 <= count <= 12, "Harmony count must be 2–12", "invalid_color")
        if scheme == "monochromatic":
            low, high = 0.25, 0.92
            colors = [
                (*gamut_map(from_polar((low + (high - low) * i / (count - 1), C * (1 - abs(i / (count - 1) - 0.5) * 0.6), H))), base[3])
                for i in range(count)
            ]
        else:
            target = {"tints": (1.0, 1.0, 1.0, base[3]), "shades": (0.0, 0.0, 0.0, base[3]), "tones": (0.5, 0.5, 0.5, base[3])}[scheme]
            colors = [mix(base, target, i / count * 0.9) for i in range(count)]
    return [hex_of(c) for c in colors]


def resolve_expression(value, swatches, depth=0):
    """Expand ``@swatch`` references anywhere inside a color expression."""
    if not isinstance(value, str) or "@" not in value:
        return value
    require(depth < MAX_DEPTH, "Swatch references are nested too deeply", "invalid_color")

    def replace(match):
        name = match[1]
        require(name in swatches, f"Unknown swatch: @{name}", "invalid_color")
        return resolve_expression(swatches[name], swatches, depth + 1)

    return re.sub(r"@([A-Za-z0-9_][\w-]*)", replace, value)


INTENTS = ("perceptual", "relative", "saturation", "absolute")


def load_profile(source):
    """Open an ICC profile from bytes, checking it describes a CMYK device."""
    from io import BytesIO
    from PIL import ImageCms

    try:
        profile = ImageCms.ImageCmsProfile(BytesIO(source))
    except (OSError, TypeError, ValueError) as exc:
        raise VixlError("invalid_profile", f"Not a readable ICC profile: {exc}") from exc
    space = (profile.profile.xcolor_space or "").strip().upper()
    require(space == "CMYK", f"ICC profile color space is {space or 'unknown'}, not CMYK", "invalid_profile")
    return profile


def _intent(name):
    from PIL import ImageCms

    require(name in INTENTS, f"Rendering intent must be one of {', '.join(INTENTS)}")
    return {
        "perceptual": ImageCms.Intent.PERCEPTUAL,
        "relative": ImageCms.Intent.RELATIVE_COLORIMETRIC,
        "saturation": ImageCms.Intent.SATURATION,
        "absolute": ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
    }[name]


def flatten(image, background="white"):
    from PIL import Image

    base = Image.new("RGBA", image.size, to_rgba8(background))
    base.alpha_composite(image.convert("RGBA"))
    return base.convert("RGB")


def separation_transform(profile, intent="relative"):
    """The sRGB → CMYK colour transform of an ICC profile, to reuse across many ``cmyk_image`` calls."""
    from PIL import ImageCms

    return ImageCms.buildTransform(ImageCms.createProfile("sRGB"), profile, "RGB", "CMYK", _intent(intent))


def cmyk_image(image, *, profile=None, intent="relative", black=1.0, ink_limit=None, background="white",
               transform=None):
    """Separate an RGBA render into a CMYK image (alpha is flattened onto ``background``).
    ``transform`` is a prebuilt ``separation_transform`` of ``profile``."""
    import numpy as np
    from PIL import Image, ImageCms

    rgb = flatten(image, background)
    require(ink_limit is None or 1 <= ink_limit <= 4, "Ink limit must be 100–400%")
    if profile is not None:
        transform = transform or separation_transform(profile, intent)
        separated = ImageCms.applyTransform(rgb, transform)
        if ink_limit is None:
            return separated
        # The profile decides black generation; the requested ink limit still caps the total.
        a = np.asarray(separated, dtype=np.float32) / 255
        cmy, k = limit_ink(a[:, :, :3], a[:, :, 3:], ink_limit), a[:, :, 3:]
        return Image.fromarray(np.uint8(np.clip(np.concatenate((cmy, k), axis=2), 0, 1) * 255 + 0.5), "CMYK")
    require(0 <= black <= 1, "Black generation must be 0–1")
    a = np.asarray(rgb, dtype=np.float32) / 255
    cmy = 1 - a
    k = cmy.min(axis=2, keepdims=True) * black
    cmy = np.where(k < 1 - 1e-6, (cmy - k) / np.maximum(1 - k, 1e-6), 0)
    if ink_limit is not None:
        cmy = limit_ink(cmy, k, ink_limit)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((cmy, k), axis=2), 0, 1) * 255 + 0.5), "CMYK")


def limit_ink(cmy, k, ink_limit):
    """Scale C, M and Y down where C + M + Y + K exceeds ``ink_limit`` (3.0 for 300%), keeping K."""
    import numpy as np

    total = cmy.sum(axis=2, keepdims=True)
    room = np.maximum(ink_limit - k, 0)
    return np.where(total + k > ink_limit, cmy * room / np.maximum(total, 1e-6), cmy)


def cmyk_to_rgb_image(cmyk, profile=None, intent="relative"):
    import numpy as np
    from PIL import Image, ImageCms

    if profile is not None:
        transform = ImageCms.buildTransform(profile, ImageCms.createProfile("sRGB"), "CMYK", "RGB", _intent(intent))
        return ImageCms.applyTransform(cmyk, transform)
    a = np.asarray(cmyk, dtype=np.float32) / 255
    rgb = (1 - a[:, :, :3]) * (1 - a[:, :, 3:])
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 1) * 255 + 0.5), "RGB")


def proof_image(image, *, profile=None, intent="relative", black=1.0, ink_limit=None, background="white"):
    """Soft proof: how the RGBA render looks after CMYK separation, returned as RGBA."""
    rgb = cmyk_to_rgb_image(
        cmyk_image(image, profile=profile, intent=intent, black=black, ink_limit=ink_limit, background=background),
        profile,
        intent,
    )
    result = rgb.convert("RGBA")
    return result


def simulate_vision(image, kind):
    """Approximate color-vision deficiency (Machado 2009) so designs don't rely on hue alone."""
    import numpy as np
    from PIL import Image

    require(kind in VISION, f"Vision simulation must be one of {', '.join(VISION)}")
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255
    rgb = rgba[:, :, :3]
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    if kind == "achromatopsia":
        y = linear @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        linear = np.repeat(y[:, :, None], 3, axis=2)
    else:
        linear = linear @ np.array(CVD[kind], dtype=np.float32).T
    linear = np.clip(linear, 0, 1)
    encoded = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055)
    out = np.concatenate((encoded, rgba[:, :, 3:]), axis=2)
    return Image.fromarray(np.uint8(np.clip(out, 0, 1) * 255 + 0.5), "RGBA")


def ink_coverage(cmyk):
    """Total area coverage statistics (percent) of a CMYK image."""
    import numpy as np

    total = np.asarray(cmyk, dtype=np.float32).sum(axis=2) / 255 * 100
    return {"max": round(float(total.max()), 1), "mean": round(float(total.mean()), 1), "values": total}


SCALE_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)


def scale(value, steps=SCALE_STEPS):
    """A lightness ramp (50 = lightest … 950 = darkest) that keeps the base hue.

    The base color keeps its own lightness at the step nearest to it, so ``brand-500``-style
    names stay predictable for UI and design-system palettes.
    """
    base = parse(value)
    L, C, H = to_polar(srgb_to_oklab(base[:3]))
    count = len(steps)
    targets = [0.975 - (0.975 - 0.22) * i / (count - 1) for i in range(count)]
    nearest = min(range(count), key=lambda i: abs(targets[i] - L))
    targets[nearest] = L
    result = {}
    for step, lightness in zip(steps, targets):
        # Chroma tapers toward white and black, as real tints and shades do.
        taper = 1 - abs(lightness - L) / max(L if lightness < L else 1 - L, 1e-6) * 0.65
        result[str(step)] = hex_of((*gamut_map(from_polar((lightness, C * max(taper, 0.15), H))), 1.0))
    return result


def interpolate_scale(values, count, space="oklab"):
    """``count`` colours from the first value to the last through the ones between, mixed in ``space``."""
    require(isinstance(count, int) and 2 <= count <= 64, "A scale between colours has 2–64 steps (--count)",
            "invalid_color", field="count")
    stops = [parse(v) for v in values]
    result = []
    for i in range(count):
        position = i / (count - 1) * (len(stops) - 1)
        index = min(int(position), len(stops) - 2)
        result.append(hex_of(mix(stops[index], stops[index + 1], position - index, space)))
    return result


def generate_swatches(op):
    """Swatches for the ``palette-generate`` operation."""
    from .design import named

    prefix = named(op["name"])
    scheme = op.get("scheme", "scale")
    if scheme == "scale":
        colors = scale(op["color"])
        return {f"{prefix}-{step}": value for step, value in colors.items()}
    values = harmony(op["color"], scheme, op.get("count"))
    return {f"{prefix}-{i + 1}": value for i, value in enumerate(values)}


def search_names(query, limit=50):
    key = _name_key(query)
    found = [{"name": name, "hex": value} for name, value in _canonical_names().items() if key in name]
    found.sort(key=lambda item: (len(item["name"]), item["name"]))
    return found[:limit]
