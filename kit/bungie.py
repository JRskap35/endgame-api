"""Swap the sheet's icons for Bungie's official Destiny 2 icons.
Usage: python3 -I bungie.py data_e.json icons.json ticons.json elements.json OUT_DIR [CACHE_DIR]
Inputs are the sheet build (enrich.py output, sheet icons, sheet trait icons, element icons).
Writes OUT_DIR/data.json, OUT_DIR/icons.json, OUT_DIR/ticons.json, OUT_DIR/elements.json, OUT_DIR/report.txt.

Bungie's public manifest needs no API key; images come from https://www.bungie.net.
  weapon images    : the weapon's icon with its season watermark
  frames           : the weapon's own intrinsic (frame) socket
  perks/barrels/mags/origin traits : the weapon's own sockets first, then any Bungie plug with that name
  masterwork       : Bungie's "Masterworked: <stat>" icons
  energy           : DestinyDamageTypeDefinition      stun : DestinyBreakerTypeDefinition
  armor sets       : 2 and 4 piece bonus icons (DestinySandboxPerkDefinition); the set's own icon uses
                     whichever bonus icon the sheet uses for that set
Anything Bungie doesn't have keeps the sheet's icon, and is listed in report.txt.
Armor stat icons, the logo and the background are Joe's and are not touched here."""
import json, sys, os, re, io, base64, subprocess, collections, hashlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

DATA, ICONS, TICONS, ELEMS, OUT = sys.argv[1:6]
CACHE = sys.argv[6] if len(sys.argv) > 6 else "bungie_cache"
os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.join(CACHE, "img"), exist_ok=True)
BASE = "https://www.bungie.net"

def curl(url, path):
    subprocess.run(["curl", "-sS", "--fail", "--compressed", "--retry", "3", "--retry-delay", "5", "--max-time", "600", "-o", path, url], check=True)

# ---------- manifest ----------
mpath = os.path.join(CACHE, "manifest.json")
curl(BASE + "/Platform/Destiny2/Manifest/", mpath)
man = json.load(open(mpath))["Response"]
ver = man["version"]; paths = man["jsonWorldComponentContentPaths"]["en"]
def comp(k):
    p = os.path.join(CACHE, f"{k}-{ver}.json")
    if not os.path.exists(p):
        for old in os.listdir(CACHE):
            if old.startswith(k + "-"): os.remove(os.path.join(CACHE, old))
        curl(BASE + paths[k], p)
    return json.load(open(p))
items = comp("DestinyInventoryItemDefinition"); plugsets = comp("DestinyPlugSetDefinition")
sets = comp("DestinyEquipableItemSetDefinition"); sperks = comp("DestinySandboxPerkDefinition")
dmg = comp("DestinyDamageTypeDefinition"); brk = comp("DestinyBreakerTypeDefinition")

data = json.load(open(DATA)); icons = json.load(open(ICONS)); ticons = json.load(open(TICONS)); elems = json.load(open(ELEMS))
nn = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("’", "'"))
pname = lambda x: x[0] if isinstance(x, list) else x

# ---------- lookups ----------
WEAP = collections.defaultdict(list); PLUG = {}
for h, it in items.items():
    dp = it.get("displayProperties", {}); n = dp.get("name")
    if not n or not dp.get("icon"): continue
    if it.get("itemType") == 3: WEAP[nn(n)].append(it)
    elif it.get("plug"):
        k = nn(n)
        cat = (it["plug"].get("plugCategoryIdentifier") or "")
        # prefer real weapon perk categories over cosmetics or enhanced copies that share a name
        score = (cat in ("frames", "barrels", "magazines", "intrinsics", "origins", "guards", "blades", "batteries", "arrows", "stocks", "scopes", "tubes", "grips", "hafts", "bowstrings") or "origin" in cat,
                 "enhanced" not in cat)
        if k not in PLUG or score > PLUG[k][1]: PLUG[k] = (dp["icon"], score)
def weapon_def(w):
    c = WEAP.get(nn(w["name"]))
    if not c: return None
    return sorted(c, key=lambda it: (bool(it.get("screenshot")), bool(it.get("iconWatermark")), it.get("index", 0)), reverse=True)[0]
