"""Full size weapon images for the Claude build's image popup.
Usage: python3 -I shots.py data.json OUT_DIR [CACHE_DIR]
Reads each weapon's Bungie screenshot paths (w["shot"], newest first, set by bungie.py), downloads it, and writes
OUT_DIR/shots/<section>.json = {weapon id: webp data URI}, one file per weapon section, 1280px wide.
The Claude artifact can't load images from bungie.net, so these files are published next to the page
(Artifact publish with files={"shots/<section>.json": ...}) and the page loads one section at a time.
The website build doesn't need this step: it loads the images straight from bungie.net."""
import json, sys, os, io, re, base64, subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

DATA, OUT = sys.argv[1:3]
CACHE = sys.argv[3] if len(sys.argv) > 3 else "bungie_cache"
os.makedirs(os.path.join(OUT, "shots"), exist_ok=True); os.makedirs(os.path.join(CACHE, "shots"), exist_ok=True)
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
data = json.load(open(DATA))
# both modes; a gun listed in both shares one image (bungie.py sets w["sh"] = [file, weapon id] to the first copy)
allw = data["weapons"] + (data.get("pvp") or {}).get("weapons", [])
ws = [w for w in allw if w.get("shot") and (not w.get("sh") or w["sh"][1] == w["id"])]

def get(path):
    """download once per image (some weapons share artwork); write to a temp name so a cut off download never sticks"""
    src = os.path.join(CACHE, "shots", os.path.basename(path))
    for _ in range(2):
        if not os.path.exists(src) or os.path.getsize(src) == 0:
            tmp = src + ".part"
            if subprocess.run(["curl", "-s", "--fail", "--retry", "3", "--retry-delay", "5", "--max-time", "120", "-o", tmp, "https://www.bungie.net" + path]).returncode: continue
            os.replace(tmp, src)
        try:
            im = Image.open(src).convert("RGB")
        except Exception:
            os.remove(src); continue
        if im.width > 1280: im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
        b = io.BytesIO(); im.save(b, "WEBP", quality=74, method=6)
        return path, "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    return path, None

def first(paths):
    for p in paths:
        if p not in done: done[p] = get(p)[1]
        if done[p]: return done[p]
done = {}
with ThreadPoolExecutor(12) as ex: done.update(ex.map(get, sorted({w["shot"][0] for w in ws})))   # newest copies in parallel
shards, missing = {}, []
for w in ws:
    u = first(w["shot"])   # falls back to older copies one by one when the newest has no art yet
    if u: shards.setdefault(w["sh"][0] if w.get("sh") else slug(w["arch"]), {})[w["id"]] = u
    else: missing.append(w["name"])
total = 0
for k, v in shards.items():
    p = os.path.join(OUT, "shots", k + ".json"); json.dump(v, open(p, "w"), separators=(",", ":")); total += os.path.getsize(p)
print(f"full images {sum(len(v) for v in shards.values())} unique (for {sum(1 for w in allw if w.get('shot'))} of {len(allw)} weapons) in {len(shards)} files, {total/1e6:.1f} MB"
      + (f"; failed: {', '.join(missing)}" if missing else ""))
