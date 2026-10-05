#!/usr/bin/env python3
"""Build lighthouse.mp4 from lighthouse.wav + lighthouse.lrc using ImageMagick + ffmpeg (ASS subtitles)."""
import re, subprocess, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "../../../../fixtures")
WAV = os.path.join(FIX, "lighthouse.wav")
LRC = os.path.join(FIX, "lighthouse.lrc")
W, H, FPS = 1280, 720, 30
LYRIC_OFFSET = -0.25   # round 2: every LRC timestamp (lyrics, clear, section markers) moves 0.25 s earlier
CHORUS_SCALE = 1.25    # round 2: chorus lyric lines are 25 % larger
ASSETS = os.path.join(HERE, "assets"); os.makedirs(ASSETS, exist_ok=True)

def run(cmd):
    print("+", " ".join(cmd)[:200]); subprocess.run(cmd, check=True)

dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration",
                                     "-of","csv=p=0",WAV]).decode().strip())

# ---------- parse LRC ----------
tags, events = {}, []   # events: (time, kind, text) kind in lyric/section/clear
ts_re = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
for raw in open(LRC, encoding="utf-8"):
    line = raw.strip()
    if not line: continue
    m = re.fullmatch(r"\[([a-z]+):(.*)\]", line)
    if m and not ts_re.match(line):
        tags[m.group(1)] = m.group(2).strip(); continue
    times, pos = [], 0
    while True:
        m = ts_re.match(line, pos)
        if not m: break
        times.append(max(0.0, int(m.group(1))*60 + float(m.group(2)) + LYRIC_OFFSET)); pos = m.end()
    if not times: continue
    text = line[pos:].strip()
    sec = re.fullmatch(r"\[(.+)\]", text)
    for t in times:
        if sec: events.append((t, "section", sec.group(1)))
        elif text: events.append((t, "lyric", text))
        else: events.append((t, "clear", ""))
order = {"section":0, "clear":1, "lyric":2}
events.sort(key=lambda e: (e[0], order[e[1]]))
# title card starts at 0 and ends when the first lyric appears (2.00 - 0.25 = 1.75 s)
TITLE_END = min(e[0] for e in events if e[1] == "lyric")

# Build display segments: each lyric/clear timestamp runs until the next lyric/clear timestamp (or song end)
stamps = [e for e in events if e[1] != "section"]
sections = [e for e in events if e[1] == "section"]
lyric_stamps = [e for e in stamps if e[1] == "lyric"]
def section_at(t):
    cur = None
    for s in sections:
        if s[0] <= t + 1e-6: cur = s[2]
    return cur
segs = []
for i, (t, kind, text) in enumerate(stamps):
    end = stamps[i+1][0] if i+1 < len(stamps) else dur
    nx = next((e for e in lyric_stamps if e[0] > t + 1e-6), None)
    segs.append(dict(start=t, end=end, kind=kind, text=text, next=nx[2] if nx else None,
                     next_section=section_at(nx[0]) if nx else None, section=section_at(t)))
# section-label intervals (label persists until next section label)
sec_iv = []
for i, s in enumerate(sections):
    sec_iv.append((s[0], sections[i+1][0] if i+1 < len(sections) else dur, s[2]))

def is_chorus(name): return bool(name) and "chorus" in name.lower()
glow_iv = [(s["start"], s["end"]) for s in segs if s["kind"]=="lyric" and re.search(r"\blighthouse\b", s["text"], re.I)]
chorus_iv = [(a, b) for a, b, n in sec_iv if is_chorus(n)]

