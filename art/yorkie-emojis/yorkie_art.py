"""Yorkie emoji artwork: 72x72 SVG masters in the VIXL Line style (navy 1.7 px outlines)."""

NAVY = "#23364D"
TAN = "#D49A5C"      # head fur
TAN_LT = "#EDC48A"   # top tuft / muzzle
TAN_DK = "#A86A3C"   # inner ear
STEEL = "#6E7787"    # steel-grey body coat
PINK = "#E8899E"
BLUE = "#2F86B8"     # sweater
RED = "#E2525C"
GREEN = "#86C45A"
YELLOW = "#F2C14E"
WHITE = "#FFFCF5"

def p(d, fill="none", **kw):
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<path d="{d}" fill="{fill}"{extra}/>'

def c(cx, cy, r, fill=NAVY, stroke="none"):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}"/>'

def g(parts, transform=None):
    t = f' transform="{transform}"' if transform else ""
    return f"<g{t}>" + "".join(parts) + "</g>"

# --- head pieces ---------------------------------------------------------
def ears(fold_left=False):
    out = []
    if fold_left:  # floppy left ear, like the car-ride photo
        out.append(p("M18 27L10 17Q9 15 11 15L28 19Z", TAN))
        out.append(p("M17 23L13 18L23 19.5Z", TAN_DK, stroke="none"))
    else:
        out.append(p("M17 30L14 10Q14 7 16.5 8.5L31 19Z", TAN))
        out.append(p("M18.5 24L17 13.5L26 19.5Z", TAN_DK, stroke="none"))
    out.append(p("M55 30L58 10Q58 7 55.5 8.5L41 19Z", TAN))
    out.append(p("M53.5 24L55 13.5L46 19.5Z", TAN_DK, stroke="none"))
    return out

HEAD = "M24 18H48Q50 18 51 19.5L57 27.5Q58 29 58 31V41L61.5 45L57.5 46.5L59.5 50.5L54 51.5L50 57Q48.5 59 46.5 59H25.5Q23.5 59 22 57L18 51.5L12.5 50.5L14.5 46.5L10.5 45L14 41V31Q14 29 15 27.5L21 19.5Q22 18 24 18Z"

def head():
    return [
        p(HEAD, TAN),
        # muzzle: lighter fur, no outline
        p("M27 39Q36 35 45 39L50 48Q51 53 47 56H25Q21 53 22 48Z", TAN_LT, stroke="none"),
        # spiky top-knot (open path: outline only on the spikes)
        p("M23 24L24.5 13L29.5 18.5L33.5 9L38.5 17L45 11.5L48.5 24", TAN_LT),
    ]

def eyes_dot(dx=0, r=3.2):
    return [c(27 + dx, 34, r), c(45 + dx, 34, r), c(28 + dx, 32.8, 1.1, WHITE), c(46 + dx, 32.8, 1.1, WHITE)]

def eyes_big():
    return [c(27, 34, 4.6), c(45, 34, 4.6), c(28.6, 32.2, 1.8, WHITE), c(46.6, 32.2, 1.8, WHITE),
            c(25.6, 36.2, 0.8, WHITE), c(43.6, 36.2, 0.8, WHITE),
            p("M21 26.5L29 24.5"), p("M51 26.5L43 24.5")]

def eyes_closed_happy():
    return [p("M23 35Q27 30 31 35"), p("M41 35Q45 30 49 35")]

def eyes_sleep():
    return [p("M23 34Q27 38 31 34"), p("M41 34Q45 38 49 34")]

def eyes_hearts():
    def heart(x, y):
        return p(f"M{x} {y+4}L{x-4.6} {y-0.4}Q{x-6} {y-2.2} {x-4.4} {y-3.8}Q{x-2.2} {y-5.4} {x} {y-2.6}Q{x+2.2} {y-5.4} {x+4.4} {y-3.8}Q{x+6} {y-2.2} {x+4.6} {y-0.4}Z", RED)
    return [heart(27, 34.5), heart(45, 34.5)]

def eyes_wink():
    return [c(27, 34, 3.2), c(28, 32.8, 1.1, WHITE), p("M41 34Q45 30 49 34")]

def eyes_grumpy():
    return [c(27, 35, 2.8), c(45, 35, 2.8), p("M22 28.5L31 31"), p("M50 28.5L41 31")]

def eyes_wow():
    return [c(27, 34, 3.8, WHITE, NAVY), c(45, 34, 3.8, WHITE, NAVY), c(27, 34, 1.8), c(45, 34, 1.8),
            p("M22 26L30 25"), p("M50 26L42 25")]

