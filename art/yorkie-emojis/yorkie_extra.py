"""83 more Yorkie emojis built from the parts in yorkie_art.py: expressions, hats, props, paw reactions and scenes."""

import math

from yorkie_art import (
    EMOJIS, GREEN, NAVY, PINK, RED, TAN, TAN_LT, WHITE, YELLOW,
    c, collar, ears, eyes_big, eyes_closed_happy, eyes_dot, eyes_grumpy, eyes_hearts,
    eyes_sleep, eyes_wink, eyes_wow, g, head, heart, mouth_blep, mouth_flat, mouth_frown, mouth_lick,
    mouth_o, mouth_open, mouth_smile, nose, p, party_hat, sunglasses, zzz,
)

PURPLE = "#8E6BD8"
SKY = "#8FC8EA"
BROWN = "#8A5A3A"
GREY = "#C9CED6"
DARK = "#2B3140"
MOUTH = "#7A3346"
BEAN = "#4A3A3A"
ORANGE = "#F08A3C"


def face(eyes, mouth, fold_left=False, neck="collar", over=(), under=()):
    """A Yorkie head; `under` draws behind the ears, `over` on top of the face."""
    necks = {"collar": collar(), "none": [], "bandana": bandana(), "stripes": stripes_neck(), "scarf": scarf()}
    return list(under) + necks[neck] + ears(fold_left) + head() + list(eyes) + nose() + list(mouth) + list(over)


def fit(parts, s=0.8, dx=0, dy=0):
    """Scale a drawing about the canvas centre, then shift it."""
    return g(parts, f"translate({36 - 36 * s + dx} {36 - 36 * s + dy}) scale({s})")


def star_path(cx, cy, r, inner=0.45, points=5, rot=-90):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + i * 180 / points)
        pts.append(f"{cx + rr * math.cos(a):.2f} {cy + rr * math.sin(a):.2f}")
    return "M" + "L".join(pts) + "Z"


def sparkle(x, y, r, fill=YELLOW):
    return p(f"M{x} {y - r}Q{x + r * .18} {y - r * .18} {x + r} {y}Q{x + r * .18} {y + r * .18} {x} {y + r}"
             f"Q{x - r * .18} {y + r * .18} {x - r} {y}Q{x - r * .18} {y - r * .18} {x} {y - r}Z", fill, stroke_width="1.2")


# --- necks ---------------------------------------------------------------
def bandana():  # the blue star bandana from the sofa photo
    return [p("M16 52H56L40 66Q36 69 32 66Z", "#3F5FBF"), sparkle(29, 57, 2.4), sparkle(43, 57, 2.4), sparkle(36, 62, 2)]


def stripes_neck():
    return [p("M17 53H55L59 63Q59 64 58 64H14Q13 64 13 63Z", DARK),
            p("M15.5 57.5H56.5", stroke=RED, stroke_width="2.4"), p("M14.5 61H57.5", stroke=WHITE, stroke_width="2"),
            p("M17 53H55L59 63Q59 64 58 64H14Q13 64 13 63Z")]


def scarf():
    return [p("M15 51H57Q59 55 57 58H15Q13 55 15 51Z", RED), p("M44 56L48 66H54L50 56Z", RED),
            p("M47 60H51.5M48.5 63.5H53", stroke=WHITE, stroke_width="1.4")]


# --- eyes ----------------------------------------------------------------
def eyes_stars():
    return [p(star_path(27, 34, 5.2), YELLOW, stroke_width="1.4"), p(star_path(45, 34, 5.2), YELLOW, stroke_width="1.4")]


def eyes_spiral():
    def spiral(cx, cy):
        pts = [f"{cx + 0.55 * t * math.cos(t):.2f} {cy + 0.55 * t * math.sin(t):.2f}" for t in [i * 0.35 for i in range(0, 28)]]
        return p("M" + "L".join(pts), stroke_width="1.4")
    return [spiral(27, 34), spiral(45, 34)]


def eyes_side():  # pupils to the right, heavy lids
    return [c(29, 35, 2.8), c(47, 35, 2.8), p("M22.5 32.5H31.5"), p("M40.5 32.5H49.5")]


def eyes_unamused():
    return [p("M22.5 33H31.5"), p("M40.5 33H49.5"), c(27, 35.3, 2.2), c(45, 35.3, 2.2)]


def eyes_squeeze():
    return [p("M23 31L29.5 34.5L23 38"), p("M49 31L42.5 34.5L49 38")]


def eyes_zany():
    return [c(26, 34, 5.2, WHITE, NAVY), c(27.2, 34.6, 2.4), c(45, 34, 2.4), p("M41 29L49 30.5")]


def eyes_worried():
    return [c(27, 35, 3), c(45, 35, 3), c(28, 34, 1, WHITE), c(46, 34, 1, WHITE), p("M22 29L30 27"), p("M50 29L42 27")]


def eyes_angry():
    return [c(27.5, 35.5, 2.8), c(44.5, 35.5, 2.8), p("M21 28L31.5 32.5", stroke_width="2.2"), p("M51 28L40.5 32.5", stroke_width="2.2")]


def eyes_calm():
    return [p("M23 34.5Q27 37 31 34.5"), p("M41 34.5Q45 37 49 34.5")]


def eyes_up():  # rolling up / thinking
    return [c(27, 34, 3.6, WHITE, NAVY), c(45, 34, 3.6, WHITE, NAVY), c(28, 32, 1.7), c(46, 32, 1.7)]


def blush():
    return ['<ellipse cx="22" cy="41" rx="3.6" ry="2.2" fill="#F0A0B4" stroke="none"/>',
            '<ellipse cx="50" cy="41" rx="3.6" ry="2.2" fill="#F0A0B4" stroke="none"/>']


# --- mouths --------------------------------------------------------------
def mouth_smirk():
    return [p("M36 47V48.5"), p("M33 49.5Q37 51 41.5 47")]


