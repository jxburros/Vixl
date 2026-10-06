import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('L')
for spec in sys.argv[2:]:
    y, x0, x1 = map(int, spec.split(','))
    runs = []; start = None
    for x in range(x0, x1):
        dark = im.getpixel((x, y)) < 128
        if dark and start is None: start = x
        if not dark and start is not None: runs.append((start, x - 1)); start = None
    if start is not None: runs.append((start, x1))
    print(y, [(a, b, b - a + 1, (a + b) // 2) for a, b in runs])