def sunglasses():
    def lens(x):
        return p(f"M{x-8} 30H{x+8}L{x+6.5} 37Q{x+5.5} 40 {x+2.5} 40H{x-2.5}Q{x-5.5} 40 {x-6.5} 37Z", NAVY)
    return [lens(27), lens(45), p("M35 31.5H37"), p("M19 31L15 29.5"), p("M53 31L57 29.5"),
            p("M22 32.2L25 32.2", stroke=WHITE, stroke_width="1.2"), p("M40 32.2L43 32.2", stroke=WHITE, stroke_width="1.2")]

NOSE = "M32 41.5H40Q41.5 41.5 40.6 43L37.2 46.6Q36 47.7 34.8 46.6L31.4 43Q30.5 41.5 32 41.5Z"
def nose():
    return [p(NOSE, NAVY), c(34.3, 42.7, 0.8, "#5C6E86")]

def mouth_smile():
    return [p("M36 47V49"), p("M30.5 48.5Q33 52.5 36 49Q39 52.5 41.5 48.5")]

def mouth_blep():
    return [p("M33.5 49.5H38.5V53.5Q36 57.5 33.5 53.5Z", PINK), p("M36 51V53.5", stroke="#B8566E", stroke_width="1.2"),
            p("M36 47V49.5"), p("M30.5 48.5Q33 52 36 49.5Q39 52 41.5 48.5")]

def mouth_lick():  # tongue curling up over the nose, as in the sofa photo
    return [p("M36 47V48.5"), p("M31 48Q33.5 51 36 48.5Q38.5 51 41 48"),
            p("M36 49.5Q42.5 50 43 44Q43 41 40.5 40", stroke=NAVY, stroke_width="6.6"),
            p("M36 49.5Q42.5 50 43 44Q43 41 40.5 40", stroke=PINK, stroke_width="3.4"),
            p("M38.5 48Q41 47 41.4 44.5", stroke="#B8566E", stroke_width="1")]

def mouth_open():
    return [p("M36 47V48"), p("M30 48.5Q36 49 42 48.5Q41 56 36 56Q31 56 30 48.5Z", "#7A3346"),
            p("M32.5 53Q36 51 39.5 53Q38.5 55.8 36 55.8Q33.5 55.8 32.5 53Z", PINK, stroke="none")]

def mouth_o():
    return [p("M36 47V48.5"), '<ellipse cx="36" cy="52" rx="3" ry="3.4" fill="#7A3346"/>']

def mouth_flat():
    return [p("M36 47V49"), p("M31.5 50.5Q36 49 40.5 50.5")]

def mouth_frown():
    return [p("M36 47V49"), p("M31.5 51.5Q36 48 40.5 51.5")]

def collar():  # knit sweater neckline peeking under the chin
    return [p("M17 53H55L59 63Q59 64 58 64H14Q13 64 13 63Z", BLUE),
            p("M15.5 58.5H56.5", stroke=RED, stroke_width="2.4"),
            p("M17 53H55L59 63Q59 64 58 64H14Q13 64 13 63Z")]

def face(eyes, mouth, fold_left=False, with_collar=True):
    return (collar() if with_collar else []) + ears(fold_left) + head() + eyes + nose() + mouth

def zzz():
    return [p("M53 7H59L53 14H59", stroke_width="1.6"), p("M61 15H64.5L61 19.5H64.5", stroke_width="1.4")]

def tear():
    return [p("M22 39Q20 43 22 44.5Q24 43 22 39Z", "#8FC8EA", stroke_width="1.2")]

def party_hat():
    return [p("M46 4L55 25Q48 27 39.5 20Z", "#8E6BD8"),
            p("M43.6 9.6Q47.5 12 50.6 15M41.2 15.2Q46 19 53 20.5", stroke=YELLOW, stroke_width="1.8"),
            p("M46 4L55 25Q48 27 39.5 20Z"), c(46, 4, 2.6, RED, NAVY)]

def confetti():
    return [p("M9 12L12 10", stroke=RED), p("M62 33L65 35", stroke=GREEN), p("M8 33l3 1", stroke=YELLOW), c(63, 12, 1.2, BLUE)]

def heart(x, y, s=1.0, fill=RED):
    return g([p("M0 5L-5.5 -0.5Q-7 -2.6 -5.2 -4.6Q-2.6 -6.6 0 -3.2Q2.6 -6.6 5.2 -4.6Q7 -2.6 5.5 -0.5Z", fill)],
             f"translate({x} {y}) scale({s})")

# Sweater body: steel-grey coat in the blue harlequin knit with red/green ribbing.
def sweater_body():
    body = "M14 64V50Q14 40 23 40H49Q58 40 58 50V64Z"
    tri = [("M20 52L25 46L30 52Z", GREEN), ("M30 52L35 46L40 52Z", "#F09AC0"), ("M40 52L45 46L50 52Z", YELLOW),
           ("M25 58L30 52L35 58Z", "#9CD3E6"), ("M35 58L40 52L45 58Z", RED), ("M45 58L50 52L55 58Z", GREEN),
           ("M15 58L20 52L25 58Z", "#F09AC0")]
    return ([p(body, BLUE)] + [p(d, f, stroke="none") for d, f in tri] +
            [p("M14 60H58", stroke=RED, stroke_width="3"), p("M14 63H58", stroke=GREEN, stroke_width="2.2"),
             p(body)])