def mouth_kiss():
    return [p("M36 47V48"), p("M35 48.5Q38 49.5 36 51Q38 52.5 35 53.5")]


def mouth_teeth():
    return [p("M36 47V48"), p("M29.5 49H42.5V53.5H29.5Z", WHITE), p("M33.8 49V53.5M38.2 49V53.5M29.5 51.2H42.5", stroke_width="1.1")]


def mouth_wail():
    return [p("M36 47V48"), p("M29 54Q29 48 36 48Q43 48 43 54Q43 56.5 41 56.5H31Q29 56.5 29 54Z", MOUTH),
            p("M31.5 56.5Q36 52.5 40.5 56.5", PINK, stroke="none")]


def mouth_yawn():
    return [p("M36 47V47.5"), '<ellipse cx="36" cy="53" rx="4.4" ry="5.2" fill="#7A3346"/>',
            p("M32.5 55.5Q36 53 39.5 55.5Q38.5 58 36 58Q33.5 58 32.5 55.5Z", PINK, stroke="none")]


def mouth_drool():
    return mouth_blep() + [p("M40.5 50Q42 54 40.5 56Q39 54 40.5 50Z", SKY, stroke_width="1.1")]




def mouth_wavy():
    return [p("M36 47V48.5"), p("M30 51Q32 49 34 51Q36 53 38 51Q40 49 42 51")]


def mouth_tongue_side():
    return [p("M36 47V48.5"), p("M30.5 48.5Q33 51.5 36 49Q39 51.5 41.5 48.5"),
            p("M38.5 50.5H44V55Q41.5 59 38.5 55Z", PINK), p("M41.2 52V55", stroke="#B8566E", stroke_width="1.1")]


def mouth_holding(width=26):  # flat mouth, for things carried in it
    return [p("M36 47V49"), p(f"M{36 - width / 2} 51Q36 49.5 {36 + width / 2} 51")]


# --- hats (head space; the head is fitted smaller to make room) ----------
def crown():
    return [p("M22 18L20 4L28.5 11L36 1L43.5 11L52 4L50 18Z", YELLOW), c(36, 12, 2, RED, NAVY), c(26, 14, 1.4, SKY, NAVY), c(46, 14, 1.4, SKY, NAVY)]


def topknot_bow():
    return [p("M36 13L25 6Q23 5.5 23 8V18Q23 20.5 25 19.5Z", "#F07C93"), p("M36 13L47 6Q49 5.5 49 8V18Q49 20.5 47 19.5Z", "#F07C93"),
            c(36, 13, 3.4, "#D85C7A", NAVY), c(27, 9.5, 0.9, WHITE), c(45, 9.5, 0.9, WHITE)]


def chef_hat():
    return [p("M24 22V13Q16 11 18 4Q21 -2 28 1Q31 -5 38 -3Q44 -6 47 0Q55 -1 55 6Q55 12 48 13V22Z", WHITE),
            p("M24 18H48", stroke_width="1.4")]


def grad_cap():
    return [p("M25 15V21Q36 25 47 21V15Z", DARK), p("M36 4L60 12L36 20L12 12Z", DARK),
            p("M54 14V24", stroke=YELLOW, stroke_width="1.6"), c(54, 25, 1.8, YELLOW, NAVY)]


def santa_hat():
    return [p("M19 19Q20 4 36 1Q50 -1 59 13L54 15Q48 8 44 9L51 19Z", RED), c(59, 15, 3.6, WHITE, NAVY),
            p("M16 18Q36 13 56 18Q57 23 55 24Q36 19 17 24Q15 22 16 18Z", WHITE)]


def witch_hat():
    return [p("M24 18L42 -6Q44 -8 44 -5L48 18Z", PURPLE), p("M8 20Q36 12 64 20Q36 26 8 20Z", PURPLE),
            p("M25 16Q36 13.5 47 16", stroke=GREEN, stroke_width="2.6")]


def bunny_ears():
    return [p("M24 20Q16 -2 22 -6Q28 -4 31 18Z", WHITE), p("M24 14Q21 2 23 -2Q26 1 27.5 14Z", "#F5B2C2", stroke="none"),
            p("M48 20Q56 -2 50 -6Q44 -4 41 18Z", WHITE), p("M48 14Q51 2 49 -2Q46 1 44.5 14Z", "#F5B2C2", stroke="none")]


def pirate():
    return [p("M16 22Q20 8 36 8Q52 8 56 22Q36 16 16 22Z", RED), c(24, 15, 1.2, WHITE), c(36, 12, 1.2, WHITE), c(47, 15, 1.2, WHITE),
            p("M56 20L63 17L62 26Z", RED)]


def eyepatch():
    return [p("M16 25L56 39", stroke_width="1.6"), '<ellipse cx="45" cy="34.5" rx="5.6" ry="5" fill="#23364D"/>']


def beanie():
    return [p("M17 22Q17 4 36 4Q55 4 55 22Z", "#3E8E7E"), p("M15 18H57Q58 24 56 25H16Q14 24 15 18Z", "#2E6F62"),
            c(36, 3, 3.6, WHITE, NAVY), p("M24 11V18M30 8V18M36 7V18M42 8V18M48 11V18", stroke="#2E6F62", stroke_width="1.4")]


def headphones():
    return [p("M12 36Q12 6 36 6Q60 6 60 36", stroke_width="4.6"), p("M12 36Q12 6 36 6Q60 6 60 36", stroke="#E2525C", stroke_width="2.4"),
            p("M7 31Q7 28 10 28H15V44H10Q7 44 7 41Z", DARK), p("M65 31Q65 28 62 28H57V44H62Q65 44 65 41Z", DARK)]


