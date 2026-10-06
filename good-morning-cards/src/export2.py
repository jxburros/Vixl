import sys, os; sys.path.insert(0,'.')
from common import *
import numpy as np
name, out = sys.argv[1], sys.argv[2]
p = Project.load(name + '.vixl')
dur = p.state['timeline']['duration']; fps = 20
f = lambda t: np.asarray(render_at(p, t).convert('RGB'), dtype=float)
a, last, nxt = f(0), f(dur - 1000/fps), f(1000/fps)
print(name, 'seam(last->first)=%.3f  typical step=%.3f' % (np.abs(a-last).mean(), np.abs(a-nxt).mean()))
for ext, kw, fp in (('gif', dict(colors=96, scale=0.7), 15), ('mp4', dict(scale=1.0), 30)):
    path = f'{out}.{ext}'
    export_timeline(p, path, fps=fp, overwrite=True, **kw)
    print(' ', path, os.path.getsize(path)//1024, 'KB')
