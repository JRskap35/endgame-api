"""Build Endgame API's PvP mode from Pride Eternal / Finnald's "Destiny 2 PvP Spreadsheet".
Usage: python3 -I pvp.py data_e.json pvp_raw.json OUT.json
data_e.json is the PvE build (enrich.py output); pvp_raw.json comes from pvp_fetch.py. OUT.json is the PvE data with a
"pvp" section added: {weapons, sets, ammo, updated}. bungie.py then fills in icons, art, exotic types and elements.

Rules (Joe's):
  * Legendary Weapons tab -> the same sections as PvE (Autos, HCs, ... ; rocket pulse rifles go in Other like Aegis's).
  * Only obtainable weapons, one entry each: "Unobtainable" versions come out, and when Pride lists a gun more than
    once only the newest release stays (see recency()). Exotics are left out (Joe's call).
  * Pride lists perks best first, so keep at most 2 barrels, 2 magazines and 3 perks in each perk column.
  * Shopping List: adds perks the Legendary tab lacks, and marks priority picks with their role.
  * Set Bonuses tab -> PvP tiers, ranks and analysis for the same 56 armor sets.
"""
import json, re, sys, collections

DATA, RAW, OUT = sys.argv[1:4]
pve = json.load(open(DATA)); raw = json.load(open(RAW))
nn = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("’", "'"))
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
CAP = {"barrel": 2, "mag": 2, "p1": 3, "p2": 3}
TYPE = {"auto rifle": "Autos", "bow": "Bows", "hand cannon": "HCs", "pulse rifle": "Pulses", "scout rifle": "Scouts",
        "sidearm": "Sidearms", "smg": "SMGs", "special gl": "BGLs", "fusion rifle": "Fusions", "glaive": "Glaives",
        "shotgun": "Shotguns", "sniper rifle": "Snipers", "rocket sidearm": "Rocket Sidearms", "trace rifle": "Traces",
        "heavy grenade launcher": "HGLs", "lfr": "LFRs", "machine gun": "LMGs", "rocket launcher": "Rockets",
        "sword": "Swords", "rocket pulse rifle": "Other"}
AMMO_OF = {ar: a for a, archs in pve["ammo"].items() for ar in archs}
report = collections.defaultdict(list)

def table(rows, key):
    """header row (the one containing `key`) -> list of {header: text} records"""
    hi = next(i for i, r in enumerate(rows) if any(c["t"] == key for c in r))
    H = [re.sub(r"\s+", " ", c["t"]).strip() for c in rows[hi]]
    out = []
    for r in rows[hi + 1:]:
        rec = {H[i]: r[i]["t"].strip() for i in range(min(len(H), len(r))) if H[i] and H[i] not in out and H[i] != "🖼️"}
        if any(rec.values()): out.append(rec)
    return out
def items(text, cap=None):
    xs = [re.sub(r"\s+", " ", x).strip(" ,") for x in re.split(r"\n|,(?![^()]*\))", text or "")]
    xs = [x for x in xs if x and x.upper() not in ("N/A", "NONE", "NONE.", "-")]
    xs = list(dict.fromkeys(xs))
    return xs[:cap] if cap else xs
def split_name(full):
    """'Adamantite (Pit of Heresy Dungeon Variant)' -> ('Adamantite', 'Pit of Heresy Dungeon')"""
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", full)
    if not m: return full.strip(), ""
    return m.group(1).strip(), re.sub(r"\s*variant\s*$", "", m.group(2), flags=re.I).strip()

# PvE lookups, to borrow a weapon's season and ammo count when Pride and Aegis list the same gun
PVE_BY = collections.defaultdict(list)
for w in pve["weapons"]: PVE_BY[nn(w["name"])].append(w)

# ---------- Shopping List ----------
shop = {}
for r in table(raw["Shopping List"], "Name"):
    name = r.get("Name", "")
    if not name or name == "Name": continue
    base, var = split_name(name)
    c = {"role": re.sub(r"\s+", " ", r.get("Role", "")).strip(), "priority": r.get("Priority", "").strip().lower(),
         "c1": r.get("Column 1", ""), "c2": r.get("Column 2", ""), "name": base, "var": var}
    shop.setdefault(nn(base), []).append(c)
def shop_for(base, var):
    cands = shop.get(nn(base)) or []
    exact = [c for c in cands if nn(c["var"]) == nn(var)]   # only the exact variant Pride listed
    return (exact or [None])[0]
def shop_perks(c):
    """Shopping List columns may be plain perk lists, or labeled: 'Barrels - A, B, or C' / 'Perks - X, Y, Z'"""
    out = {}
    for col, default in (("c1", "p1"), ("c2", "p2")):
        t = (c or {}).get(col, "")
        m = re.match(r"^\s*(barrels?|magazines?|mags?|perks?)\s*-\s*(.*)$", t, re.I | re.S)
        target, body = default, t
        if m:
            kind = m.group(1).lower(); body = m.group(2).replace(" or ", ", ")
            target = "barrel" if kind.startswith("barrel") else "mag" if kind.startswith("mag") else ("p1" if "p1" not in out else "p2")
        xs = items(body, CAP[target])
        if xs: out[target] = xs
    return out