def flower_crown():
    out = [p("M16 21Q36 12 56 21", stroke=GREEN, stroke_width="2")]
    for x, y, col in [(18, 20, "#F07C93"), (27, 16, YELLOW), (36, 14.5, "#F09AC0"), (45, 16, SKY), (54, 20, YELLOW)]:
        out += [c(x, y, 3.8, col, NAVY), c(x, y, 1.3, WHITE)]
    return out


def cowboy_hat():
    return [p("M24 16Q23 2 30 3Q36 7 42 3Q49 2 48 16Z", BROWN), p("M6 16Q12 22 36 21Q60 22 66 16Q66 25 36 26Q6 25 6 16Z", BROWN),
            p("M24 13Q36 16 48 13", stroke=YELLOW, stroke_width="2.2")]


def wizard_hat():
    return [p("M22 19L40 -6Q42 -8 43 -5L50 19Z", "#3F5FBF"), p("M16 19Q36 14 56 19Q57 23 55 24Q36 20 17 24Q15 23 16 19Z", "#3F5FBF"),
            p(star_path(38, 6, 3.2), YELLOW, stroke_width="1"), p(star_path(45, 13, 2.2), YELLOW, stroke_width="1")]


def hard_hat():
    return [p("M19 20Q19 4 36 4Q53 4 53 20Z", YELLOW), p("M13 19H59Q60 23 58 24H14Q12 23 13 19Z", YELLOW), p("M36 5V19", stroke_width="1.4")]


def nightcap():
    return [p("M17 21Q16 4 36 2Q54 1 64 20Q63 24 60 23Q52 10 50 13L55 21Z", SKY),
            c(62, 24, 3.4, WHITE, NAVY), p("M15 18Q36 13 57 18Q58 23 56 24Q36 19 16 24Q14 22 15 18Z", WHITE),
            p("M30 9L32 11M42 7L44 9M50 12L51.5 14", stroke=WHITE, stroke_width="1.4")]


def halo():
    return ['<ellipse cx="36" cy="2" rx="14" ry="4" fill="none" stroke="#F2C14E" stroke-width="3.2"/>',
            '<ellipse cx="36" cy="2" rx="14" ry="4" fill="none" stroke="#23364D" stroke-width="1"/>']


def horns():
    return [p("M20 20Q12 10 16 2Q20 12 27 15Z", RED), p("M52 20Q60 10 56 2Q52 12 45 15Z", RED)]


def towel_wrap():
    return [p("M14 24Q12 6 36 4Q60 6 58 24Q36 17 14 24Z", WHITE), p("M24 9Q36 4 50 11M20 16Q36 10 54 17", stroke=GREY, stroke_width="1.3")]


def deerstalker():
    return [p("M18 22Q17 5 36 4Q55 5 54 22Z", "#A8875A"), p("M22 9L50 18M26 6L54 14M18 15L44 23", stroke="#7D6340", stroke_width="1.2"),
            p("M12 22Q24 17 36 18Q48 17 60 22L58 25Q36 20 14 25Z", "#A8875A")]


# --- glasses and masks (face space) --------------------------------------
def nerd_glasses():
    return [c(27, 34, 6.2, "#E6F2FA", NAVY), c(45, 34, 6.2, "#E6F2FA", NAVY), p("M33 33.5Q36 31.5 39 33.5"),
            c(27, 34, 2.4), c(45, 34, 2.4), p("M21 33L16 31M51 33L56 31")]




def med_mask():
    return [p("M22 43Q36 38 50 43V50Q36 59 22 50Z", "#BFE3F2"), p("M24 46Q36 43 48 46M24 49.5Q36 47 48 49.5", stroke="#7FB4CC", stroke_width="1"),
            p("M22 44L14 40M50 44L58 40", stroke_width="1.2")]


def hero_mask():
    return [p("M17 30Q26 26 36 31Q46 26 55 30L54 38Q46 41 36 36Q26 41 18 38Z", RED), c(27, 34, 2.4, WHITE), c(45, 34, 2.4, WHITE)]


def cucumbers():
    return [c(27, 34, 5, "#9BD27A", NAVY), c(27, 34, 3.2, "#D4EFC0"), c(45, 34, 5, "#9BD27A", NAVY), c(45, 34, 3.2, "#D4EFC0")]




# --- decorations around the head (canvas space) --------------------------
def question(x, y, s=1.0, col=NAVY):
    return g([p("M-4 -4Q-4 -9 0 -9Q4 -9 4 -5Q4 -2 0 0V3", stroke=col, stroke_width="2.4"), c(0, 8, 1.5, col)], f"translate({x} {y}) scale({s})")


def exclaim(x, y, s=1.0, col=RED):
    return g([p("M0 -9V2", stroke=col, stroke_width="3"), c(0, 8, 1.8, col)], f"translate({x} {y}) scale({s})")


def sweat(x=55, y=26):
    return [p(f"M{x} {y}Q{x - 3} {y + 5} {x} {y + 7}Q{x + 3} {y + 5} {x} {y}Z", SKY, stroke_width="1.2")]


def steam():
    return [p("M6 12Q9 9 8 6Q11 8 10 12Q8 14 6 12Z", WHITE, stroke_width="1.2"), p("M66 12Q63 9 64 6Q61 8 62 12Q64 14 66 12Z", WHITE, stroke_width="1.2")]


def tears_stream():
    return [p("M24 38V55Q24 58 22 58", stroke=SKY, stroke_width="3"), p("M48 38V55Q48 58 50 58", stroke=SKY, stroke_width="3")]


def notes():
    return [g([p("M0 0V-9L6 -11V-2", stroke_width="1.6"), c(-1.6, 0, 2, NAVY), c(4.4, -2, 2, NAVY)], "translate(61 17)"),
            g([p("M0 0V-8", stroke_width="1.6"), p("M0 -8Q3 -6 4 -3", stroke_width="1.4"), c(-1.6, 0, 2, NAVY)], "translate(11 22)")]