def socket_plugs(it):
    out = {}; intrinsic = None
    for se in it.get("sockets", {}).get("socketEntries", []):
        hs = [se.get("singleInitialItemHash")]
        for k in ("randomizedPlugSetHash", "reusablePlugSetHash"):
            if se.get(k): hs += [x["plugItemHash"] for x in plugsets.get(str(se[k]), {}).get("reusablePlugItems", [])]
        hs += [x["plugItemHash"] for x in se.get("reusablePlugItems", [])]
        for h in hs:
            d = items.get(str(h))
            if not d or not d.get("displayProperties", {}).get("name") or not d["displayProperties"].get("icon"): continue
            out.setdefault(nn(d["displayProperties"]["name"]), d["displayProperties"]["icon"])
            if intrinsic is None and (d.get("plug") or {}).get("plugCategoryIdentifier") == "intrinsics" and h == se.get("singleInitialItemHash"):
                intrinsic = d["displayProperties"]["icon"]
    return out, intrinsic

# ---------- image download (cached by file name; Bungie icon paths are content hashed) ----------
need = set()
plan = {"weapons": {}, "frames": {}, "perks": {}, "origins": {}}
report = collections.defaultdict(list)
for w in data["weapons"]:
    it = weapon_def(w)
    if not it: report["weapon not on Bungie"].append(f"{w['arch']}: {w['name']}"); continue
    plan["weapons"][w["id"]] = (it["displayProperties"]["icon"], it.get("iconWatermark", ""))
    # full weapon artwork for the image popup, newest copy first; Bungie is sometimes slow to upload art for reissues,
    # so older copies are kept as fallbacks (shots.py and the website try them in order)
    shots = [x["screenshot"] for x in sorted(WEAP[nn(w["name"])], key=lambda x: x.get("index", 0), reverse=True) if x.get("screenshot")]
    if shots: w["shot"] = list(dict.fromkeys(shots))[:3]
    else: report["weapon without full image"].append(w["name"])
    need.update(p for p in plan["weapons"][w["id"]] if p)
    own, intrinsic = socket_plugs(it)
    if w["frame"]:
        p = intrinsic or own.get(nn(w["frame"] + " frame")) or own.get(nn(w["frame"])) or (PLUG.get(nn(w["frame"] + " frame")) or PLUG.get(nn(w["frame"])) or (None,))[0]
        if p: plan["frames"][w["id"]] = p; need.add(p)
        else: report["frame without Bungie icon"].append(f"{w['name']}: {w['frame']}")
    for slot in ("p1", "p2", "barrel", "mag"):
        for x in w[slot]:
            n = pname(x); p = own.get(nn(n)) or (PLUG.get(nn(n)) or (None,))[0]
            if p: plan["perks"][(w["id"], n)] = p; need.add(p)
            else: report[("perk" if slot[0] == "p" else slot) + " without Bungie icon"].append(n)
    if w["origin"] and w["origin"] != "None":
        p = own.get(nn(w["origin"])) or (PLUG.get(nn(w["origin"])) or (None,))[0]
        if p: plan["origins"][w["id"]] = p; need.add(p)
        else: report["origin trait without Bungie icon"].append(w["origin"])
MWN = {"Reload": "Reload Speed"}
MW = {}
for it in items.values():
    n = it.get("displayProperties", {}).get("name", "")
    if n.startswith("Masterworked: ") and it["displayProperties"].get("icon"): MW[n[14:]] = it["displayProperties"]["icon"]
for w in data["weapons"]:
    for st in filter(None, (x.strip() for x in (w["mw"] or "").split("/"))):
        p = MW.get(MWN.get(st, st))
        if p: need.add(p)
        else: report["masterwork without Bungie icon"].append(st)
