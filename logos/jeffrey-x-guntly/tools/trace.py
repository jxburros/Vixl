import json, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import potrace

SRC, OUT = sys.argv[1], sys.argv[2]
S = 4  # supersample for smoother curves
g = Image.open(SRC).convert('L')
gb = np.array(g.resize((g.width*S, g.height*S), Image.BICUBIC)) < 128
b = np.array(g) < 128
lab, n = ndimage.label(b)
_, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
nearest = lab[iy, ix]
labS = np.array(Image.fromarray(nearest.astype(np.int32)).resize(gb.shape[::-1], Image.NEAREST))
# dilate low-res labels a bit so the supersampled edge pixels get a label
names = {4:'J',5:'e',2:'f',3:'f 2',6:'r',7:'e 2',8:'y',10:'G',13:'u',12:'n',11:'t',9:'l',14:'y 2'}
# X thick stroke polygon (canvas px) and the vine/X crossing
poly = [(712,276),(778,276),(802,322),(808,340),(822,365),(850,400),(880,440),(930,495),(930,505),
        (860,505),(835,485),(835,450),(830,440),(808,400),(795,380),(785,365),(765,338),(740,333),(738,305),(712,290)]
pm = Image.new('L', gb.shape[::-1], 0)
ImageDraw.Draw(pm).polygon([(x*S,y*S) for x,y in poly], fill=1)
pm = np.array(pm).astype(bool)
yy, xx = np.mgrid[0:gb.shape[0], 0:gb.shape[1]]
def jline(w):
    jm = Image.new('L', gb.shape[::-1], 0)
    ImageDraw.Draw(jm).line([(838*S,326*S),(766*S,404*S)], fill=1, width=w*S)
    return np.array(jm).astype(bool)
junction = jline(22)
jvine = jline(15)

def near(i):
    return gb & (labS == i)

parts = {}
for i, nm in names.items():
    parts[nm] = near(i)
c1 = near(1)
bm_ = Image.new('L', gb.shape[::-1], 0)
ImageDraw.Draw(bm_).polygon([(x*S,y*S) for x,y in [(769,336),(792,336),(830,388),(807,388)]], fill=1)
band = np.array(bm_).astype(bool)
parts['X'] = c1 & ((pm & ~junction) | (junction & band))
parts['vine'] = c1 & ~(pm & ~junction) & ~(band & ~jvine)

def to_path(mask):
    bm = potrace.Bitmap(~mask)
    pl = bm.trace(turdsize=8, alphamax=1.0, opticurve=True, opttolerance=0.2)
    out = []
    f = lambda p: f"{p.x/S:.2f} {p.y/S:.2f}"
    for c in pl:
        out.append("M" + f(c.start_point))
        for seg in c.segments:
            if seg.is_corner:
                out.append("L" + f(seg.c) + " L" + f(seg.end_point))
            else:
                out.append("C" + f(seg.c1) + " " + f(seg.c2) + " " + f(seg.end_point))
        out.append("Z")
    return " ".join(out)

res = {nm: to_path(m) for nm, m in parts.items()}
json.dump(res, open(OUT, 'w'))
print({k: len(v) for k, v in res.items()})