def speed_lines():
    return [p("M5 28H12M4 38H10M5 48H12", stroke_width="1.6")]


def bark_lines():
    return [p("M57 46L64 44M58 51H66M57 56L64 58", stroke_width="1.8")]




def snowflakes():
    return [p("M10 10V18M6 14H14M7 11L13 17M13 11L7 17", stroke=SKY, stroke_width="1.4"),
            p("M64 6V12M61 9H67M62 7L66 11M66 7L62 11", stroke=SKY, stroke_width="1.4"), c(66, 22, 1.2, SKY)]


def sneeze_spray():
    return [c(52, 52, 1.4, SKY), c(57, 50, 1.2, SKY), c(56, 56, 1, SKY), c(61, 53, 1.2, SKY), c(60, 58, 0.9, SKY)]


def kiss_heart():
    return [heart(56, 50, 0.6, "#F07C93")]


# --- paws ----------------------------------------------------------------
def leg(x0, y0, x1, y1, w=8.5):
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1
    ox, oy = -dy / n * w / 2, dx / n * w / 2
    return p(f"M{x0 + ox:.2f} {y0 + oy:.2f}L{x1 + ox:.2f} {y1 + oy:.2f}L{x1 - ox:.2f} {y1 - oy:.2f}L{x0 - ox:.2f} {y0 - oy:.2f}Z", TAN)


def paw(cx, cy, rot=0, to=None, beans=True, s=1.0):
    """A paw pad at (cx, cy); `to` draws the leg down to a point (canvas space)."""
    out = [leg(cx, cy, *to)] if to else []
    pad = [p("M-7 0Q-7 -8.5 0 -8.5Q7 -8.5 7 0Q7 7.5 0 7.5Q-7 7.5 -7 0Z", TAN_LT)]
    if beans:
        pad += [c(-3.5, -3.5, 1.5, BEAN), c(0, -5, 1.5, BEAN), c(3.5, -3.5, 1.5, BEAN),
                p("M-3 2Q0 -1 3 2Q3 4.5 0 4.5Q-3 4.5 -3 2Z", BEAN, stroke="none")]
    else:
        pad += [p("M-2.5 -8V-3M2.5 -8V-3", stroke_width="1.2")]
    return out + [g(pad, f"translate({cx} {cy}) rotate({rot}) scale({s})")]


def badge(kind, x=56, y=56, r=10):
    col = {"check": "#4CAF6A", "x": RED, "q": "#3F5FBF", "!": ORANGE, "100": WHITE}[kind]
    out = [c(x, y, r, col, NAVY)]
    if kind == "check":
        out.append(p(f"M{x - 4.5} {y}L{x - 1} {y + 3.8}L{x + 5} {y - 4}", stroke=WHITE, stroke_width="2.6"))
    elif kind == "x":
        out.append(p(f"M{x - 4} {y - 4}L{x + 4} {y + 4}M{x + 4} {y - 4}L{x - 4} {y + 4}", stroke=WHITE, stroke_width="2.6"))
    elif kind == "q":
        out.append(question(x, y - 1, 0.62, WHITE))
    elif kind == "!":
        out.append(exclaim(x, y - 1, 0.7, WHITE))
    return out


def hundred(x=52, y=58):
    s = "1.9"
    return [p(f"M{x - 9} {y - 4}L{x - 7} {y - 6}V{y + 3}", stroke=RED, stroke_width=s),
            f'<ellipse cx="{x - 1.5}" cy="{y - 1.5}" rx="3" ry="4.5" fill="none" stroke="{RED}" stroke-width="{s}"/>',
            f'<ellipse cx="{x + 6.5}" cy="{y - 1.5}" rx="3" ry="4.5" fill="none" stroke="{RED}" stroke-width="{s}"/>',
            p(f"M{x - 9} {y + 6}H{x + 10}M{x - 8} {y + 8.6}H{x + 9}", stroke=RED, stroke_width="1.5")]


def flame(x=56, y=58, s=1.0):
    return [g([p("M0 10Q-9 10 -9 1Q-9 -6 -2 -12Q-2 -6 2 -4Q3 -9 6 -10Q9 -4 9 2Q9 10 0 10Z", ORANGE),
               p("M0 9Q-4.5 9 -4.5 4Q-4.5 0 0 -3Q1 1 3 2Q4.5 4 4.5 5Q4 9 0 9Z", YELLOW, stroke="none")], f"translate({x} {y}) scale({s})")]


# --- props (canvas space, bottom right unless noted) ---------------------
def mug():
    return [p("M46 46H62V60Q62 64 58 64H50Q46 64 46 60Z", WHITE), p("M62 49Q67 49 67 53.5Q67 58 62 58", stroke_width="1.7"),
            p("M46 46H62", stroke=BROWN, stroke_width="3"), p("M50 41Q48 38 50 35M56 41Q54 38 56 35", stroke=GREY, stroke_width="1.4"),
            heart(54, 55, 0.45, RED)]


def pizza():
    return [p("M42 44L66 40L58 66Z", YELLOW), p("M42 44L66 40", stroke="#C98A3E", stroke_width="4"), p("M42 44L66 40L58 66Z"),
            c(55, 47, 2, RED), c(58, 55, 2, RED), c(52, 52, 1.5, RED)]


def cake():
    return [p("M42 52H66V64H42Z", "#F5D7A1"), p("M42 52H66V56Q63 59 60 56Q57 59 54 56Q51 59 48 56Q45 59 42 56Z", "#F09AC0"),
            p("M54 52V45", stroke=SKY, stroke_width="2.4"), p("M54 39Q57 42 54 45Q51 42 54 39Z", ORANGE, stroke_width="1.1")]


def tennis_ball(x=36, y=53, r=7.5):
    return [c(x, y, r, "#D4E157", NAVY), p(f"M{x - r + 1.5} {y - 4}Q{x} {y} {x - r + 1.5} {y + 4}M{x + r - 1.5} {y - 4}Q{x} {y} {x + r - 1.5} {y + 4}", stroke=WHITE, stroke_width="1.2")]


