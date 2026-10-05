import json,numpy as np
g=json.load(open('geom.json'));W,H=g['W'],g['H'];Lx={k:[np.array(p) for p in v] for k,v in g['lines'].items()}
SW=5.5
def inter(A,B):
    p,q=A;r,s=B;d1=q-p;d2=s-r;den=d1[0]*d2[1]-d1[1]*d2[0]
    t=((r-p)[0]*d2[1]-(r-p)[1]*d2[0])/den;return p+t*d1
gr=np.array(g['ground'])
def gy(x): return float(np.interp(x,gr[:,0],gr[:,1]))
def atY(line,yfun):
    p,q=line;
    y=p[1]
    for _ in range(20):
        t=(y-p[1])/(q[1]-p[1]);x=p[0]+t*(q[0]-p[0]);y=yfun(x)
    return np.array([x,y])
f=lambda pts:' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)
cx,cy,r=g['sun']
lines=[]
for k,(p,q) in Lx.items():
    lines.append(f'<line id="{k}" x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
lines.append(f'<circle id="sun" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"/>')
lines.append(f'<polygon id="canopy" points="{f(g["canopy"])}" fill="none"/>')
lines.append(f'<polyline id="ground" points="{f(gr)}" fill="none"/>')
LG=f'<g id="lines" inkscape:groupmode="layer" inkscape:label="Lines" stroke="#000" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round" fill="none">\n'+'\n'.join(lines)+'\n</g>'
hdr=f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
open('sketch-lines.svg','w').write(hdr+f'<rect id="paper" width="{W}" height="{H}" fill="#fff"/>\n'+LG+'\n</svg>\n')
# fills
gext=[(0,gr[0,1])]+gr.tolist()+[(W,gr[-1,1])]
sky=[(0,0),(W,0)]+gext[::-1]
ground=gext+[(W,H),(0,H)]
TL=inter(Lx['wallTop'],Lx['wallL']);TR=inter(Lx['wallTop'],Lx['wallR'])
BL=atY(Lx['wallL'],gy);BR=atY(Lx['wallR'],gy)
mid=[(x,y) for x,y in gr if BL[0]<x<BR[0]]
walls=[TL,TR,BR]+mid[::-1]+[BL]
apex=inter(Lx['roofL'],Lx['roofR'])
roof=[apex,inter(Lx['roofR'],Lx['wallTop']),inter(Lx['roofL'],Lx['wallTop'])]
def quad(p):
    t,b,l,r_=[Lx[p+s] for s in ('_t','_b','_l','_r')]
    return [inter(t,l),inter(t,r_),inter(b,r_),inter(b,l)]
dTL=inter(Lx['door_t'],Lx['door_l']);dTR=inter(Lx['door_t'],Lx['door_r'])
dBL=atY(Lx['door_l'],gy);dBR=atY(Lx['door_r'],gy)
door=[dTL,dTR,dBR]+[(x,y) for x,y in gr if dBL[0]<x<dBR[0]][::-1]+[dBL]
import cv2
cp=np.array(g['canopy'],np.float32)
for k in ('trunkL','trunkR'):
    p,q=Lx[k]
    for t in np.linspace(0,1,400):
        X=p+t*(q-p)
        if cv2.pointPolygonTest(cp,(float(X[0]),float(X[1])),True)<-1: break
    Lx[k][0]=p+max(t-1/400,0)*(q-p)
tTL=Lx['trunkL'][0];tTR=Lx['trunkR'][0]
trunk=[tTL,tTR,atY(Lx['trunkR'],gy),atY(Lx['trunkL'],gy)]
fills=f'''<g id="color" inkscape:groupmode="layer" inkscape:label="Color" stroke="none">
<polygon id="sky" fill="#d9ecf2" points="{f(sky)}"/>
<polygon id="sea-foam" fill="#a8d5c8" points="{f(ground)}"/>
<polygon id="walls" fill="#f7f1e5" points="{f(walls)}"/>
<polygon id="roof" fill="#e2725b" points="{f(roof)}"/>
<polygon id="door" fill="#14263b" points="{f(door)}"/>
<polygon id="windowL" fill="#14263b" points="{f(quad('wL'))}"/>
<polygon id="windowR" fill="#14263b" points="{f(quad('wR'))}"/>
<circle id="sunfill" fill="#f2a541" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>
<polygon id="trunk" fill="#7a5236" points="{f(trunk)}"/>
<polygon id="canopyfill" fill="#5a8f5a" points="{f(g['canopy'])}"/>
</g>'''
lines=[f'<line id="{k}" x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>' for k,(p,q) in Lx.items()]+lines[len(Lx):]
LG=f'<g id="lines" inkscape:groupmode="layer" inkscape:label="Lines" stroke="#000" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round" fill="none">\n'+'\n'.join(lines)+'\n</g>'
open('sketch-lines.svg','w').write(hdr+f'<rect id="paper" width="{W}" height="{H}" fill="#fff"/>\n'+LG+'\n</svg>\n')
open('sketch-color.svg','w').write(hdr+fills+'\n'+LG+'\n</svg>\n')