def mini(parts, s=0.74, ty=-1):
    # scale the head around its centre-top so it sits above a body
    return g(parts, f"translate({36 - 36 * s} {ty}) scale({s})")

def carrier():
    return [p("M8 64V52Q8 48 12 48H60Q64 48 64 52V64Z", "#2B3140"),
            p("M8 46Q8 41 13 41H59Q64 41 64 46V49Q64 51 62 51H10Q8 51 8 49Z", "#E9E1D3"),
            p("M27 51V64", stroke="#11151D", stroke_width="2.2"), p("M45 51V64", stroke="#11151D", stroke_width="2.2"),
            p("M4 44Q9 38 15 43L13 64H6Z", "#B9A5D8"), p("M7 47L12 46M6.5 52L12.5 51M6 57L12.5 56", stroke="#7DB7D9", stroke_width="1.4")]

def stripes_sweater_collar():
    return [p("M18 44H54L56 52H16Z", "#2B2E3A"), p("M17 48H55", stroke=RED, stroke_width="2"),
            p("M17 50.5H55", stroke=WHITE, stroke_width="1.6")]

def paw():
    return [p("M50 64L52 46H61L62 64Z", TAN),
            p("M49.5 40Q49.5 31 56.5 31Q63.5 31 63.5 40Q63.5 47 56.5 47Q49.5 47 49.5 40Z", TAN_LT),
            c(53, 36.5, 1.6, "#4A3A3A"), c(56.5, 35, 1.6, "#4A3A3A"), c(60, 36.5, 1.6, "#4A3A3A"),
            p("M53.5 42Q56.5 39 59.5 42Q59.5 44.5 56.5 44.5Q53.5 44.5 53.5 42Z", "#4A3A3A", stroke="none"),
            p("M64 24Q67 27 66.5 31", stroke_width="1.4"), p("M60 21.5Q63 22 65 24", stroke_width="1.4")]

def bone():
    return [p("M20 50H52Q55 46.5 57.5 48Q60 49.5 57.5 52Q60 54.5 57.5 56Q55 57.5 52 54H20Q17 57.5 14.5 56Q12 54.5 14.5 52Q12 49.5 14.5 48Q17 46.5 20 50Z", WHITE)]

EMOJIS = {
    "yorkie": ("Happy Yorkie", face(eyes_dot(), mouth_smile())),
    "yorkie_blep": ("Tongue-out blep", face(eyes_dot(), mouth_blep(), fold_left=True)),
    "yorkie_lick": ("Nose lick", face(eyes_dot(dx=1), mouth_lick())),
    "yorkie_love": ("Heart eyes", face(eyes_hearts(), mouth_blep()) + [heart(61, 13, 0.8, "#F07C93")]),
    "yorkie_puppy_eyes": ("Pleading puppy eyes", face(eyes_big(), mouth_blep())),
    "yorkie_sad": ("Teary", face(eyes_big(), mouth_frown()) + tear()),
    "yorkie_sleepy": ("Sleepy", face(eyes_sleep(), mouth_flat(), fold_left=True) + zzz()),
    "yorkie_wink": ("Wink", face(eyes_wink(), mouth_blep())),
    "yorkie_laugh": ("Laughing", face(eyes_closed_happy(), mouth_open())),
    "yorkie_wow": ("Surprised", face(eyes_wow(), mouth_o())),
    "yorkie_grumpy": ("Grumpy", face(eyes_grumpy(), mouth_flat())),
    "yorkie_cool": ("Sunglasses", face(sunglasses(), mouth_smile())),
    "yorkie_party": ("Party", face(eyes_closed_happy(), mouth_open()) + party_hat() + confetti()),
    "yorkie_sweater": ("Cozy in the harlequin sweater", sweater_body() + [mini(face(eyes_dot(), mouth_lick(), with_collar=False), 0.74, -2)]),
    "yorkie_car_ride": ("Car-ride carrier", [mini(stripes_sweater_collar() + face(eyes_dot(dx=-1), mouth_blep(), fold_left=True, with_collar=False), 0.74, 1)] + carrier()),
    "yorkie_wave": ("Paw wave", [g(face(eyes_closed_happy(), mouth_open()), "translate(-5 0)")] + paw()),
    "yorkie_treat": ("Bone treat", face(eyes_closed_happy(), mouth_flat()) + bone()),
}

def svg(parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72" '
            f'stroke="{NAVY}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            + "".join(parts) + "</svg>\n")

