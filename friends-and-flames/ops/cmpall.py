import sys, glob
from vixl.project import Project
from vixl.proxy import render_preview
from PIL import Image, ImageChops
for f in sorted(glob.glob('friends-and-flames/*.vixl')):
    p=Project.load(f)
    full=p.render().convert('RGB').resize((400,400),Image.LANCZOS)
    prev=render_preview(p,400,400).convert('RGB')
    d=ImageChops.difference(full,prev).convert('L')
    bad=sum(1 for v in d.getdata() if v>80)
    print(f"{bad:6d}  {f}", flush=True)
