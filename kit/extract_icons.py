"""Pull frame, perk and origin trait icons from the full sheet PDF.
Usage: python3 -I extract_icons.py FULL.pdf OUT.json
FULL.pdf is the unfiltered export (fetch.py --full). Output: {"frames": {"Auto rifle|Adaptive": uri}, "perks": {name: uri}, "origins": {name: uri}}"""
import pdfplumber, io, base64, json, re, sys
import numpy as np
from PIL import Image
SRC, OUT = sys.argv[1], sys.argv[2]
pdf = pdfplumber.open(SRC)

def raw_image(im):
    st = im["stream"]; w, h = st.get("Width"), st.get("Height")
    if "DCT" in str(st.get("Filter")):
        return Image.open(io.BytesIO(st.get_rawdata())).convert("RGB")
    data = st.get_data(); n = len(data) // (w * h)
    return Image.frombytes({1: "L", 3: "RGB", 4: "CMYK"}.get(n, "RGB"), (w, h), data[:w*h*n]).convert("RGB")

def smask_of(im):
    sm = im["stream"].get("SMask")
    if not sm: return None
    sm = sm.resolve(); w, h = sm.get("Width"), sm.get("Height")
    return np.asarray(Image.frombytes("L", (w, h), sm.get_data()[:w*h])).astype(float)

def glyph(pim, mode, mask=None):
    """Return a white glyph on transparent. mode 'light' = white glyph on black, 'tile' = black glyph inside a white tile."""
    a = np.asarray(pim.convert("L")).astype(float)
    if mode == "tile":
        tile = a > 128
        # keep the tile's interior and cut the glyph out: alpha = white tile minus black glyph
        from scipy import ndimage
        filled = ndimage.binary_fill_holes(tile)
        alpha = np.where(filled, a / 255.0, 0)  # tile white, glyph dark -> glyph becomes a hole
    elif mask is not None and mask.shape == a.shape and mask.min() < 128:
        # the shape lives in the transparency layer: use it directly, cutting out any dark detail drawn inside
        inside = a[mask > 128]
        bright = inside.size and inside.mean() > 128
        alpha = (mask / 255.0) * (np.clip((a - 40) / 175.0, 0, 1) if bright else 1.0)
    else:
        if a.mean() > 128: a = 255 - a   # a few icons are drawn dark on light; flip them
        alpha = np.clip((a - 40) / 175.0, 0, 1)
    if mode != "tile":
        # trim each glyph to its own shape and scale it to the same box, so icons drawn with different
        # amounts of padding on the sheet all appear the same size
        ys, xs = np.where(alpha > 0.12)
        if ys.size:
            alpha = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            h, w = alpha.shape; side = int(max(h, w) / 0.9)
            box = np.zeros((side, side)); oy, ox = (side - h) // 2, (side - w) // 2
            box[oy:oy + h, ox:ox + w] = alpha; alpha = box
    rgba = np.zeros((*alpha.shape, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = (alpha * 255).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA").resize((48, 48), Image.LANCZOS)
    b = io.BytesIO(); out.save(b, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def tab_of(p):
    ws = p.extract_words()
    if not ws: return ""
    top = min(w["top"] for w in ws)
    return " ".join(w["text"] for w in ws if abs(w["top"] - top) < 3 and w["x0"] > 500)

def plain_lines(p, bbox):
    x0, t, x1, b = bbox
    txt = p.crop((x0 + .5, t + .5, x1 - .5, b - .5)).extract_text() or ""
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    # italic sub labels (e.g. "Heavy Bolts") are on later lines; keep both
    return lines

out = {"frames": {}, "perks": {}, "origins": {}}
for p in pdf.pages:
    tab = tab_of(p)
    if tab not in ("Archetypes", "Perks", "Origin Traits"): continue
    tb = p.find_tables()[0]
    hdr = None
    for j, r in enumerate(tb.rows):
        txts = [((p.crop(c).extract_text() or "").split("\n")[-1].strip() if c else "") for c in r.cells]
        if "Name" in txts or "Weapon" in txts: hdr = (j, txts); break
    j, header = hdr
    for r in tb.rows[j + 1:]:
        cells = dict(zip(header, r.cells))
        rt, rb = r.bbox[1], r.bbox[3]
        imgs = [im for im in p.images if rt <= (im["top"] + im["bottom"]) / 2 <= rb]
        if tab == "Archetypes":
            if not cells.get("Weapon") or not cells.get("Frame"): continue
            wt = plain_lines(p, cells["Weapon"]); fr = plain_lines(p, cells["Frame"])
            if not wt or not fr: continue
            icon = [im for im in imgs if im["x0"] < 58 and im["width"] > 8]
            if not icon: continue
            key = " ".join(wt) + "|" + fr[0] + ("|" + " ".join(fr[1:]) if len(fr) > 1 else "")
            out["frames"][key] = glyph(raw_image(icon[0]), "tile")
        else:
            if not cells.get("Name"): continue
            nm = " ".join(plain_lines(p, cells["Name"]))
            icon = [im for im in imgs if im["x0"] < 66 and im["width"] > 10]
            if not nm or not icon: continue
            out["perks" if tab == "Perks" else "origins"][nm] = glyph(raw_image(icon[0]), "light", smask_of(icon[0]))
json.dump(out, open(OUT, "w"))
print({k: len(v) for k, v in out.items()})