def stick():
    return [p("M8 47L64 55L63.5 58.5L7.5 50.5Z", BROWN), p("M48 53L53 47", stroke_width="1.6"), c(52, 47, 1.6, GREEN, NAVY)]


def food_bowl():
    return [p("M14 54H58L54 64H18Z", RED), p("M12 52Q36 48 60 52Q60 55 58 55H14Q12 55 12 52Z", "#F0A0A8"),
            p("M28 59L32 59M40 59L44 59", stroke=WHITE, stroke_width="1.4")]


def laptop():
    return [p("M30 42H64V60H30Z", GREY), p("M33 45H61V57H33Z", "#5A84B8", stroke="none"), p("M26 60H68L66 64H28Z", GREY),
            c(47, 51, 2.2, WHITE)]


def phone():
    return [p("M48 40H62Q64 40 64 42V63Q64 65 62 65H48Q46 65 46 63V42Q46 40 48 40Z", DARK), p("M48.5 43.5H61.5V59.5H48.5Z", "#7FB4E0", stroke="none"),
            heart(55, 51.5, 0.5, "#F07C93"), p("M53 62.5H57", stroke=WHITE, stroke_width="1")]


def book():
    return [p("M36 64V48Q28 44 18 46V61Q28 59 36 64Z", WHITE), p("M36 64V48Q44 44 54 46V61Q44 59 36 64Z", WHITE),
            p("M15 49V63Q26 61 36 66Q46 61 57 63V49", stroke=RED, stroke_width="2"),
            p("M22 50Q27 49 32 51M22 54Q27 53 32 55M40 51Q45 49 50 50M40 55Q45 53 50 54", stroke=GREY, stroke_width="1.1")]


def umbrella():
    return [g([p("M6 22Q8 4 36 3Q64 4 66 22Q61 18 56 22Q51 18 46 22Q41 18 36 22Q31 18 26 22Q21 18 16 22Q11 18 6 22Z", RED),
            p("M36 3V1", stroke_width="2"), p("M21 4Q26 10 26 20M51 4Q46 10 46 20", stroke="#B83A44", stroke_width="1.2")], "translate(0 4)")]


def raindrops():
    return [p(f"M{x} {y}Q{x - 2} {y + 3.5} {x} {y + 4.5}Q{x + 2} {y + 3.5} {x} {y}Z", SKY, stroke_width="1") for x, y in [(6, 32), (66, 30), (8, 50), (64, 52)]]


def sun():
    rays = "".join(f"M{48 + 10 * math.cos(math.radians(a)):.1f} {18 + 10 * math.sin(math.radians(a)):.1f}L{48 + 14 * math.cos(math.radians(a)):.1f} {18 + 14 * math.sin(math.radians(a)):.1f}" for a in range(0, 360, 45))
    return [p(rays, stroke=ORANGE, stroke_width="2"), c(48, 18, 7, YELLOW, NAVY)]


def gift():
    return [p("M42 48H66V64H42Z", "#3F5FBF"), p("M40 44H68V50H40Z", "#3F5FBF"), p("M54 44V64", stroke=YELLOW, stroke_width="3.4"),
            p("M54 44Q47 36 46 41Q46 44 54 44Q61 36 62 41Q62 44 54 44Z", YELLOW, stroke_width="1.4")]


def balloon():
    return [p("M57 40Q52 46 58 52Q63 58 58 66", stroke_width="1.2"), p("M57 4Q66 4 66 15Q66 25 57 31Q48 25 48 15Q48 4 57 4Z", RED),
            p("M55 37L57 31L59 37Z", RED, stroke_width="1.2"), p("M52 11Q53 8 56 8", stroke=WHITE, stroke_width="1.6")]


def trophy():
    return [p("M44 40H64V46Q64 56 54 56Q44 56 44 46Z", YELLOW), p("M44 43Q38 43 39 48Q40 52 45 51M64 43Q70 43 69 48Q68 52 63 51"),
            p("M52 56H56V60H52Z", YELLOW), p("M47 60H61V64H47Z", BROWN), p(star_path(54, 47, 3.6), WHITE, stroke_width="1")]


def popcorn():
    return [c(47, 44, 4, WHITE, NAVY), c(54, 41, 4.2, WHITE, NAVY), c(61, 44, 4, WHITE, NAVY), c(51, 46.5, 3.6, "#FFF2C4", NAVY), c(58, 46.5, 3.6, "#FFF2C4", NAVY),
            p("M44 48H64L61 66H47Z", WHITE), p("M49 48L50.5 66M54 48V66M59 48L57.5 66", stroke=RED, stroke_width="2.4"), p("M44 48H64L61 66H47Z")]


def ice_cream():
    return [p("M48 46H62L55 66Z", "#E9B872"), p("M50 50L59 59M58 49L52 56", stroke="#B98444", stroke_width="1"),
            c(55, 40, 7, "#F5B2C2", NAVY), c(55, 31.5, 5, "#FFF2D9", NAVY), c(55, 25.5, 2, RED, NAVY)]


def pumpkin():
    return [p("M54 46Q44 45 42 54Q42 64 54 64Q66 64 66 54Q64 45 54 46Z", ORANGE), p("M54 47Q49 55 54 63.5M54 47Q59 55 54 63.5", stroke="#C46520", stroke_width="1.2"),
            p("M54 46Q54 42 57 40", stroke="#5D8B3A", stroke_width="2.4")]


def xmas_tree():
    return [p("M55 34L65 48H60L67 59H43L50 48H45Z", "#4C9A5A"), p("M53 59H57V65H53Z", BROWN), p(star_path(55, 33, 3.6), YELLOW, stroke_width="1"),
            c(51, 52, 1.4, RED), c(59, 54, 1.4, YELLOW), c(56, 45, 1.4, SKY)]