used_shop = set()

# ---------- Legendary Weapons ----------
weapons = []; seen = collections.Counter()
for r in table(raw["Legendary Weapons"], "Name"):
    full = r.get("Name", ""); typ = re.sub(r"\s+", " ", r.get("Type", "")).strip().lower()
    if not full or full == "Name" or not typ: continue
    arch = TYPE.get(typ)
    if not arch: report["unknown weapon type (add to TYPE in pvp.py)"].append(f"{full}: {typ}"); continue
    name, var = split_name(full)
    wid = "pvp-" + slug(f"{arch} {name} {var}")
    seen[wid] += 1
    if seen[wid] > 1: wid += f"-{seen[wid]}"
    origins = [o for o in items(r.get("Origin Trait", "")) if not o.lower().startswith("none") and not o.startswith("(") and "preference" not in o.lower()]
    w = {"id": wid, "a": AMMO_OF.get(arch, "other"), "arch": arch, "name": name, "var": var, "season": "",
         "element": r.get("Affinity", "").strip() or "Kinetic", "frame": re.sub(r"\s+", " ", r.get("Frame", "")).strip(), "frameNote": "",
         "source": re.sub(r"\s+", " ", r.get("Where to get", "")).strip(), "srcX": 0, "stun": "", "stats": [],
         "up": "", "craft": r.get("Craftable", "").strip(), "slot": r.get("Slot", "").strip(),
         "barrel": items(r.get("Barrel", ""), CAP["barrel"]), "mag": items(r.get("Magazine", ""), CAP["mag"]),
         "mw": " / ".join(items(r.get("MW", ""), 2)), "p1": items(r.get("Column 1", ""), CAP["p1"]), "p2": items(r.get("Column 2", ""), CAP["p2"]),
         "origin": origins[0] if origins else "None", "oriX": 0, "notes": r.get("Role / Notes", "").strip(),
         "rank": None, "tier": r.get("Tier", "").strip().upper()[:1] or "F"}
    if len(origins) > 1: w["origin2"] = origins[1:]
    c = shop_for(name, var)
    if c:
        used_shop.add(id(c))
        for k, v in shop_perks(c).items():
            if not w[k]: w[k] = v                      # fill only what the Legendary tab left blank
        if c["role"]: w["shop"] = {"role": c["role"], "priority": c["priority"]}
    m = PVE_BY.get(nn(name))
    if m:
        pv = next((x for x in m if nn(x["var"]) == nn(var)), m[0])
        w["season"] = pv["season"]; w["stats"] = pv["stats"]
    weapons.append(w)

# ---------- obtainable, newest version only (Joe's rules) ----------
# 1. Pride marks retired versions "Unobtainable (Previously ...)" in Where to get: those come out.
# 2. One entry per weapon. When Pride lists several versions, keep the newest release. Checked against Bungie's
#    item data: the newest copies are the ones Pride labels with the current reissue (Monument of Triumph, Renegades,
#    Reclamation), with their current activity (a raid or dungeon), or with no label; "Original", "Season of ...",
#    "Episode: ...", "Pantheon", "Onslaught" and similar labels are earlier releases.
unobtainable = lambda w: bool(re.search(r"\bu\w{0,2}obtainable", w["source"].lower()))
ACTIVITY = ("raid", "dungeon", "pit of heresy", "shattered throne", "king's fall", "last wish", "deep stone crypt",
            "vow of the disciple", "garden of salvation", "crota's end", "root of nightmares", "salvation's edge",
            "spire of the watcher", "prophecy", "duality", "ghosts of the deep", "warlord's ruin", "vesper's host",
            "sundered doctrine", "grasp of avarice")
def recency(var):
    v = var.lower()
    if not v: return 50
    if any(k in v for k in ("monument of triumph", "renegades", "reclamation")): return 100
    if any(k in v for k in ACTIVITY): return 90
    for k, sc in (("edge of fate", 40), ("episode", 35), ("onslaught", 30), ("into the light", 30), ("pantheon", 30),
                  ("season of", 20), ("festival", 10), ("baroque", 15), ("original", 5), ("legendary", 5), ("forsaken", 5), ("collections", 8)):
        if k in v: return sc
    return 25
dropped_unob = [f"{w['name']}{' (' + w['var'] + ')' if w['var'] else ''}" for w in weapons if unobtainable(w)]
weapons = [w for w in weapons if not unobtainable(w)]
best = {}
for i, w in enumerate(weapons):
    k = (w["arch"], nn(w["name"]))
    if k not in best or recency(w["var"]) > recency(best[k][1]["var"]): best[k] = (i, w)
