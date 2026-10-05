import cv2,numpy as np
im=cv2.imread('/home/user/Vixl/evals/tool-comparison/fixtures/sketch.jpg')
src=np.float32([[0,34],[1973,0],[1999,1465],[26,1499]])
W=2000; H=round(2000*1465/1973)
dst=np.float32([[0,0],[W,0],[W,H],[0,H]])
M=cv2.getPerspectiveTransform(src,dst)
w=cv2.warpPerspective(im,M,(W,H),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
g=cv2.cvtColor(w,cv2.COLOR_BGR2GRAY).astype(np.float32)
bg=cv2.morphologyEx(g,cv2.MORPH_CLOSE,np.ones((25,25),np.uint8))
bg=cv2.GaussianBlur(bg,(0,0),15)
n=np.clip(g/bg*255,0,255).astype(np.uint8)
cv2.imwrite('norm.png',n)
b=(n<150).astype(np.uint8)*255
# remove speckles
nl,lab,st,_=cv2.connectedComponentsWithStats(b)
keep=np.zeros_like(b)
for i in range(1,nl):
    if st[i,4]>=40: keep[lab==i]=255
# trim near borders
keep[:15,:]=0;keep[-15:,:]=0;keep[:,:15]=0;keep[:,-15:]=0
cv2.imwrite('bin.png',255-keep)
print(W,H)
