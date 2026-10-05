# Round 2: red roof + chimney on right roof slope. Edits copies of the round-1 SVGs.
import re
src='..'  # round-1 folder relative to round2/
R=(834.5,412.9,1131.9,700.9)  # roofR line
def roofy(x):
    x1,y1,x2,y2=R; return y1+(x-x1)*(y2-y1)/(x2-x1)
def roofx(y):
    x1,y1,x2,y2=R; return x1+(y-y1)*(x2-x1)/(y2-y1)
# chimney sides with a slight hand lean (~1 deg, like the walls), top at y~478
top=478.0; lean=0.017  # dx per dy
def side(xtop):
    # intersect x = xtop + lean*(y-top) with roof line
    y=top
    for _ in range(30): y=roofy(xtop+lean*(y-top))
    return (xtop,top),(xtop+lean*(y-top),y)
L0,L1=side(982.0); R0,R1=side(1046.0)
tA=(L0[0]-6, top+0.8); tB=(R0[0]+6, top-0.8)  # top edge with small overshoot past corners
p=lambda a:f'{a[0]:.1f}'; q=lambda a:f'{a[1]:.1f}'
chim_lines=(f'<line id="chimneyL" x1="{p(L0)}" y1="{q(L0)}" x2="{p(L1)}" y2="{q(L1)}"/>\n'
 f'<line id="chimneyR" x1="{p(R0)}" y1="{q(R0)}" x2="{p(R1)}" y2="{q(R1)}"/>\n'
 f'<line id="chimneyTop" x1="{p(tA)}" y1="{q(tA)}" x2="{p(tB)}" y2="{q(tB)}"/>\n')
# split roofR where the chimney covers it
roof_split=(f'<line id="roofR" x1="834.5" y1="412.9" x2="{p(L1)}" y2="{q(L1)}"/>\n'
 f'<line id="roofR2" x1="{p(R1)}" y1="{q(R1)}" x2="1131.9" y2="700.9"/>')
old='<line id="roofR" x1="834.5" y1="412.9" x2="1131.9" y2="700.9"/>'
fill=(f'<polygon id="chimney" fill="#c0392b" points="{p(L0)},{q(L0)} {p(R0)},{q(R0)} '
      f'{R1[0]:.1f},{R1[1]+4:.1f} {L1[0]:.1f},{L1[1]+4:.1f}"/>')
for name in ('sketch-lines.svg','sketch-color.svg'):
    s=open(f'{src}/{name}').read()
    assert old in s
    s=s.replace(old,roof_split+'\n'+chim_lines.rstrip('\n'))
    if 'color' in name:
        s=s.replace('fill="#e2725b"','fill="#c0392b"')
        s=s.replace('<polygon id="roof" ', fill+'\n<polygon id="roof" ')  # chimney fill sits just before the roof fill; it overlaps the roof by 4 px to hide the antialias seam
    open(name,'w').write(s)
print(L0,L1,R0,R1,tA,tB)