keep = {id(w) for _, w in best.values()}
dropped_old = [f"{w['name']} ({w['var'] or 'unlabeled'})" for w in weapons if id(w) not in keep]
weapons = [w for w in weapons if id(w) in keep]
print(f"Removed {len(dropped_unob)} unobtainable entries and {len(dropped_old)} older versions of weapons listed more than once")
print("  older versions removed: " + ", ".join(dropped_old))
# Exotics are left out of PvP mode (Joe's call: Pride lists perks for only two of them)

# order inside each section: tier first, then the sheet's order (Pride's sheet has no rank column), numbered for sorting
TIER = {t: i for i, t in enumerate("SABCDEF")}
order = collections.defaultdict(list)
for i, w in enumerate(weapons): order[w["a"] if w.get("exotic") else w["arch"]].append((TIER.get(w["tier"], 9), i, w))
for sec, lst in order.items():
    for n, (_, _, w) in enumerate(sorted(lst, key=lambda t: (t[0], t[1])), 1): w["rank"] = n

# ---------- Set Bonuses ----------
PVE_SET = {nn(s["name"]): s for s in pve["sets"]}
psets = collections.OrderedDict()
shop_bonus = {nn(c["name"]): c for cs in shop.values() for c in cs if re.search(r"set bonus", c["role"], re.I)}
for r in table(raw["Set Bonuses"], "Set"):
    setname = (r.get("Set", "").split("\n") or [""])[0].strip(); bonus = r.get("Bonus", "").strip()
    if not setname or not bonus: continue
    s = PVE_SET.get(nn(setname))
    if not s: report["PvP set not in Aegis's sheet"].append(setname); continue
    pcs = int(re.sub(r"\D", "", r.get("Pcs", "") or "0") or 0)
    TAGFIX = {"weapon buffs": "Weapon Buff"}
    tags = [t.strip() for t in re.split(r"/|,", r.get("Tags", "")) if t.strip()]
    tags = list(dict.fromkeys(TAGFIX.get(t.lower(), t[:1].upper() + t[1:]) for t in tags))   # one spelling per tag
    b = {"pcs": pcs, "name": bonus, "tags": tags, "trigger": r.get("Trigger", "").strip(), "effect": r.get("Effect", "").strip(),
         "desc": r.get("Description", "").strip(), "rank": int(re.sub(r"\D", "", r.get("Rank", "") or "") or 999),
         "tier": (r.get("Tier", "").strip().upper()[:1] or "F")}
    sb = shop_bonus.get(nn(bonus))
    if sb: b["tags"] = b["tags"] + ["Shopping List"]; b["shop"] = {"role": sb["role"], "priority": sb["priority"]}
    psets.setdefault(s["id"], {"id": s["id"], "bonuses": []})["bonuses"].append(b)
for v in psets.values(): v["bonuses"].sort(key=lambda b: b["pcs"])
missing_sets = [s["name"] for s in pve["sets"] if s["id"] not in psets]
if missing_sets: report["Aegis sets with no PvP rating"] += missing_sets

# ---------- status (which tabs Pride updated when) ----------
updated = {}
for r in table(raw.get("Status", []), "TAB") if raw.get("Status") else []:
    if r.get("TAB") and re.match(r"\d{4}-\d\d-\d\d", r.get("UPDATED", "")): updated[r["TAB"]] = r["UPDATED"]

ammo = {a: [ar for ar in archs if any(w["arch"] == ar and not w.get("exotic") for w in weapons)] for a, archs in pve["ammo"].items()}
pve["pvp"] = {"weapons": weapons, "sets": list(psets.values()), "ammo": ammo, "updated": updated,
              "source": "Destiny 2 PvP Spreadsheet by Pride Eternal / Finnald"}
json.dump(pve, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
leg = [w for w in weapons if not w.get("exotic")]; exo = [w for w in weapons if w.get("exotic")]
print(f"PvP: {len(leg)} legendary weapons in {len({w['arch'] for w in leg})} sections, {len(exo)} exotics, "
      f"{len(psets)} armor sets rated, {len(used_shop)} Shopping List entries used, "
      f"{sum(1 for w in weapons if w.get('shop'))} weapons marked as Shopping List picks")
for k, v in report.items(): print(f"{k} ({len(v)}): " + ", ".join(v[:30]))
# safety check: stop the build (nothing is published) if Pride's sheet came through looking broken
problems = []
if len(leg) < 450: problems.append(f"only {len(leg)} legendary weapons (expected about 700)")
if len(psets) < 40: problems.append(f"only {len(psets)} armor sets rated (expected 56)")
if problems: print("PvP sheet check FAILED: " + "; ".join(problems)); sys.exit(1)