def flower():
    out = [p("M52 64Q50 54 56 44", stroke="#5D8B3A", stroke_width="2.2"), p("M51 56Q46 52 47 48Q52 50 52 55Z", GREEN, stroke_width="1.2")]
    for a in range(0, 360, 72):
        x, y = 56 + 5.2 * math.cos(math.radians(a - 90)), 38 + 5.2 * math.sin(math.radians(a - 90))
        out.append(c(round(x, 2), round(y, 2), 3.6, "#F09AC0", NAVY))
    return out + [c(56, 38, 3, YELLOW, NAVY)]


def camera():
    return [p("M38 46H44L46 42H54L56 46H64Q66 46 66 48V62Q66 64 64 64H38Q36 64 36 62V48Q36 46 38 46Z", DARK),
            c(51, 55, 6, GREY, NAVY), c(51, 55, 3, "#5A84B8"), c(61, 50, 1.2, YELLOW)]




def big_heart(x=36, y=55, s=1.9, fill=RED):
    return [heart(x, y, s, fill)]


def broken_heart():
    return [g([p("M0 5L-5.5 -0.5Q-7 -2.6 -5.2 -4.6Q-2.6 -6.6 0 -3.2L-1 -0.5L1 1.5L-0.5 4Z", RED, stroke_width="0.9")], "translate(34 55) scale(1.9)"),
            g([p("M0 5L5.5 -0.5Q7 -2.6 5.2 -4.6Q2.6 -6.6 0 -3.2L-1 -0.5L1 1.5L-0.5 4Z", RED, stroke_width="0.9")], "translate(39 55) scale(1.9)")]


def leash():
    return [p("M30 51Q20 56 18 64", stroke=RED, stroke_width="3"), p("M42 51Q56 52 60 64", stroke=RED, stroke_width="3"), c(36, 51, 3, GREY, NAVY)]


def magnifier():
    return [p("M51 41L62 54", stroke=BROWN, stroke_width="4.4"), c(45, 34, 8, "#E6F2FA", NAVY), c(45, 34, 3)]


def tub():
    out = [p("M7 44H65V52Q65 62 55 62H17Q7 62 7 52Z", WHITE), p("M15 62L13 66M57 62L59 66", stroke_width="2"), p("M6 44H66", stroke_width="2.4")]
    for x, y, r in [(11, 40, 4), (18, 37, 4.6), (54, 37, 4.6), (61, 40, 4), (25, 41, 3.4), (47, 41, 3.4), (63, 30, 2), (9, 30, 1.6)]:
        out.append(c(x, y, r, "#E6F2FA", NAVY))
    return out


def teacup():
    return [p("M12 44H58V50Q58 64 44 64H26Q12 64 12 50Z", "#F5F0FA"), p("M58 48Q66 48 66 54Q66 60 57 59", stroke_width="1.8"),
            p("M12 44H58", stroke_width="2"), p("M22 52Q26 56 30 52M40 52Q44 56 48 52", stroke="#B9A5D8", stroke_width="1.4"),
            p("M6 64H64", stroke_width="2")]


def dog_bed():
    return [p("M4 50Q4 38 36 38Q68 38 68 50Q68 64 36 64Q4 64 4 50Z", "#5A84B8"), p("M12 50Q12 44 36 44Q60 44 60 50Q60 58 36 58Q12 58 12 50Z", "#BFD6EE")]


def ghost_sheet():
    return [p("M14 34Q14 10 36 10Q58 10 58 34V60L53 56L48 61L42 56L36 61L30 56L24 61L19 56L14 60Z", WHITE),
            '<ellipse cx="28" cy="32" rx="3" ry="4" fill="#23364D"/>', '<ellipse cx="44" cy="32" rx="3" ry="4" fill="#23364D"/>',
            p("M33 42Q36 45 39 42", stroke_width="1.4")]


def wall():
    return [p("M5 46H67V64H5Z", "#B9A5D8"), p("M5 46H67", stroke_width="2"), p("M12 54H20M30 58H44M52 53H60", stroke="#9A86C0", stroke_width="1.2")]




# --- the set -------------------------------------------------------------
HAPPY = (eyes_closed_happy(), mouth_open())


def hatted(hat, eyes=None, mouth=None, s=0.8, dy=6, **kw):
    return [fit(face(eyes or eyes_dot(), mouth or mouth_smile(), over=hat, **kw), s, 0, dy)]


def with_prop(parts, prop, s=0.76, dx=-8, dy=-3, front=True):
    head_part = fit(parts, s, dx, dy)
    return [head_part] + prop if front else prop + [head_part]


def reaction(parts, extra, s=0.84, dx=-4, dy=-2):
    return [fit(parts, s, dx, dy)] + extra


