from lib import *
import random, math
random.seed(16)
N=60; C=50
grid=[[None]*N for _ in range(N)]
sky=["#0b0f2a","#121640","#1c1d52","#2a2463","#3b2a6e"]
for r in range(N):
    for c in range(N):
        if r<40: grid[r][c]=sky[min(4,r//8)]
        else: grid[r][c]="#2d4a2b" if r<52 else "#22381f"
for _ in range(70):
    r=random.randint(0,30); c=random.randint(0,59)
    if 4<=r<=12: continue
    grid[r][c]=random.choice(["#ffffff","#fff3b0","#b9c6ff"])
for r in range(N):
    for c in range(N):
        if (c-49)**2+(r-9)**2<=10: grid[r][c]="#f4e9c1"
# mountains
for c in range(N):
    h=int(5+3*math.sin(c/4.0)+2*math.sin(c/1.7))
    for r in range(40-h,40): grid[r][c]="#191637"
# ground glow around fire
for r in range(40,N):
    for c in range(N):
        d=math.hypot((c-30)/1.6,(r-46))
        if d<6: grid[r][c]="#5b6b2e"
        elif d<10: grid[r][c]="#3f5a2c"
for r in range(40,N):
    for c in range(N):
        if random.random()<0.06: grid[r][c]="#1d311b"
def sprite(rows, r0, c0, pal, flip=False):
    for i,row in enumerate(rows):
        if flip: row=row[::-1]
        for j,ch in enumerate(row):
            if ch!='.': grid[r0+i][c0+j]=pal[ch]
fire=["....Y....",
      "...YY....",
      "...YOY...",
      "..YOOY.Y.",
      ".YOORRYY.",
      ".YORWROY.",
      "YORWWWROY",
      "YORWWWROY",
      ".YRRWRRY.",
      "..BBBBB..",
      ".BbBBBbB."]
sprite(fire,37,26,{"Y":"#ffd23f","O":"#ff8c1a","R":"#ff3d1f","W":"#fff6d6","B":"#6b3a1e","b":"#3e2010"})
guy=["..HH..",
     ".HHHH.",
     ".SSSE.",
     ".SSSS.",
     "..SS..",
     ".TTTT.",
     "TTTTTA",
     "TTTT.A",
     ".LLLLL",
     ".LL..F"]
people=[(16,"#c0392b","#3b2414","#e0ac69",False),(21,"#2e86ab","#111111","#8d5524",False),
        (35,"#f2c14e","#7a4a22","#f1c27d",True),(40,"#8e44ad","#2b1d14","#c68642",True)]
for c0,shirt,hair,skin,fl in people:
    sprite(guy,37,c0,{"H":hair,"S":skin,"E":"#111111","T":shirt,"A":skin,"L":"#2c3e50","F":"#111111"},flip=fl)
# one path per colour
by={}
for r in range(N):
    for c in range(N):
        by.setdefault(grid[r][c],[]).append(f"M{c*C} {r*C}h{C}v{C}h-{C}Z")
ops = strip_all()
for i,(col,subs) in enumerate(by.items()):
    ops.append({"type":"shape","shape":"path","name":f"px{i}","path":"".join(subs),"x":0,"y":0,"fill":col})
ops += text("title","FRIENDS AND FLAMES","pixel",130,"#ffd23f",0,250)
ops += [{"type":"move","target":"title","x":"center"},
        {"type":"layer-style","target":"title","name":"drop-shadow","settings":{"color":"#ff3d1f","dx":12,"dy":12,"blur":0,"opacity":1}}]
ops += text("artist","JEFFREY X GUNTLY","pixel",60,"#ffffff",0,520)
ops += [{"type":"move","target":"artist","x":"center"}]
ops += text("ly","PRESS START TO RALLY","pixel",44,"#b9c6ff",0,2780)
ops += [{"type":"move","target":"ly","x":150}]
ops += pa(2500,2650,400)
save('c16',ops)
print(len(by))
