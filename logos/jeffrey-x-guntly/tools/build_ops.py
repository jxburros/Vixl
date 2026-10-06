import json, re, sys
paths = json.load(open(sys.argv[1]))
def bbox(d):
    nums = list(map(float, re.findall(r'-?\d+\.?\d*', d)))
    return min(nums[0::2]), min(nums[1::2]), max(nums[0::2]), max(nums[1::2])
def shift(d, dx, dy):
    out, k = [], 0
    for t in re.findall(r'[MLCZ]|-?\d+\.?\d*', d):
        if t in 'MLCZ': out.append(t)
        else:
            out.append(f"{float(t) - (dx if k % 2 == 0 else dy):.2f}"); k += 1
    return " ".join(out)
ops = [{"type": "remove", "target": t} for t in sys.argv[3:]]
groups = {"Jeffrey": ['J','e','f','f 2','r','e 2','y'], "Guntly": ['G','u','n','t','l','y 2']}
for nm in ['vine','X'] + groups['Jeffrey'] + groups['Guntly']:
    d = paths[nm]; x0, y0, x1, y1 = bbox(d); x0, y0 = int(x0), int(y0)
    ops.append({"type": "shape", "shape": "path", "name": nm, "x": x0, "y": y0,
                "width": int(x1 - x0) + 2, "height": int(y1 - y0) + 2,
                "path": shift(d, x0, y0), "fill": "#000000", "stroke": "transparent"})
ops += [{"type": "group", "name": "Jeffrey", "targets": groups['Jeffrey']},
        {"type": "group", "name": "Guntly", "targets": groups['Guntly']},
        {"type": "group", "name": "Jeffrey X Guntly", "targets": ['vine', 'X', 'Jeffrey', 'Guntly']}]
json.dump(ops, open(sys.argv[2], 'w'))
