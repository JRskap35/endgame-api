"""Attach frame, perk and origin trait icon ids to the weapon data.
Usage: python3 -I enrich.py data.json trait_icons.json OUT_data.json OUT_ticons.json
Weapons keep their text fields untouched (filters and search use the text); icons are added as w.fi, w.oi and
w.pi (perk name -> icon id). Anything without a match on the sheet simply shows as text."""
import json, re, sys, hashlib
data = json.load(open(sys.argv[1])); ti = json.load(open(sys.argv[2]))
TYPE = {"Autos":"Auto rifle","Bows":"Bow","HCs":"Hand cannon","Pulses":"Pulse rifle","Scouts":"Scout rifle","Sidearms":"Sidearm",
        "SMGs":"SMG","BGLs":"Grenade launcher - breech","Fusions":"Fusion rifle","Glaives":"Glaive","Shotguns":"Shotgun",
        "Snipers":"Sniper rifle","Rocket Sidearms":"Sidearm","Traces":"Trace rifle","HGLs":"Grenade launcher - drum",
        "LFRs":"Linear fusion rifle","LMGs":"Machine gun","Rockets":"Rocket launcher","Swords":"Sword","Other":None}
def nf(s):
    s = re.sub(r"\[\d+\]", "", s).lower()
    s = s.replace("rapid-fire", "rapid").replace("rapid fire", "rapid")
    return re.sub(r"[^a-z]", "", s)
def nn(s): return re.sub(r"[^a-z0-9]", "", s.lower().replace("’", "'"))
icons = {}
def iid(uri):
    k = hashlib.md5(uri.encode()).hexdigest()[:10]; icons[k] = uri; return k
# frames: by (type, frame) with the first line, first two lines joined, and frame-only fallback
by_tf, by_f = {}, {}
for key, uri in ti["frames"].items():
    parts = key.split("|"); t = re.sub(r"\s*\[\d+\]", "", parts[0]).strip()
    cands = [parts[1]] + ([parts[1] + " " + parts[2]] if len(parts) > 2 else [])
    for c in cands:
        by_tf.setdefault((t, nf(c)), uri); by_f.setdefault(nf(c), uri)
perks = {nn(k): v for k, v in ti["perks"].items()}
origins = {nn(k): v for k, v in ti["origins"].items()}
miss_f, miss_p, miss_o, hit_p, tot_p = set(), set(), set(), 0, 0
for w in data["weapons"]:
    t = TYPE.get(w["arch"]); f = nf(w["frame"])
    uri = by_tf.get((t, f)) if t else None
    uri = uri or by_f.get(f)
    if uri: w["fi"] = iid(uri)
    elif w["frame"]: miss_f.add(f"{w['arch']}: {w['frame']}")
    o = origins.get(nn(w["origin"]))
    if o: w["oi"] = iid(o)
    elif w["origin"]: miss_o.add(w["origin"])
    pi = {}
    for col in ("p1", "p2"):
        for x in w[col]:
            name = x[0] if isinstance(x, list) else x
            tot_p += 1
            u = perks.get(nn(name))
            if u: pi[name] = iid(u); hit_p += 1
            else: miss_p.add(name)
    if pi: w["pi"] = pi
json.dump(data, open(sys.argv[3], "w"), separators=(",", ":"), ensure_ascii=False)
json.dump(icons, open(sys.argv[4], "w"), separators=(",", ":"))
n = len(data["weapons"])
print(f"frames {sum('fi' in w for w in data['weapons'])}/{sum(bool(w['frame']) for w in data['weapons'])}  origins {sum('oi' in w for w in data['weapons'])}/{n}  perk slots {hit_p}/{tot_p}  unique icons {len(icons)}")
print("frames without icon:", sorted(miss_f))
print("origins without icon:", sorted(miss_o))
print("perks without icon:", sorted(miss_p))