DMG = {d["displayProperties"]["name"].lower(): d["displayProperties"].get("icon") for d in dmg.values() if d["displayProperties"].get("icon")}
BRK = {"Barrier": "Shield Piercing", "Overload": "Disruption", "Unstoppable": "Stagger"}
BRKI = {d["displayProperties"]["name"]: d["displayProperties"].get("icon") for d in brk.values()}
need.update(v for v in DMG.values() if v); need.update(v for v in BRKI.values() if v)
SETS = {nn(s["displayProperties"]["name"]).removesuffix("set"): s for s in sets.values()}
ALIAS = {"uncageddeviants": "waywardpsyche"}   # the sheet's name for Bungie's "Wayward Psyche Set"
setplan = {}
for s in data["sets"]:
    k = nn(s["name"]); bs = SETS.get(ALIAS.get(k, k))
    if not bs: report["armor set not on Bungie"].append(s["name"]); continue
    bon = {}
    for p in bs.get("setPerks", []):
        sp = sperks.get(str(p["sandboxPerkHash"]), {}).get("displayProperties", {})
        if sp.get("icon"): bon[p["requiredSetCount"]] = sp["icon"]; need.add(sp["icon"])
    setplan[s["id"]] = bon

def fetch(p):
    f = os.path.join(CACHE, "img", os.path.basename(p))
    if not os.path.exists(f) or os.path.getsize(f) == 0:
        try: curl(BASE + p, f)
        except Exception: return p, None
    return p, f
with ThreadPoolExecutor(12) as ex: files = dict(ex.map(fetch, sorted(need)))
for p, f in files.items():
    if not f: report["image download failed"].append(p)

# ---------- image encoding ----------
def uri(im, fmt="PNG", **kw):
    b = io.BytesIO(); im.save(b, fmt, **kw); return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()
def load(p):
    f = files.get(p); return Image.open(f).convert("RGBA") if f else None
