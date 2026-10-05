"""Editable source for T10: re-run to regenerate all deliverables from the untouched raw."""
import os, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '../../../../fixtures/coast-raw.jpg')

# ---- adjustment settings -----------------------------------------------
ANGLE = 2.2          # deg, counter-clockwise (horizon falls 2.2 deg to the right in raw)
DENOISE_H = 8        # fastNlMeansDenoisingColored luminance strength
DENOISE_HC = 10      # chroma strength
WB_GAINS = None      # computed (gray-world on mid-tones) if None
BLACK_PCT, WHITE_PCT = 0.5, 99.7   # levels stretch percentiles (on luma)
GAMMA = 0.80         # <1 brightens mid-tones (exposure lift)
SATURATION = 1.05
# ---- round 2 ----
WARM_R, WARM_G, WARM_B = 1.04, 1.01, 0.94   # warmth: per-channel gains (RGB)
CONTRAST = 0.90      # <1 = less contrast: pull tones toward the mean luma pivot

def load():
    return cv2.imread(SRC)  # BGR uint8

def denoise(img):
    return cv2.fastNlMeansDenoisingColored(img, None, DENOISE_H, DENOISE_HC, 7, 21)

def level(img):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ANGLE, 1.0)
    rot = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4, borderValue=0)
    # valid area: raw was already rotated (black wedges), so content survives where
    # a full frame rotated by -ANGLE then +ANGLE stays filled.
    ones = np.full((h, w), 255, np.uint8)
    Mi = cv2.getRotationMatrix2D((w / 2, h / 2), -ANGLE, 1.0)
    m = cv2.warpAffine(ones, Mi, (w, h), flags=cv2.INTER_NEAREST)
    m = cv2.warpAffine(m, M, (w, h), flags=cv2.INTER_NEAREST) > 0
    # largest centred rectangle with original aspect that is fully valid (+2px safety)
    best = None
    for s in np.arange(1.0, 0.8, -0.001):
        cw, ch = int(w * s), int(h * s)
        x0, y0 = (w - cw) // 2, (h - ch) // 2
        if m[y0:y0 + ch, x0:x0 + cw].all():
            best = (x0 + 2, y0 + 2, cw - 4, ch - 4); break
    x, y, cw, ch = best
    return rot[y:y + ch, x:x + cw], best

def color(img):
    f = img.astype(np.float32) / 255.0
    # white balance: gray-world on mid-tones (exclude near-black land & clipped sun)
    luma = f.mean(2)
    sel = (luma > 0.12) & (luma < 0.85)
    means = f[sel].reshape(-1, 3).mean(0)
    gains = WB_GAINS if WB_GAINS is not None else means.mean() / means
    # soften toward neutral so the warm sunset is kept (50 % correction)
    gains = 1 + 0.5 * (np.asarray(gains) - 1)
    f = f * gains
    # levels + gamma (exposure)
    luma = f.mean(2)
    lo, hi = np.percentile(luma, [BLACK_PCT, WHITE_PCT])
    f = np.clip((f - lo) / (hi - lo), 0, 1) ** GAMMA
    # round 2: warmth (BGR order) then reduced contrast around the mean luma
    f = np.clip(f * np.array([WARM_B, WARM_G, WARM_R], np.float32), 0, 1)
    pivot = float(f.mean())
    f = np.clip(pivot + CONTRAST * (f - pivot), 0, 1)
    print('contrast pivot:', pivot)
    # saturation
    hsv = cv2.cvtColor((f * 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * SATURATION, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return out, gains, (lo, hi)

def main():
    raw = load()
    d = denoise(raw)
    lv, rect = level(d)
    out, gains, lohi = color(lv)
    cv2.imwrite(os.path.join(HERE, 'coast-edited.jpg'), out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print('crop rect (x,y,w,h) in rotated frame:', rect, 'size', out.shape[1], 'x', out.shape[0])
    print('WB gains BGR:', gains, 'levels lo/hi:', lohi)
    pil = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    W, H = pil.size

    # ---- Instagram 1080x1350 (4:5) ----
    ch = H; cw = round(ch * 1080 / 1350)
    cx = int(W * IG_CENTER_X); x0 = min(max(cx - cw // 2, 0), W - cw)
    ig = pil.crop((x0, 0, x0 + cw, ch)).resize((1080, 1350), Image.LANCZOS)
    ig.save(os.path.join(HERE, 'coast-instagram.jpg'), quality=95)
    print('instagram crop box:', (x0, 0, x0 + cw, ch), 'scale', 1350 / ch)

    # ---- Caption 1600x900 (16:9) ----
    cw2 = W; ch2 = round(W * 9 / 16)
    if ch2 > H: ch2 = H; cw2 = round(H * 16 / 9)
    y0 = min(max(int(H * CAP_CENTER_Y) - ch2 // 2, 0), H - ch2)
    x1 = (W - cw2) // 2
    cap = pil.crop((x1, y0, x1 + cw2, y0 + ch2)).resize((1600, 900), Image.LANCZOS).convert('RGBA')
    print('caption crop box:', (x1, y0, x1 + cw2, y0 + ch2))
    grad = np.zeros((900, 1600), np.float32)
    gy = np.clip((np.arange(900) - 900 * 0.55) / (900 * 0.45), 0, 1) ** 1.5
    gx = np.clip(1.15 - np.arange(1600) / 1600, 0.35, 1)
    grad = np.outer(gy, gx) * 0.72
    ov = np.zeros((900, 1600, 4), np.uint8); ov[..., 3] = (grad * 255).astype(np.uint8)
    cap = Image.alpha_composite(cap, Image.fromarray(ov))
    font = ImageFont.truetype(FONT, 64)
    dr = ImageDraw.Draw(cap)
    text = 'Port Ellery, October evening'
    bb = dr.textbbox((0, 0), text, font=font)
    tx, ty = 72, 900 - 72 - (bb[3])
    dr.text((tx + 2, ty + 2), text, font=font, fill=(0, 0, 0, 110))
    dr.text((tx, ty), text, font=font, fill=(255, 246, 232, 255))
    cap.convert('RGB').save(os.path.join(HERE, 'coast-caption.png'))
    print('caption text box:', (tx + bb[0], ty + bb[1], tx + bb[2], ty + bb[3]))

IG_CENTER_X = 0.65    # keeps sun, figure and sun glitter; excludes headland tip; lighthouse falls outside 4:5
CAP_CENTER_Y = 0.5
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'

if __name__ == '__main__':
    main()