EXTRA = {
    # expressions
    "yorkie_cry": ("Crying", face(eyes_squeeze(), mouth_wail()) + tears_stream()),
    "yorkie_blush": ("Blushing", face(eyes_closed_happy(), mouth_smile(), over=blush())),
    "yorkie_dizzy": ("Dizzy", face(eyes_spiral(), mouth_wavy()) + [sparkle(10, 12, 3.4), sparkle(62, 14, 3)]),
    "yorkie_smirk": ("Smirk", face(eyes_side(), mouth_smirk())),
    "yorkie_unamused": ("Unamused", face(eyes_unamused(), mouth_frown())),
    "yorkie_nervous": ("Nervous sweat", face(eyes_worried(), mouth_wavy()) + sweat()),
    "yorkie_yawn": ("Yawn", face(eyes_squeeze(), mouth_yawn())),
    "yorkie_kiss": ("Blowing a kiss", face(eyes_wink(), mouth_kiss(), over=blush()) + kiss_heart()),
    "yorkie_star_struck": ("Star-struck", face(eyes_stars(), mouth_open())),
    "yorkie_angry": ("Angry", face(eyes_angry(), mouth_teeth()) + steam()),
    "yorkie_scream": ("Scream", face(eyes_wow(), mouth_yawn()) + [exclaim(62, 16, 0.9)]),
    "yorkie_zany": ("Zany", face(eyes_zany(), mouth_tongue_side())),
    "yorkie_content": ("Content", face(eyes_calm(), mouth_smile())),
    "yorkie_hungry": ("Drooling", face(eyes_big(), mouth_drool())),
    "yorkie_sneeze": ("Sneeze", face(eyes_squeeze(), mouth_o()) + sneeze_spray()),
    "yorkie_eye_roll": ("Eye roll", face(eyes_up(), mouth_flat())),
    "yorkie_head_tilt": ("Head tilt", [g([fit(face(eyes_dot(), mouth_flat()), 0.88, -2, 2)], "rotate(-14 36 38)")] + [question(61, 16, 0.9)]),
    "yorkie_bark": ("Bark", [fit(face(eyes_angry(), mouth_open()), 0.86, -5, 0)] + bark_lines()),
    "yorkie_mask": ("Face mask", face(eyes_dot(), [], over=med_mask())),
    "yorkie_nerd": ("Nerd glasses", face(nerd_glasses(), mouth_smile())),
    "yorkie_hero": ("Superhero mask", face(hero_mask(), mouth_smile(), neck="bandana")),
    "yorkie_spa": ("Spa day", hatted(towel_wrap(), cucumbers(), mouth_smile(), s=0.86, dy=3)),
    "yorkie_zoomies": ("Zoomies", [fit(face(eyes_wow(), mouth_tongue_side(), fold_left=True), 0.86, 4, 0)] + speed_lines()),
    # hats and costumes
    "yorkie_crown": ("Crown", hatted(crown())),
    "yorkie_bow": ("Topknot bow", hatted(topknot_bow(), mouth=mouth_blep(), s=0.86, dy=4)),
    "yorkie_chef": ("Chef", hatted(chef_hat(), *HAPPY)),
    "yorkie_grad": ("Graduate", hatted(grad_cap(), *HAPPY)),
    "yorkie_santa": ("Santa hat", hatted(santa_hat(), mouth=mouth_blep(), neck="scarf")),
    "yorkie_witch": ("Witch hat", hatted(witch_hat(), mouth=mouth_smirk())),
    "yorkie_bunny": ("Bunny ears", hatted(bunny_ears(), mouth=mouth_blep(), s=0.78, dy=8)),
    "yorkie_pirate": ("Pirate", hatted(pirate() + eyepatch(), [c(27, 34, 3.2), c(28, 32.8, 1.1, WHITE)], mouth_smirk(), s=0.84, dy=4)),
    "yorkie_beanie": ("Beanie", hatted(beanie(), neck="scarf")),
    "yorkie_headphones": ("Headphones", [fit(face(eyes_calm(), mouth_smile(), over=headphones()), 0.88, 0, 1)] + notes()),
    "yorkie_flower_crown": ("Flower crown", hatted(flower_crown(), eyes_closed_happy(), mouth_smile(), s=0.86, dy=3)),
    "yorkie_bandana": ("Star bandana", face(eyes_dot(dx=1), mouth_lick(), neck="bandana")),
    "yorkie_cowboy": ("Cowboy", hatted(cowboy_hat(), mouth=mouth_smirk(), s=0.82, dy=5)),
    "yorkie_wizard": ("Wizard", hatted(wizard_hat(), eyes_dot(), mouth_smirk(), s=0.78, dy=9)),
    "yorkie_hard_hat": ("Hard hat", hatted(hard_hat(), mouth=mouth_flat())),
    "yorkie_nightcap": ("Nightcap", hatted(nightcap(), eyes_sleep(), mouth_flat())),
    "yorkie_angel": ("Angel", hatted(halo(), eyes_calm(), mouth_smile(), s=0.84, dy=6)),
    "yorkie_devil": ("Little devil", hatted(horns(), eyes_side(), mouth_smirk(), s=0.84, dy=4)),
    "yorkie_detective": ("Detective", [fit(face([c(27, 34, 3)], mouth_flat(), over=deerstalker() + magnifier()), 0.82, -2, 5)]),
    "yorkie_astronaut": ("Astronaut", [fit(face(eyes_wow(), mouth_open(), neck="none"), 0.72, 0, -2),
                                       p("M14 58Q14 52 22 52H50Q58 52 58 58V64H14Z", GREY),
                                       '<circle cx="36" cy="32" r="27" fill="#BFE3F2" fill-opacity="0.35" stroke="#23364D"/>',
                                       p("M17 22Q21 12 31 9", stroke=WHITE, stroke_width="2.4")]),
    "yorkie_ghost": ("Ghost costume", ears() + ghost_sheet()),
    # props
    "yorkie_coffee": ("Coffee", with_prop(face(eyes_sleep(), mouth_flat()), mug())),
    "yorkie_pizza": ("Pizza", with_prop(face(eyes_hearts(), mouth_drool()), pizza())),
    "yorkie_cake": ("Birthday cake", with_prop(face(*HAPPY, over=party_hat()), cake(), s=0.72, dy=0)),
    "yorkie_ball": ("Tennis ball", face(eyes_big(), mouth_holding(12)) + tennis_ball()),
    "yorkie_stick": ("Stick", face(eyes_closed_happy(), mouth_holding(30)) + stick()),
    "yorkie_bowl": ("Empty bowl", [fit(face(eyes_big(), mouth_frown()), 0.76, 0, -6)] + food_bowl()),
    "yorkie_laptop": ("Working", with_prop(face(eyes_dot(dx=1), mouth_flat(), neck="stripes"), laptop(), dx=-10)),
    "yorkie_phone": ("Phone", with_prop(face(eyes_dot(dx=1), mouth_smile()), phone() + paw(48, 57, -20, to=(41, 64)), dx=-9)),
    "yorkie_book": ("Reading", [fit(face(nerd_glasses(), mouth_flat()), 0.76, 0, -7)] + book()),
    "yorkie_rain": ("Rainy day", [fit(face(eyes_worried(), mouth_frown()), 0.76, 0, 7)] + umbrella() + raindrops()),
    "yorkie_sunny": ("Sunny", [fit(face(sunglasses(), mouth_blep()), 0.84, -5, 4)] + sun()),
    "yorkie_cold": ("Cold", hatted(beanie(), eyes_squeeze(), mouth_wavy(), neck="scarf", s=0.8, dy=6) + snowflakes()),
    "yorkie_gift": ("Gift", with_prop(face(eyes_stars(), mouth_open()), gift(), dx=-9)),
    "yorkie_balloon": ("Balloon", with_prop(face(*HAPPY), balloon(), dx=-9, dy=6)),
    "yorkie_trophy": ("Trophy", with_prop(face(eyes_closed_happy(), mouth_open(), over=crown()), [g(trophy(), "translate(-3 0)")], s=0.7, dx=-11, dy=0)),
    "yorkie_popcorn": ("Popcorn", with_prop(face(eyes_wow(), mouth_flat()), popcorn(), dx=-9)),
    "yorkie_ice_cream": ("Ice cream", with_prop(face(eyes_closed_happy(), mouth_blep()), ice_cream(), dx=-10, dy=4)),
    "yorkie_pumpkin": ("Pumpkin", with_prop(face(eyes_dot(), mouth_smirk(), over=witch_hat()), pumpkin(), s=0.66, dx=-8, dy=4)),
    "yorkie_xmas_tree": ("Holiday tree", with_prop(face(eyes_closed_happy(), mouth_blep(), over=santa_hat(), neck="scarf"), xmas_tree(), s=0.68, dx=-9, dy=4)),
    "yorkie_flower": ("Flower", with_prop(face(eyes_calm(), mouth_smile(), over=blush()), flower(), dx=-9, dy=2)),
    "yorkie_camera": ("Camera", with_prop(face(eyes_wink(), mouth_smile()), camera(), dx=-9, dy=-4)),
    "yorkie_heart": ("Big heart", [fit(face(eyes_closed_happy(), mouth_smile(), over=blush()), 0.78, 0, -7)] + big_heart()),
    "yorkie_heartbreak": ("Heartbreak", [fit(face(eyes_squeeze(), mouth_wail()), 0.78, 0, -7)] + broken_heart()),
    # paw reactions
    "yorkie_yes": ("Approve", reaction(face(*HAPPY), badge("check"))),
    "yorkie_no": ("Nope", reaction(face(eyes_grumpy(), mouth_frown()), badge("x"))),
    "yorkie_question": ("Question", reaction(face(eyes_worried(), mouth_wavy()), badge("q"))),
    "yorkie_important": ("Important", reaction(face(eyes_wow(), mouth_o()), badge("!"))),
    "yorkie_100": ("One hundred", reaction(face(eyes_stars(), mouth_open()), hundred(56, 58), dx=-7, dy=-4)),
    "yorkie_fire": ("On fire", reaction(face(sunglasses(), mouth_smirk()), flame())),
    "yorkie_sparkles": ("Sparkles", face(eyes_closed_happy(), mouth_smile(), over=blush()) + [sparkle(9, 12, 5), sparkle(63, 10, 4), sparkle(65, 26, 2.6)]),
    "yorkie_high_five": ("High five", reaction(face(*HAPPY), paw(56, 24, 8, to=(55, 64), s=1.05) + [p("M62 11L65 7M65 19L68.5 18M52 10L51 6", stroke_width="1.6")], s=0.82, dx=-6, dy=3)),
    "yorkie_facepalm": ("Facepalm", face(eyes_dot(), mouth_frown()) + paw(29, 35, 15, to=(23, 64), beans=False, s=1.15)),
    "yorkie_hug": ("Hug", face(eyes_closed_happy(), mouth_smile(), over=blush()) + paw(22, 56, 20, to=(14, 64)) + paw(50, 56, -20, to=(58, 64))),
    "yorkie_peek": ("Peeking", [fit(face(eyes_big(), [], neck="none"), 0.8, 0, 4)] + wall() + paw(22, 47, 0, beans=False, s=0.9) + paw(50, 47, 0, beans=False, s=0.9)),
    # scenes
    "yorkie_stripe_sweater": ("Striped sweater", [p("M14 64V50Q14 40 23 40H49Q58 40 58 50V64Z", DARK),
                                                 p("M14 50H58M14 56H58", stroke=RED, stroke_width="2.6"), p("M14 53H58M14 59.5H58", stroke=WHITE, stroke_width="2"),
                                                 p("M14 64V50Q14 40 23 40H49Q58 40 58 50V64Z"),
                                                 g(face(eyes_dot(dx=-1), mouth_blep(), fold_left=True, neck="none"), "translate(9.36 -2) scale(0.74)")]),
    "yorkie_bath": ("Bath time", [fit(face(eyes_worried(), mouth_wavy(), neck="none"), 0.76, 0, -4)] + tub()),
    "yorkie_teacup": ("Teacup Yorkie", [fit(face(eyes_big(), mouth_blep(), neck="none"), 0.72, -1, -6)] + teacup()),
    "yorkie_nap": ("Nap in bed", dog_bed() + [fit(face(eyes_sleep(), mouth_flat(), fold_left=True, neck="none"), 0.66, -6, 2)] + zzz()),
    "yorkie_walkies": ("Walkies", face(eyes_big(), mouth_holding(14)) + leash()),
}


ALL = {**EMOJIS, **EXTRA}
