import cv2,numpy as np,json,math
b=(cv2.imread('bin.png',0)<128).astype(np.uint8)
ys,xs=np.nonzero(b); P=np.stack([xs,ys],1).astype(float)
H,W=b.shape
# rough guides (hand-placed, refined by fitting to ink)
L={
'roofL':[(565,710),(843,420)],'roofR':[(838,418),(1133,700)],
'wallTop':[(600,697),(1103,690)],'wallL':[(595,715),(602,1155)],'wallR':[(1103,690),(1112,1158)],
'wL_t':[(658,770),(767,767)],'wL_b':[(658,880),(771,877)],'wL_l':[(658,770),(658,880)],'wL_r':[(767,767),(771,877)],
'wL_v':[(711,770),(716,877)],'wL_h':[(660,826),(768,823)],
'wR_t':[(962,766),(1071,762)],'wR_b':[(962,873),(1077,873)],'wR_l':[(962,766),(962,873)],'wR_r':[(1071,762),(1077,873)],
'wR_v':[(1016,765),(1018,873)],'wR_h':[(968,820),(1070,818)],
'door_t':[(805,930),(921,927)],'door_l':[(800,940),(805,1150)],'door_r':[(921,927),(925,1145)],
'trunkL':[(1408,925),(1413,1140)],'trunkR':[(1450,922),(1452,1140)],
'ray1':[(1534,75),(1537,145)],'ray2':[(1370,152),(1428,200)],'ray3':[(1722,145),(1672,195)],'ray4':[(1315,300),(1388,300)],
'ray5':[(1716,297),(1786,292)],'ray6':[(1428,418),(1380,470)],'ray7':[(1667,422),(1718,472)],'ray8':[(1551,472),(1554,545)],
}
def fit(a,c,band,ext):
    a=np.array(a,float);c=np.array(c,float);d=c-a;Ln=np.linalg.norm(d);u=d/Ln;n=np.array([-u[1],u[0]])
    t=(P-a)@u; s=(P-a)@n
    m=(t>-ext)&(t<Ln+ext)&(np.abs(s)<band)
    Q=P[m]; mu=Q.mean(0)
    vx,vy,_,_=cv2.fitLine(Q.astype(np.float32),cv2.DIST_HUBER,0,0.01,0.01).ravel()
    u2=np.array([vx,vy]); 
    if u2@u<0:u2=-u2
    tt=(Q-mu)@u2
    tc=((a+c)/2-mu)@u2
    occ=set(np.round(tt).astype(int))
    lo=hi=int(round(tc))
    while any((lo-g) in occ for g in range(1,5)): lo-=1
    while any((hi+g) in occ for g in range(1,5)): hi+=1
    return mu+lo*u2, mu+hi*u2
R={}
for k,(a,c) in L.items():
    p,q=fit(a,c,14,25); p,q=fit(p,q,6,20)
    # pull ends in by half stroke (ink extent includes round cap)
    u=(q-p)/np.linalg.norm(q-p); R[k]=[p+2.5*u,q-2.5*u]
def inter(A,B):
    p,q=A;r,s=B;d1=q-p;d2=s-r;den=d1[0]*d2[1]-d1[1]*d2[0]
    if abs(den)<1e-9:return None
    t=((r-p)[0]*d2[1]-(r-p)[1]*d2[0])/den;return p+t*d1
def segdist(E,B):
    r,s=B;d=s-r;t=np.clip((E-r)@d/(d@d),0,1);return np.linalg.norm(E-(r+t*d))
# gap closing: extend an endpoint to meet a nearby line (never trim)
log=[];R0={k:[v[0].copy(),v[1].copy()] for k,v in R.items()};upd=[]
for k in R0:
    for i in (0,1):
        E=R0[k][i];O=R0[k][1-i];u=(E-O)/np.linalg.norm(E-O)
        if any(segdist(E,R0[j])<4 for j in R0 if j!=k): continue   # already joined
        best=None
        for j in R0:
            if j==k:continue
            d2=R0[j][1]-R0[j][0];cosang=abs(u@d2)/np.linalg.norm(d2)
            if cosang>0.85:continue
            X=inter(R0[k],R0[j])
            if X is None:continue
            g=(X-E)@u
            if 0.5<g<22 and segdist(X,R0[j])<22 and (best is None or g<best[0]): best=(g,X,j)
        if best: upd.append((k,i,best[1])); log.append((k,i,best[2],round(best[0],1)))
for k,i,X in upd: R[k][i]=X
for l in log:print('gap closed',l)
# sun circle: algebraic fit on ink in annulus
cx,cy,r0=1550,308,118
dd=np.hypot(P[:,0]-cx,P[:,1]-cy);Q=P[np.abs(dd-r0)<14]
A=np.c_[2*Q,np.ones(len(Q))];bb=(Q**2).sum(1);sol=np.linalg.lstsq(A,bb,rcond=None)[0]
cx,cy=sol[0],sol[1];r=math.sqrt(sol[2]+cx*cx+cy*cy)
print('sun',cx,cy,r)
# tree canopy: polar profile around centre
tx,ty=1435,790
ang=np.arctan2(P[:,1]-ty,P[:,0]-tx);rad=np.hypot(P[:,0]-tx,P[:,1]-ty)
m=(rad>60)&(rad<180)&(P[:,1]<935)
# exclude trunk interior pixels
m&=~((P[:,1]>915)&(P[:,0]>1400)&(P[:,0]<1460)&(rad>140))
N=720;prof=np.full(N,np.nan)
bins=((ang[m]+np.pi)/(2*np.pi)*N).astype(int)%N
for i in range(N):
    v=rad[m][bins==i]
    if len(v):prof[i]=np.median(v)
ok=~np.isnan(prof);idx=np.arange(N)
gaps=idx[~ok];print('canopy empty bins',len(gaps))
prof=np.interp(idx,np.r_[idx[ok]-N,idx[ok],idx[ok]+N],np.r_[prof[ok],prof[ok],prof[ok]])
# light circular smoothing
k=np.ones(9)/9;prof=np.convolve(np.r_[prof[-4:],prof,prof[:4]],k,'valid')
th=(idx+0.5)/N*2*np.pi-np.pi
canopy=[(tx+prof[i]*math.cos(th[i]),ty+prof[i]*math.sin(th[i])) for i in range(0,N,3)]
# ground: column-wise centre of ink in band
gx=[];gy=[];prev=None
for x in range(140,1880,2):
    col=b[1100:1190,x];runs=[];y=0
    while y<len(col):
        if col[y]:
            y0=y
            while y<len(col) and col[y]: y+=1
            runs.append((y0,y))
        y+=1
    runs=[r for r in runs if r[1]-r[0]<=10]
    if not runs: continue
    c=[1100+(r[0]+r[1]-1)/2 for r in runs]
    yy=min(c,key=lambda v:abs(v-prev)) if prev is not None else c[0]
    if prev is not None and abs(yy-prev)>6: continue
    gx.append(x);gy.append(yy);prev=yy
gy=np.convolve(np.r_[[gy[0]]*7,gy,[gy[-1]]*7],np.ones(15)/15,'valid')
gx=gx[::2];gy=gy[::2]
ground=list(zip(gx,gy.tolist()))
out={'lines':{k:[list(map(float,R[k][0])),list(map(float,R[k][1]))] for k in R},
 'sun':[cx,cy,r],'canopy':canopy,'ground':ground,'W':W,'H':H}
json.dump(out,open('geom.json','w'))
