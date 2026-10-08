import json, sys, glob, os
from vixl.project import Project
os.chdir('friends-and-flames')
for f in sorted([f for f in glob.glob('var13/*.vixl') if any(k in f for k in sys.argv[1:])]):
    k=os.path.basename(f)[:-5]
    p=Project.load(f)
    try:
        p.apply(json.load(open(f'ops/r13-{k}.json')))
    except Exception as e:
        print("FAIL",k,e); continue
    p.save(f, overwrite=True)
    data=p.export(format="JPEG", quality=95)
    open(f'covers/07A-S10409-{k}.jpg','wb').write(data if isinstance(data,bytes) else data)
    print("ok",k,flush=True)