def glyph(im, size=56):
    """white glyph on transparent, trimmed and scaled to the same box so every icon looks the same size"""
    a = np.asarray(im).astype(float); alpha = a[..., 3] / 255.0
    lum = a[..., :3].mean(axis=2) / 255.0
    if alpha.min() > 0.95:   # opaque icon: use brightness as the shape
        alpha = np.clip((lum - 0.15) / 0.75, 0, 1)
    ys, xs = np.where(alpha > 0.12)
    if ys.size:
        alpha = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]; lumc = lum[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = alpha.shape; side = int(max(h, w) / 0.9); box = np.zeros((side, side)); oy, ox = (side - h) // 2, (side - w) // 2
        box[oy:oy + h, ox:ox + w] = alpha; alpha = box
    rgba = np.zeros((*alpha.shape, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return uri(Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS), optimize=True)
def keep_color(im, size=64):
    a = np.asarray(im)[..., 3]; ys, xs = np.where(a > 20)
    if ys.size: im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = int(max(im.size) / 0.9); c = Image.new("RGBA", (s, s), (0, 0, 0, 0)); c.paste(im, ((s - im.size[0]) // 2, (s - im.size[1]) // 2), im)
    return uri(c.resize((size, size), Image.LANCZOS), optimize=True)
tid = lambda u: "b" + hashlib.md5(u.encode()).hexdigest()[:10]
glyph_cache = {}
def gl(p, tile=False):
    """tile=True keeps Bungie's square artwork as is (masterwork icons are full color tiles)"""
    if (p, tile) not in glyph_cache:
        im = load(p); glyph_cache[(p, tile)] = None
        if im is not None:
            u = uri(im.resize((56, 56), Image.LANCZOS), optimize=True) if tile else glyph(im)
            k = tid(u); ticons[k] = u; glyph_cache[(p, tile)] = k
    return glyph_cache[(p, tile)]

done = collections.Counter()
sheet_pi = {w["id"]: dict(w.get("pi") or {}) for w in data["weapons"]}
for w in data["weapons"]:
    if w["id"] in plan["weapons"]:
        ip, wp = plan["weapons"][w["id"]]; im = load(ip)
        if im is not None:
            im = im.resize((96, 96), Image.LANCZOS); wm = load(wp) if wp else None
            if wm is not None: im.alpha_composite(wm.resize((96, 96), Image.LANCZOS))
            icons["w"][w["id"]] = uri(im.convert("RGB"), "WEBP", quality=84, method=6); done["weapon images"] += 1
    if w["id"] in plan["frames"]:
        k = gl(plan["frames"][w["id"]])
        if k: w["fi"] = k; done["frames"] += 1
    if w["id"] in plan["origins"]:
        k = gl(plan["origins"][w["id"]])
        if k: w["oi"] = k; done["origin traits"] += 1
    w["pi"] = {}   # sheet perk icons are replaced outright; anything Bungie lacks falls back below
    for slot in ("p1", "p2", "barrel", "mag"):
        for x in w[slot]:
            n = pname(x); p = plan["perks"].get((w["id"], n))
            k = gl(p) if p else None
            if k: w["pi"][n] = k; done["perk slots" if slot[0] == "p" else slot + " icons"] += 1
            elif slot[0] == "p" and n in sheet_pi.get(w["id"], {}): w["pi"][n] = sheet_pi[w["id"]][n]
    mwi = {}
    for st in filter(None, (x.strip() for x in (w["mw"] or "").split("/"))):
        p = MW.get(MWN.get(st, st)); k = gl(p, True) if p else None
        if k: mwi[st] = k; done["masterwork icons"] += 1
    if mwi: w["mwi"] = mwi
for name, key in (("kinetic", "kinetic"), ("arc", "arc"), ("solar", "solar"), ("void", "void"), ("stasis", "stasis"), ("strand", "strand")):
    p = DMG.get(name); im = load(p) if p else None
    if im is not None: elems[key] = keep_color(im); done["energy icons"] += 1
for ours, theirs in BRK.items():
    p = BRKI.get(theirs); im = load(p) if p else None
    if im is not None: data["stun"][ours] = glyph(im, 64); done["stun icons"] += 1

def vec(im):
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255)); bg.alpha_composite(im)
    return np.asarray(bg.convert("L").resize((32, 32))).astype(float).ravel()
for s in data["sets"]:
    bon = setplan.get(s["id"]) or {}
    for b in s["bonuses"]:
        p = bon.get(b["pcs"]); k = gl(p) if p else None
        if k: b["bi"] = k; done["set bonus icons"] += 1
    # the set's own icon: whichever Bungie bonus icon the sheet's set icon looks like
    if bon:
        try:
            sheet = Image.open(io.BytesIO(base64.b64decode(icons["s"][s["id"]].split(",")[1]))).convert("RGBA"); v = vec(sheet)
            pick = min(bon.items(), key=lambda kv: np.abs(vec(load(kv[1])) - v).mean() if load(kv[1]) is not None else 1e9)[1]
        except Exception:
            pick = bon.get(4) or next(iter(bon.values()))
        im = load(pick)
        if im is not None: icons["s"][s["id"]] = glyph(im, 64); done["set icons"] += 1

# drop sheet icons nothing points at any more
used = set()
for w in data["weapons"]:
    used.update(filter(None, [w.get("fi"), w.get("oi")])); used.update((w.get("pi") or {}).values()); used.update((w.get("mwi") or {}).values())
for s in data["sets"]: used.update(b.get("bi") for b in s["bonuses"] if b.get("bi"))
ticons = {k: v for k, v in ticons.items() if k in used}
json.dump(data, open(os.path.join(OUT, "data.json"), "w"), separators=(",", ":"), ensure_ascii=False)
json.dump(icons, open(os.path.join(OUT, "icons.json"), "w"), separators=(",", ":"))
json.dump(ticons, open(os.path.join(OUT, "ticons.json"), "w"), separators=(",", ":"))
json.dump(elems, open(os.path.join(OUT, "elements.json"), "w"), separators=(",", ":"))
slots = sum(len(w["p1"]) + len(w["p2"]) for w in data["weapons"])
lines = [f"Bungie manifest {ver}",
         f"weapon images {done['weapon images']}/{len(data['weapons'])}, frames {done['frames']}/{sum(1 for w in data['weapons'] if w['frame'])}, "
         f"perk slots {done['perk slots']}/{slots}, barrels {done['barrel icons']}/{sum(len(w['barrel']) for w in data['weapons'])}, "
         f"mags {done['mag icons']}/{sum(len(w['mag']) for w in data['weapons'])}, masterwork {done['masterwork icons']}, origin traits {done['origin traits']}, energy {done['energy icons']}/6, stun {done['stun icons']}/3, "
         f"set icons {done['set icons']}/{len(data['sets'])}, set bonus icons {done['set bonus icons']}/{sum(len(s['bonuses']) for s in data['sets'])}"]
for k, v in report.items():
    lines.append(f"{k} ({len(set(v))}, these keep the sheet's icon): " + ", ".join(sorted(set(v))[:40]))
open(os.path.join(OUT, "report.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
