import pdfplumber, hashlib, json, io, base64, re, sys
from PIL import Image
SRC = sys.argv[1]; OUT = sys.argv[2]
pdf = pdfplumber.open(SRC)
STUN = {'237789c3':'Barrier','c7ddf5c1':'Unstoppable','ffda4a4b':'Overload'}

def img_uri(im, q=82):
    st = im['stream']; w, h = st.get('Width'), st.get('Height')
    flt = st.get('Filter'); flt = str(flt)
    if 'DCT' in flt:
        pim = Image.open(io.BytesIO(st.get_rawdata())).convert('RGB')
    else:
        data = st.get_data(); cs = str(st.get('ColorSpace'))
        n = len(data)//(w*h)
        mode = {1:'L',3:'RGB',4:'CMYK'}.get(n,'RGB')
        pim = Image.frombytes(mode,(w,h),data[:w*h*n]).convert('RGB')
    b = io.BytesIO(); pim.save(b,'WEBP',quality=q,method=6)
    return 'data:image/webp;base64,'+base64.b64encode(b.getvalue()).decode()

def section_of(p):
    words = p.extract_words()
    top = min(w['top'] for w in words)
    return ' '.join(w['text'] for w in words if abs(w['top']-top)<3 and w['x0']>500)

def hlines(p):
    L = [l for l in p.lines if abs(l['top']-l['bottom'])<1.5]
    L += [r for r in p.rects if r['height']<1.2 and r['width']>4]
    return L

def cell_lines(p, bbox, strikes):
    """return list of text lines in a cell, struck lines prefixed with ~, italics flagged with ^"""
    x0,t,x1,b = bbox
    chars = [c for c in p.chars if c['x0']>=x0-0.5 and c['x1']<=x1+0.5 and c['top']>=t-0.5 and c['bottom']<=b+0.5]
    rows = []
    for c in sorted(chars, key=lambda c:(round(c['top']),c['x0'])):
        for r in rows:
            if abs(r['top']-c['top'])<2: r['ch'].append(c); break
        else: rows.append({'top':c['top'],'ch':[c]})
    out = []
    for r in sorted(rows,key=lambda r:r['top']):
        ch = sorted(r['ch'],key=lambda c:c['x0'])
        txt = ''
        for i,c in enumerate(ch):
            if i and c['x0']-ch[i-1]['x1']>c['size']*0.18 and not txt.endswith(' '): txt += ' '
            txt += c['text']
        txt = re.sub(r'\s+',' ',txt).strip()
        if not txt: continue
        lx0, lx1 = ch[0]['x0'], ch[-1]['x1']; ltop=min(c['top'] for c in ch); lbot=max(c['bottom'] for c in ch)
        struck = any(ltop < s['top'] < lbot and min(lx1,s['x1'])-max(lx0,s['x0']) > 0.5*(lx1-lx0) for s in strikes)
        italic = all('Italic' in c['fontname'] or 'Oblique' in c['fontname'] for c in ch)
        bold = all('Bold' in c['fontname'] for c in ch)
        out.append({'t':txt,'s':struck,'i':italic,'b':bold})
    return out

def fill_at(p, x, y):
    best=None
    for r in p.rects:
        if r['x0']<=x<=r['x1'] and r['top']<=y<=r['bottom'] and r.get('fill'):
            col=r.get('non_stroking_color')
            if col is None: continue
            area=r['width']*r['height']
            if best is None or area<best[0]: best=(area,col)
    if not best: return None
    c=best[1]
    if isinstance(c,(list,tuple)) and len(c)==3: return '#%02x%02x%02x'%tuple(int(round(v*255)) for v in c)
    if isinstance(c,(list,tuple)) and len(c)==1: v=int(round(c[0]*255)); return '#%02x%02x%02x'%(v,v,v)
    return None

HCACHE={}
weapons=[]; sets=[]; stun_icons={}; tier_cols={}; notes={}
for pi,p in enumerate(pdf.pages):
    sec = section_of(p)
    if sec=='Notes':
        txt=p.extract_text()
        for m in re.finditer(r'\[(\d+)\]\s*(.+?)(?=\n\[\d+\]|\Z)',txt,re.S):
            notes[m.group(1)]=' · '.join(x.strip() for x in m.group(2).strip().split('\n') if x.strip())
        continue
    tbs = p.find_tables()
    if not tbs: continue
    tb = tbs[0]
    strikes = hlines(p)
    rows = tb.rows
    # header row = the one containing 'Name' or 'Set'
    hdr_i = None
    for i,r in enumerate(rows):
        txts=[((p.crop(c).extract_text() or '').split('\n')[-1].strip() if c else '') for c in r.cells]
        if 'Name' in txts or 'Set' in txts: hdr_i=i; header=txts; break
    imgs = p.images
    for r in rows[hdr_i+1:]:
        cells = r.cells
        if not any(cells): continue
        rt, rb = r.bbox[1], r.bbox[3]
        rec = {}
        for h,c in zip(header,cells):
            if c is None or h in ('🖼',''): continue
            rec[h] = cell_lines(p, c, strikes)
            if h in ('Ammo','Tier','Charge Impact','Shield'):
                rec[h+'__fill'] = fill_at(p,(c[0]+c[2])/2,(c[1]+c[3])/2)
        if not any(rec.get(k) for k in ('Name','Set')): continue
        icon=None; stun=[]
        for im in imgs:
            cy=(im['top']+im['bottom'])/2
            if not (rt<=cy<=rb): continue
            w=im['stream'].get('Width')
            if im['x0']<80 and im['width']>15: icon=img_uri(im)
            elif w==250:
                oid=im['stream'].objid
                if oid not in HCACHE: HCACHE[oid]=hashlib.md5(im['stream'].get_rawdata()).hexdigest()[:8]
                hsh=HCACHE[oid]
                stun.append(STUN.get(hsh,'?'))
                if hsh not in stun_icons:
                    st=im['stream']; data=st.get_data(); sm=st.get('SMask')
                    base=Image.frombytes('RGB',(250,250),data[:250*250*3]).convert('L')
                    alpha=Image.frombytes('L',(250,250),sm.resolve().get_data()[:250*250]) if sm else Image.new('L',(250,250),255)
                    # white glyph with original alpha*darkness
                    from PIL import ImageChops
                    a=ImageChops.multiply(alpha, ImageChops.invert(base))
                    out=Image.new('RGBA',(250,250),(255,255,255,0)); out.putalpha(a); out=out.resize((64,64),Image.LANCZOS)
                    b=io.BytesIO(); out.save(b,'PNG',optimize=True)
                    stun_icons[STUN.get(hsh,hsh)]='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
        rec['__icon']=icon; rec['__stun']=stun; rec['__page']=pi+1; rec['__sec']=sec
        (sets if 'Set' in header else weapons).append(rec)

json.dump({'weapons':weapons,'sets':sets,'stun_icons':stun_icons,'notes':notes},open(OUT,'w'))
print(len(weapons),len(sets),list(stun_icons),notes)