# ---------- ASS subtitles ----------
def ts(t):
    cs = int(round(t*100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
def esc(s): return s.replace("{", "(").replace("}", ")")
ass = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,DejaVu Serif,104,&H00FFFFFF,&H00FFFFFF,&H00301810,&H80000000,-1,0,0,0,100,100,2,0,1,3,4,5,80,80,0,1
Style: Artist,DejaVu Sans,40,&H0090D8F0,&H0090D8F0,&H00301810,&H80000000,0,0,0,0,100,100,6,0,1,2,2,5,80,80,0,1
Style: Current,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00200C08,&HA0000000,-1,0,0,0,100,100,0,0,1,3,3,5,90,90,0,1
Style: Next,DejaVu Sans,32,&H50E8E0D8,&H50E8E0D8,&H00200C08,&HA0000000,0,1,0,0,100,100,0,0,1,2,1,8,120,120,0,1
Style: CurrentChorus,DejaVu Sans,{58*CHORUS_SCALE:g},&H00FFFFFF,&H00FFFFFF,&H00200C08,&HA0000000,-1,0,0,0,100,100,0,0,1,3,3,5,60,60,0,1
Style: NextChorus,DejaVu Sans,{32*CHORUS_SCALE:g},&H50E8E0D8,&H50E8E0D8,&H00200C08,&HA0000000,0,1,0,0,100,100,0,0,1,2,1,8,100,100,0,1
Style: Section,DejaVu Sans,26,&H00B0F0FF,&H00B0F0FF,&H00200C08,&H80000000,-1,0,0,0,100,100,3,0,1,2,1,7,40,40,32,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""]
ass.append(f"Dialogue: 1,{ts(0)},{ts(TITLE_END)},Title,,0,0,0,,{{\\pos(640,320)\\fad(300,250)}}{esc(tags.get('ti','Untitled'))}")
ass.append(f"Dialogue: 1,{ts(0)},{ts(TITLE_END)},Artist,,0,0,0,,{{\\pos(640,430)\\fad(500,250)}}{esc(tags.get('ar','')).upper()}")
for s in segs:
    if s["kind"] == "lyric":
        cs = "CurrentChorus" if is_chorus(s["section"]) else "Current"
        cy = 305 if cs == "CurrentChorus" else 320   # lift slightly so a wrapped big line clears the next line
        ass.append(f"Dialogue: 2,{ts(s['start'])},{ts(s['end'])},{cs},,0,0,0,,{{\\pos(640,{cy})\\fad(150,0)}}{esc(s['text'])}")
    if s["next"]:
        ns = "NextChorus" if is_chorus(s["next_section"]) else "Next"
        ass.append(f"Dialogue: 1,{ts(s['start'])},{ts(s['end'])},{ns},,0,0,0,,{{\\pos(640,450)\\fad(150,0)}}{esc(s['next'])}")
for a, b, n in sec_iv:
    ass.append(f"Dialogue: 3,{ts(a)},{ts(b)},Section,,0,0,0,,{esc(n.upper())}")
open(os.path.join(HERE, "lighthouse.ass"), "w", encoding="utf-8").write("\n".join(ass) + "\n")

# ---------- ImageMagick assets ----------
A = lambda n: os.path.join(ASSETS, n)
# title card: dusk navy with horizon
run(["convert","-size",f"{W}x{H}","gradient:#0b1026-#1d2b4f",
     "(","-size",f"{W}x6","xc:#f2b66a","-blur","0x3",")","-geometry","+0+560","-composite",
     "-fill","#08101f","-draw","rectangle 0,563 1280,720", A("bg_title.png")])
# verse: cold deep-sea blue/teal night with stars + dark sea
run(["convert","-size",f"{W}x{H}","gradient:#06162b-#0f4a5c",
     "(","-size",f"{W}x{H}","xc:black","+noise","Random","-channel","G","-separate","+channel",
     "-threshold","99.6%","-blur","0x0.6",")","-compose","screen","-composite",
     "-fill","#041019","-draw","rectangle 0,600 1280,720",
     "-fill","#0d2f3d","-draw","rectangle 0,600 1280,604", A("bg_verse.png")])
# chorus: warm magenta/amber sunset sky, glowing sea
run(["convert","-size",f"{W}x{H}","gradient:#2a0a3a-#c2492e",
     "(","-size",f"{W}x{H}","radial-gradient:#ffb34766-none",")","-geometry","+0+300","-compose","over","-composite",
     "-fill","#3a0f2a","-draw","rectangle 0,600 1280,720",
     "-fill","#ffb347","-draw","rectangle 0,600 1280,603", A("bg_chorus.png")])
# warm beam: a cone from the left lighthouse lamp + radial glow, with alpha
run(["convert","-size","600x600","xc:none","-channel","RGBA",
     "-fill","rgba(255,214,130,0.6)","-draw","polygon 300,300 600,235 600,365","-blur","0x8",
     "(","-size","600x600","gradient:white-black","-rotate","-90","-level","0%,55%","-alpha","copy",")",
     "-compose","DstIn","-composite",
     "(","-size","240x240","radial-gradient:rgba(255,210,120,0.9)-rgba(255,210,120,0)",")",
     "-gravity","center","-compose","over","-composite","+channel", A("beam.png")])
run(["convert","-size",f"{W}x{H}","radial-gradient:#ffb14c-#000000","-resize",f"{W}x{H}!", A("glow.png")])

# ---------- ffmpeg ----------
def between(iv): return "+".join(f"between(t,{a:.3f},{b-0.001:.3f})" for a, b in iv) or "0"
chorus_e = between(chorus_iv); glow_e = between(glow_iv)
fc = (
  f"[0:v]format=rgba[title];[1:v]format=rgba[verse];[2:v]format=rgba[chorus];"
  f"[verse][chorus]overlay=enable='{chorus_e}'[b1];"
  f"[b1][title]overlay=enable='lt(t,{TITLE_END})'[b2];"
  # glow: screen-blend warm radial wash
  f"[4:v]format=rgb24,setsar=1[g];[b2]format=rgb24[b2r];"
  f"[b2r][g]blend=all_mode=screen:all_opacity=0.30:enable='{glow_e}'[b3];"
  # sweeping beam from lamp at (170,560): rotate the cone over time
  f"[3:v]format=rgba,rotate=a='-0.35+0.30*sin(2*PI*t/3.5)':c=none:ow=600:oh=600,scale=1800:1800[beam];"
  f"[b3][beam]overlay=x=170-900:y=560-900:enable='{glow_e}':format=auto[b4];"
  # lamp dot (lighthouse silhouette) always present on top of sea
  f"[b4]drawbox=x=158:y=470:w=24:h=130:color=0x10141c@1:t=fill,"
  f"drawbox=x=164:y=548:w=12:h=12:color=0xffd37a@1:t=fill:enable='{glow_e}',"
  f"drawbox=x=164:y=548:w=12:h=12:color=0x6a5a40@1:t=fill:enable='not({glow_e})',"
  f"ass='{os.path.join(HERE,'lighthouse.ass')}',format=yuv420p[v]"
)
out = os.path.join(HERE, "lighthouse.mp4")
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-loop","1","-framerate",str(FPS),"-t",f"{dur}","-i",A("bg_title.png"),
     "-loop","1","-framerate",str(FPS),"-t",f"{dur}","-i",A("bg_verse.png"),
     "-loop","1","-framerate",str(FPS),"-t",f"{dur}","-i",A("bg_chorus.png"),
     "-loop","1","-framerate",str(FPS),"-t",f"{dur}","-i",A("beam.png"),
     "-loop","1","-framerate",str(FPS),"-t",f"{dur}","-i",A("glow.png"),
     "-i",WAV,"-filter_complex",fc,"-map","[v]","-map","5:a",
     "-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-r",str(FPS),
     "-c:a","aac","-b:a","160k","-ar","44100","-t",f"{dur}","-movflags","+faststart",out])
for s in segs: print(s)
print("chorus", chorus_iv, "glow", glow_iv)
