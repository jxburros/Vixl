import sys
from vixl.project import Project
from vixl.proxy import render_preview
from PIL import Image
S='/tmp/claude-0/-home-user-Vixl/73e014c0-2ea7-5149-9d8d-1f9a9dfd57db/scratchpad/'
fs=sys.argv[1:]
T=330
s=Image.new('RGB',(2*T+10, len(fs)*(T+6)),'white')
for i,f in enumerate(fs):
    p=Project.load('friends-and-flames/'+f+'.vixl')
    s.paste(p.render().convert('RGB').resize((T,T),Image.LANCZOS),(0,i*(T+6)))
    s.paste(render_preview(p,T,T).convert('RGB'),(T+10,i*(T+6)))
s.save(S+'pairs.png')
