import base64, pathlib, subprocess
from playwright.sync_api import sync_playwright
D = pathlib.Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width':1080,'height':1656})
    pg.goto((D/'art.html').as_uri()); pg.wait_for_function('window.ART_DONE', timeout=180000)
    data = pg.evaluate("document.getElementById('c').toDataURL('image/png')")
    (D/'art.png').write_bytes(base64.b64decode(data.split(',')[1]))
    pg = b.new_page(viewport={'width':1080,'height':1656})
    pg.goto((D/'poster.html').as_uri()); pg.wait_for_load_state('networkidle'); pg.evaluate('document.fonts.ready')
    pg.pdf(path=str(D/'poster-rgb.pdf'), width='11.25in', height='17.25in', print_background=True,
           margin={'top':'0','right':'0','bottom':'0','left':'0'}, prefer_css_page_size=True)
    pg2 = b.new_page(viewport={'width':1080,'height':1656}, device_scale_factor=150/96)
    pg2.goto((D/'poster.html').as_uri()); pg2.wait_for_load_state('networkidle'); pg2.evaluate('document.fonts.ready')
    pg2.screenshot(path=str(D/'preview-full.png'), clip={'x':12,'y':12,'width':1056,'height':1632})
    b.close()
subprocess.run(['gs','-q','-dNOPAUSE','-dBATCH','-dSAFER','-sDEVICE=pdfwrite','-dCompatibilityLevel=1.6',
  '-sColorConversionStrategy=CMYK','-sProcessColorModel=DeviceCMYK',
  '-dAutoFilterColorImages=false','-dColorImageFilter=/FlateEncode','-dDownsampleColorImages=false',
  '-dEmbedAllFonts=true','-dSubsetFonts=true',
  '-sOutputFile='+str(D/'poster-print.pdf'), str(D/'poster-rgb.pdf')], check=True)
# Mark trim (inset 0.125in = 9pt) and bleed boxes for the printer
import pypdf
r = pypdf.PdfReader(str(D/'poster-print.pdf')); w = pypdf.PdfWriter(clone_from=r)
pgx = w.pages[0]
pgx.trimbox = pypdf.generic.RectangleObject([9, 9, 801, 1233])
pgx.bleedbox = pypdf.generic.RectangleObject([0, 0, 810, 1242])
pgx.cropbox = pypdf.generic.RectangleObject([0, 0, 810, 1242])
pgx.artbox = pypdf.generic.RectangleObject([9, 9, 801, 1233])
w.write(str(D/'poster-print.pdf'))
subprocess.run(['convert',str(D/'preview-full.png'),'-resize','1650x2550!','-colorspace','sRGB','-type','TrueColor','-define','png:color-type=2',str(D/'poster-preview.png')],check=True)
(D/'preview-full.png').unlink()
(D/'poster-rgb.pdf').unlink()
