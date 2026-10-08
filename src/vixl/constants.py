"""Lightweight command names, shared without importing the image renderer."""

ARTISTIC_DEFAULTS = {
    "sepia": 100,
    "duotone": 100,
    "solarize": 128,
    "pixelate": 8,
    "halftone": 8,
    "crosshatch": 8,
    "ink-blot": 128,
    "stamp": 128,
    "photocopy": 160,
    "pencil-sketch": 100,
    "charcoal": 100,
    "find-edges": 100,
    "emboss": 100,
    "oil-paint": 3,
    "watercolor": 100,
    "swirl": 90,
    "ripple": 8,
    "wave": 8,
    "glass": 6,
}

EFFECTS = (
    "brightness",
    "contrast",
    "saturation",
    "hue",
    "exposure",
    "gamma",
    "temperature",
    "tint",
    "white-balance",
    "shadows",
    "highlights",
    "levels",
    "curves",
    "blur",
    "gaussian-blur",
    "sharpen",
    "denoise",
    "grayscale",
    "invert",
    "posterize",
    "threshold",
    "noise",
    "grain",
    "vignette",
    "auto-tone",
    "auto-color",
    "auto-contrast",
) + tuple(ARTISTIC_DEFAULTS)

# Effect names a layer's stack can hold: the effect operations plus ``lookup`` (a LUT added by the
# lookup operation, whose ``name`` field names the table rather than the effect).
STACK_EFFECTS = EFFECTS + ("lookup",)
# Amount used when an effect is added without one.
EFFECT_DEFAULTS = {**ARTISTIC_DEFAULTS, "white-balance": 100, "lookup": 1}
