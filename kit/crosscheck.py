"""PvP perk cross check. Pride's sheet is the baseline; Bungie's roll pools, Hugo's WeaponStat Chart and the Destiny Data
Compendium win wherever they disagree with it. Runs after pvp.py and before bungie.py, every build.
Usage: python3 -I crosscheck.py data_ep.json hugo.json CACHE_DIR OUT.json REPORT.txt      apply the rules, then audit
       python3 -I crosscheck.py --check data.json hugo.json CACHE_DIR                   audit a finished build only

The rules (each one is applied, then the whole result is audited again, and the build stops if anything still breaks them):
  1. Rollable   Every barrel, magazine and perk listed for a PvP weapon must roll on the current version of that weapon in
                Bungie's manifest. Spellings follow Bungie. A perk listed under the wrong column moves to the column it rolls
                in. Anything that cannot roll is removed. Weapons whose only Bungie copy has fixed rolls are left as listed.
  2. Fastest    For primaries Hugo's chart covers (autos, hand cannons, pulses, scouts, sidearms, SMGs), every perk column
                that has a perk which lowers the time to kill (TTK) on its first activation must list one that reaches the
                fastest such TTK. TTK math is Hugo's: his frame damage and fire delay (WeaponData), his perk multipliers
                (Reference) and his health pool. A perk only counts when the Compendium says a duel can switch it on: a
                weapon kill, a kill reload, a combat timer, or always on (not ammo pickups, melee hits, elemental pickups,
                3 targets, supers only, and so on). Precision Instrument uses the Compendium's per stack numbers.
                If no listed perk reaches it, the fastest one is added (one Pride's notes mention first, otherwise the
                first in the game's column order). A full column (3 perks, the PvP cap) has its last perk replaced.
  3. Notes      TTK numbers in Pride's notes ("1.00 -> 0.59") are rewritten to Hugo's numbers where they disagree by
                0.02 s or more: the starting TTK always, and the result when every perk named in that claim can be
                modelled from Hugo's data and gives one answer.
  5. Perk order  In each perk column the listed perk with the fastest TTK goes first; ties keep Pride's order.
  4. Tier list  Sections Hugo covers are re-tiered and numbered #1, #2... by each weapon's finished TTK (fastest TTK
                its final perks reach on first activation, or its starting TTK). Equal TTKs keep Pride's order. Pride's number
                of S, A, B... per section stays as the template, filled fastest first. Other sections keep Pride's tiers.
Every change is listed in REPORT.txt; w["ttk"] carries the finished TTK for the weapon popup and w["pr"] Pride's own
tier and rank (used only by the audit). If Hugo's sheet or the Compendium changes layout so the TTK model no longer matches Hugo's own chart, the
build stops instead of guessing."""
import json, sys, os, re, math, subprocess, collections, difflib

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if a != "--check"]
DATA_IN, HUGO, CACHE = ARGS[:3]
OUT, REPORT = (ARGS[3:5] + [None, None])[:2]
os.makedirs(CACHE, exist_ok=True)
CAP = {"barrel": 2, "mag": 2, "p1": 3, "p2": 3}       # same caps as pvp.py
EPS = 0.02                                             # TTK numbers closer than this agree
nn = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("’", "'"))
pname = lambda x: x[0] if isinstance(x, list) else x
problems = []

# ---------- Bungie manifest (same cache layout as bungie.py, so nothing downloads twice) ----------
BASE = "https://www.bungie.net"
def curl(url, path):
    subprocess.run(["curl", "-sS", "--fail", "--compressed", "--retry", "3", "--retry-delay", "5", "--max-time", "600", "-o", path, url], check=True)
mpath = os.path.join(CACHE, "manifest.json")
curl(BASE + "/Platform/Destiny2/Manifest/", mpath)
man = json.load(open(mpath))["Response"]; ver = man["version"]; paths = man["jsonWorldComponentContentPaths"]["en"]
def comp(k):
    p = os.path.join(CACHE, f"{k}-{ver}.json")
    if not os.path.exists(p):
        for old in os.listdir(CACHE):
            if old.startswith(k + "-"): os.remove(os.path.join(CACHE, old))
        curl(BASE + paths[k], p)
    return json.load(open(p))
items = comp("DestinyInventoryItemDefinition"); plugsets = comp("DestinyPlugSetDefinition")

WEAP = collections.defaultdict(list)
for it in items.values():
    n = it.get("displayProperties", {}).get("name")
    if n and it.get("itemType") == 3: WEAP[nn(n)].append(it)
WEAPKEYS = list(WEAP)

def close(key, pool, cutoff=0.86):
    """spelling slips: closest name, a unique prefix ("Blunt Execution"), or a name with extra words after it ("Headseeker (???)")"""
    if key and key in pool: return key
    if not key or len(key) < 5: return None
    m = difflib.get_close_matches(key, pool, n=1, cutoff=cutoff)
    if m: return m[0]
    pre = [k for k in pool if k.startswith(key)]
    if len(pre) == 1 and len(key) >= 6: return pre[0]
    inside = sorted((k for k in pool if len(k) >= 8 and key.startswith(k)), key=len, reverse=True)
    return inside[0] if inside else None

def columns(it):
    """the weapon's sockets in game order: (plug category, [plug names]), enhanced copies left out. A socket's fixed plug
    counts too (sword guards, some launcher magazines are fixed)"""
    out = []
    for se in it.get("sockets", {}).get("socketEntries", []):
        hs = [se["singleInitialItemHash"]] if se.get("singleInitialItemHash") else []
        hs += [x["plugItemHash"] for x in se.get("reusablePlugItems", [])]
        for k in ("randomizedPlugSetHash", "reusablePlugSetHash"):
            if se.get(k): hs += [x["plugItemHash"] for x in plugsets.get(str(se[k]), {}).get("reusablePlugItems", [])]
        names, cat = [], None
        for h in hs:
            p = items.get(str(h))
            if not p or not p.get("plug"): continue
            n = p["displayProperties"].get("name", "")
            if not n or "enhanced" in (p.get("itemTypeDisplayName") or "").lower(): continue
            cat = cat or p["plug"].get("plugCategoryIdentifier", ""); names.append(n)
        if names: out.append((cat, list(dict.fromkeys(names))))
    return out

PARTS = {"arrows", "barrels", "batteries", "blades", "bolts", "bowstrings", "grips", "guards", "hafts", "magazines", "magazines_gl",
         "rails", "scopes", "stocks", "tubes"}
part = lambda cat: cat in PARTS or (cat or "").startswith("v950.new.sword")   # barrel and magazine style sockets only

def rollable(w):
    """the weapon's random roll copies on Bungie, newest first. Returns
    (newest copy: [trait column 1, trait column 2], every copy together: [column 1, column 2], every other random plug).
    A listed perk is kept when any random roll copy has it; perks added for TTK come from the newest copy."""
    c = WEAP.get(nn(w["name"]))
    if not c:
        k = close(nn(w["name"]), WEAPKEYS, 0.8); c = WEAP.get(k) if k else None
    if not c: return None
    copies = []
    for it in sorted(c, key=lambda it: (bool(it.get("screenshot")), bool(it.get("iconWatermark")), it.get("index", 0)), reverse=True):
        cols = columns(it)
        traits = [n for cat, n in cols if cat == "frames"]
        if len(traits) >= 2 and all(len(t) >= 3 for t in traits[:2]): copies.append((traits[:2], [x for cat, n in cols if part(cat) for x in n]))
    if not copies: return None
    union = [list(dict.fromkeys(p for t, _ in copies for p in t[i])) for i in (0, 1)]
    other = list(dict.fromkeys(x for _, o in copies for x in o))
    return copies[0][0], union, other

# ---------- Hugo's model ----------
H = json.load(open(HUGO))
num = lambda x, d=0.0: float(x.replace(",", "")) if x and re.fullmatch(r"-?[\d.,]+", x.strip()) else d
FR = {r[0]: dict(zip(H["data_head"], r)) for r in H["data"]}
HP = next((num(c) for c in (H["chart"][0] if H["chart"] else []) if re.fullmatch(r"\d{3}(\.\d+)?", c or "") and 150 <= num(c) <= 400), 230.0)

TR = {}   # perk -> {variant: {stack: (fire delay, body, head, charge)}}
for t in H["ref"]:
    if t[1] not in ("Trait", "Trait, Intrinsic", "Intrinsic, Trait") and t[2] != "Perk": continue
    if t[2] in ("Exotic", "Artefact"): continue
    n = t[0]; m = re.search(r"\s+x(\d+)$", n); st = int(m.group(1)) if m else 1; n = re.sub(r"\s+x\d+$", "", n)
    if n.endswith("+"): continue                                   # enhanced versions; Bungie pools list the base perk
    m = re.search(r"\s*\((.*)\)$", n); var = m.group(1) if m else ""; n = re.sub(r"\s*\(.*\)$", "", n)
    TR.setdefault(n, {}).setdefault(var, {})[st] = (num(t[3], 1), num(t[7], 1), num(t[8], 1), num(t[6], 1))
TRKEYS = {nn(k): k for k in TR}
HEAT = {nn(t[0]): (num(t[7], 1), num(t[8], 1)) for t in H["ref"] if t[2] == "Heat"}   # Overclocked / Accelerated Heatsink
PERKS = {nn(k): v for k, v in H["perks"].items()}                # Compendium descriptions

def times(m, n, fr=1.0):
    sd = num(m["shot delay"]) * fr; bd = num(m["burst delay"]); spb = int(num(m["shots per burst"], 1) or 1)
    t = 0.0
    for i in range(1, n): t += (bd if i % spb else sd) if spb > 1 else sd
    return t
def ttk(m, body=1.0, head=1.0, fr=1.0, shot=None):
    """Hugo's optimal TTK in seconds (30 frames a second) and the shot pattern, e.g. (0.6, '5h0b').
    shot(i) gives a damage bonus that changes shot by shot (Precision Instrument ramps up, Magnificent Howl buffs only
    as many shots as it has stacks); those fights are counted all precision, the fastest way to kill"""
    b = num(m["body damage"]) * body; h = num(m["crit damage"]) * head
    if b <= 0 or h <= 0: return None
    if shot:
        tot, n = 0.0, 0
        while tot < HP - 1e-9 and n < 80: tot += h * (1 + shot(n)); n += 1
        hc = n
    else:
        n = math.ceil(HP / h - 1e-9); hc = n
        while hc > 0 and (hc - 1) * h + (n - hc + 1) * b >= HP - 1e-9: hc -= 1
    return round(times(m, n, fr) / 30, 3), f"{hc}h{n - hc}b"

HITSCAN = {"Auto", "Hand Cannon", "Pulse", "Scout", "Sidearm", "SMG"}
def selftest():
    """our math has to reproduce Hugo's own chart for the plain frames, or his sheet changed and we stop"""
    ok = tot = 0
    for t in H["chart"]:
        if t[0] not in HITSCAN: continue          # bows and fusions charge, which this model leaves out
        if (t[6] and nn(t[6]) not in HEAT and t[6] != "(base)") or t[7] or not re.fullmatch(r"\d+\.\d+", t[12] or ""): continue
        k = next((k for k, m in FR.items() if m["type"] == t[0] and m["frame"] == t[1].split(" / ")[0]
                  and abs(num(m["body damage"]) - num(t[2])) < 0.05), None)
        b, h = HEAT.get(nn(t[6]), (1, 1))
        r = k and ttk(FR[k], b, h)
        if not r: continue
        tot += 1; ok += abs(r[0] - num(t[12])) < EPS
    return ok, tot

TYPE = {"Autos": "Auto", "HCs": "Hand Cannon", "Pulses": "Pulse", "Scouts": "Scout", "Sidearms": "Sidearm", "SMGs": "SMG"}
def frame_key(w):
    typ = TYPE.get(w["arch"])
    if not typ: return None, None
    f = w["frame"]
    f = {"Rapid-Fire": "Rapid Fire", "Support Frame (Healing)": "Support", "Legacy PR-55": "Lightweight",
         "Together Forever (Adaptive 300RPM)": "Adaptive", "MIDA Synergy (Lightweight SMG)": "Lightweight"}.get(f, f)
    if f.startswith("Balanced"): f = "Balanced Heat"
    if f.startswith("Dynamic"): f = "Dynamic Heat"
    if f == "Lightweight" and typ in ("Hand Cannon", "Auto"): f = {"Hand Cannon": "Adaptive", "Auto": "Rapid Fire"}[typ]   # Hugo's chart groups these
    ammo = "s" if "special" in w["frame"].lower() else "p"
    k = f"{typ}_{ammo}_{f}"
    return typ, (k if k in FR else None)

def model(w):
    """Hugo's frame row for the weapon, with its listed heatsink magazine applied the way his chart does"""
    typ, fk = frame_key(w)
    if not fk: return typ, None
    m = dict(FR[fk])
    mags = [nn(pname(x)) for x in w.get("mag", [])]
    hs = next((HEAT[k] for k in mags if k in HEAT), None)
    if hs:
        m["body damage"] = str(num(m["body damage"]) * hs[0]); m["crit damage"] = str(num(m["crit damage"]) * hs[1])
    return typ, m

PER_SHOT = {nn("Magnificent Howl")}   # Compendium: "Firing consumes a stack of Magnificent Howl per shot"
OVERRIDES = {}                        # perks whose damage follows the Compendium's PvP number instead of Hugo's

def pvp_pct(perk):
    """the Compendium's PvP damage number, written in [brackets] after the PvE one ("30% ↑33% [10% ↑11%] increased damage")"""
    d = compendium(perk) or ""
    m = re.search(r"\d+(?:\.\d+)?%\s*(?:↑\s*\d+(?:\.\d+)?%\s*)?\[(\d+(?:\.\d+)?)%[^\]]*\]\s*increased damage", d, re.I)
    return float(m.group(1)) / 100 if m else None

def variant(perk, typ, slot):
    k = TRKEYS.get(nn(perk)) or TRKEYS.get(close(nn(perk), list(TRKEYS), 0.9) or "")
    if not k: return None
    v = TR[k]; out = None
    for var, stacks in v.items():
        words = [x.strip() for x in re.split(r"[/,]", var)] if var else []
        if var and (typ in words or "Primary" in words or (var == "Kinetic" and slot == "Kinetic")): out = stacks; break
    out = out or v.get("")
    if out and list(out) == [1]:
        p = pvp_pct(perk); fr, b, h, ch = out[1]
        if p is not None and b > 0 and abs(b - (1 + p)) > 0.011 and b == h:   # Hugo and the Compendium disagree: the Compendium's PvP value wins
            OVERRIDES[k] = (b, 1 + p); out = {1: (fr, 1 + p, 1 + p, ch)}
    return out

def compendium(perk):
    return PERKS.get(nn(perk)) or PERKS.get(close(nn(perk), list(PERKS), 0.9) or "")

def duel_ready(perk):
    """can a duel switch this perk on? read from the Compendium's trigger text (the part before the first colon)"""
    d = compendium(perk)
    if not d: return False
    trig = d.split(":")[0].lower()
    if "kill" in trig: return True
    if trig.startswith("after having maintained a state of dealing or receiving damage"): return True
    return (trig.startswith("while ads") or trig.startswith("passively")) and "combatant" not in d.lower() and "super" not in d.lower()

def pi_ramp():
    d = compendium("Precision Instrument") or ""
    m = re.search(r"((?:\d+(?:\.\d+)?%\s*\|\s*)+\d+(?:\.\d+)?%)\s*Increased Precision Damage", d)
    return [0.0] + [float(x) / 100 for x in re.findall(r"(\d+(?:\.\d+)?)%", m.group(1))] if m else None
PI = pi_ramp()

def first_ttk(perk, m, typ, slot, w, stack=None):
    """TTK with the perk on its first activation (x1, or a given stack); None if Hugo/Compendium can't model it"""
    if perk in ("Explosive Payload", "Timed Payload"):
        k = f"{m['type']}_{m['ammo']}_{m['frame']} {perk}"
        r = FR.get(k) and ttk(FR[k]); return r[0] if r else None
    if nn(perk) == nn("Precision Instrument"):
        return ttk(m, shot=lambda i: PI[min(i, len(PI) - 1)])[0] if PI else None
    v = variant(perk, typ, slot)
    if not v: return None
    st = stack or 1
    if nn(perk) in PER_SHOT:      # one buffed shot per stack, then normal shots
        fr, b, h, ch = v[min(v)]
        r = ttk(m, shot=lambda i: (h - 1) if i < st else 0.0); return r[0] if r else None
    if st not in v: return None
    fr, b, h, ch = v[st]
    r = ttk(m, b, h, fr * ch)    # on these primaries Hugo's charge column scales the fire delay (hand cannon Adagio)
    return r[0] if r else None

# ---------- Pride's note claims ----------
ABBR = {"swash": "Swashbuckler", "moa": "Master of Arms", "kc": "Kill Clip", "tricorn": "Golden Tricorn", "mkc": "Multikill Clip",
        "aj": "Adrenaline Junkie", "adren junkie": "Adrenaline Junkie", "pa": "Paracausal Affinity", "para aff": "Paracausal Affinity",
        "pi": "Precision Instrument", "bo": "Binary Orbit", "mag howl": "Magnificent Howl", "dm": "Desperate Measures",
        "ele honing": "Elemental Honing", "ele hone": "Elemental Honing"}
ARROW = r"(?:->|→)"
def claim(text, m, typ, slot, w):
    """the one TTK every perk in a claim like "Kill Clip, Binary Orbit, or Swash x3" gives, or None if any part can't be modelled"""
    text = re.sub(r"(?i)^.*?\bvia\b", "", text).strip(" :=")
    vals = set()
    for it in re.split(r",\s*|\s+or\s+|\s*/\s*", text, flags=re.I):
        it = it.strip(" .:=")
        if not it: continue
        if re.search(r"\+|&|\band\b|weapon|surge|stat|overclock|radiant|frostee|bakris|light shift|ornament", it, re.I): return None
        s = re.match(r"(.+?)\s*x(\d+)$", it, re.I)
        name, st = (s.group(1).strip(), int(s.group(2))) if s else (it, None)
        name = ABBR.get(name.lower(), name)
        t = first_ttk(name, m, typ, slot, w, st)
        if t is None: return None
        vals.add(round(t, 2))
    return vals.pop() if len(vals) == 1 else None

def note_edits(w, m, typ):
    """TTK numbers in the notes that disagree with Hugo: (line, start, end, new text, change log line).
    A claimed result is only rewritten when every perk named can be modelled and Hugo still shows a speedup; a claim
    Hugo shows no speedup for usually leans on something his chart leaves out (the Weapons stat, exotic armor), so it stays."""
    out = []; base = ttk(m)[0]; slot = w.get("slot", "")
    for li, line in enumerate((w.get("notes") or "").split("\n")):
        for mm in re.finditer(rf"(\d\.\d\d?)\s*{ARROW}\s*(\d\.\d\d?)", line):
            a, b = float(mm.group(1)), float(mm.group(2))
            if base <= b + EPS:
                if abs(a - base) >= EPS:
                    out.append((li, mm.start(), mm.end(), f"{base:.2f} (already the starting TTK in Hugo's data)",
                                f"Notes: {a:.2f}s to {b:.2f}s is the starting TTK ({base:.2f}s) in Hugo's data"))
                continue
            v = claim(line[:mm.start()], m, typ, slot, w)
            if v is not None and v < base - EPS and abs(v - b) >= EPS:
                label = re.sub(r"(?i)^.*?\bvia\b|ttk shift|neutral", "", line[:mm.start()]).strip(" :=")
                out.append((li, mm.start(2), mm.end(2), f"{v:.2f}", f"Notes: {label} gives {v:.2f}s in Hugo's data, not {b:.2f}s"))
            if abs(a - base) >= EPS:
                out.append((li, mm.start(1), mm.end(1), f"{base:.2f}", f"Notes: starting TTK is {base:.2f}s in Hugo's data, not {a:.2f}s"))
        mm = re.match(r"\s*(.*?)\s*=>\s*(\d\.\d\d?)", line)
        if mm and not re.search(ARROW, line):
            v = claim(mm.group(1), m, typ, slot, w); b = float(mm.group(2))
            if v is not None and v < base - EPS and abs(v - b) >= EPS:
                out.append((li, mm.start(2), mm.end(2), f"{v:.2f}", f"Notes: {mm.group(1).strip(' :=')} gives {v:.2f}s in Hugo's data, not {b:.2f}s"))
    return out

# ---------- the rules ----------
def fix(w, pool, log):
    newest, union, other = pool
    tk = [{nn(n): n for n in col} for col in union]
    new = [[], []]
    for ci, key in enumerate(("p1", "p2")):
        for x in w.get(key, []):
            n = pname(x)
            k = close(nn(n), list(tk[ci]))           # the column Pride lists it in comes first
            col = ci
            if not k:
                col = 1 - ci; k = close(nn(n), list(tk[col]))
            if not k: log.append(f"Removed {n}: it does not roll on this weapon right now"); continue
            real = tk[col][k]
            if any(nn(pname(y)) == k for y in new[col]): continue
            if col != ci: log.append(f"Moved {real} to Perk {col + 1}, the column it rolls in")
            new[col].append([real] if isinstance(x, list) else real)
    for ci, key in enumerate(("p1", "p2")):
        if len(new[ci]) > CAP[key]:
            for x in new[ci][CAP[key]:]: log.append(f"Removed {pname(x)}: Perk {ci + 1} already lists {CAP[key]}")
            new[ci] = new[ci][:CAP[key]]
        w[key] = new[ci]
    ok = {nn(n): n for n in other}
    for key in ("barrel", "mag"):
        keep = []
        for x in w.get(key, []):
            n = pname(x); k = close(nn(n), list(ok))
            if not k: log.append(f"Removed {n}: it does not roll on this weapon right now"); continue
            keep.append([ok[k]] if isinstance(x, list) else ok[k])
        w[key] = keep

    typ, m = model(w)
    if not m: return
    base = ttk(m)
    if not base: return
    traits = newest
    slot = w.get("slot", ""); notes = nn(w.get("notes"))
    for ci, key in enumerate(("p1", "p2")):
        shifts = {}
        for p in traits[ci]:
            if p not in ("Explosive Payload", "Timed Payload") and nn(p) != nn("Precision Instrument") and not duel_ready(p): continue
            t = first_ttk(p, m, typ, slot, w)
            if t is not None and t < base[0] - 1e-6: shifts[p] = t
        listed = [pname(x) for x in w[key] if not isinstance(x, list)]
        if not shifts: continue
        best = min(shifts.values())
        if any(shifts.get(p, 9) <= best + 1e-6 for p in listed): continue
        cands = [p for p in traits[ci] if shifts.get(p, 9) <= best + 1e-6]
        pick = sorted(cands, key=lambda p: (nn(p) not in notes, traits[ci].index(p)))[0]
        why = f"Hugo's data: {base[0]:.2f}s to {best:.2f}s"
        if len(w[key]) < CAP[key]:
            w[key].append(pick); log.append(f"Added {pick} to Perk {ci + 1}. {why}")
        else:
            old = pname(w[key][-1]); w[key][-1] = pick; log.append(f"Replaced {old} with {pick} in Perk {ci + 1}. {why}")

    edits = note_edits(w, m, typ)
    if edits:
        lines = w["notes"].split("\n")
        for li, a, b, txt, msg in sorted(edits, key=lambda e: (e[0], -e[1])):
            lines[li] = lines[li][:a] + txt + lines[li][b:]; log.append(msg)
        w["notes"] = "\n".join(lines)
    seen = set(); w_log = [x for x in log if not (x in seen or seen.add(x))]; log[:] = w_log

def audit(w, pool):
    """every rule, checked again on the finished weapon; returns the broken ones"""
    bad = []; traits, union, other = pool
    for ci, key in enumerate(("p1", "p2")):
        if len(w.get(key, [])) > CAP[key]: bad.append(f"{key} lists more than {CAP[key]} perks")
        for x in w.get(key, []):
            if pname(x) not in union[ci]: bad.append(f"{pname(x)} does not roll in Perk {ci + 1}")
    for key in ("barrel", "mag"):
        if len(w.get(key, [])) > CAP[key]: bad.append(f"{key} lists more than {CAP[key]}")
        for x in w.get(key, []):
            if pname(x) not in other: bad.append(f"{pname(x)} does not roll as a {key}")
    typ, m = model(w)
    if not m: return bad
    base = ttk(m)[0]
    for ci, key in enumerate(("p1", "p2")):
        shifts = {p: t for p in traits[ci]
                  if (p in ("Explosive Payload", "Timed Payload") or nn(p) == nn("Precision Instrument") or duel_ready(p))
                  for t in [first_ttk(p, m, typ, w.get("slot", ""), w)] if t is not None and t < base - 1e-6}
        if shifts and not any(shifts.get(pname(x), 9) <= min(shifts.values()) + 1e-6 for x in w.get(key, []) if not isinstance(x, list)):
            bad.append(f"Perk {ci + 1} is missing its fastest TTK perk ({min(shifts, key=shifts.get)})")
    for e in note_edits(w, m, typ): bad.append("notes still disagree with Hugo: " + e[4])
    return bad

# ---------- rule 4: the PvP tier list follows TTK ----------
eligible = lambda p: p in ("Explosive Payload", "Timed Payload") or nn(p) == nn("Precision Instrument") or duel_ready(p)

def ttk_box(w):
    """the weapon's finished TTK from its final perk lists: from neutral, each listed perk that speeds it up, and the best"""
    typ, m = model(w)
    if not m: return None
    base = ttk(m)
    if not base: return None
    perks = {}
    for key in ("p1", "p2"):
        for x in w.get(key, []):
            p = pname(x)
            if isinstance(x, list) or not eligible(p): continue
            t = first_ttk(p, m, typ, w.get("slot", ""), w)
            if t is not None and t < base[0] - 1e-6: perks[p] = t
    best = min([base[0]] + list(perks.values()))
    return {"base": base[0], "shots": base[1], "perks": perks, "best": best,
            "by": [p for p, t in sorted(perks.items(), key=lambda kv: kv[1]) if t <= best + 1e-6]}

def column_tops(w):
    """rule 5: in each perk column, the listed perk with the fastest TTK goes first (ties keep Pride's order).
    Returns the column lists in that order"""
    typ, m = model(w)
    out = {}
    for key in ("p1", "p2"):
        col = list(w.get(key, []))
        if m:
            base = ttk(m)
            ts = [(first_ttk(pname(x), m, typ, w.get("slot", ""), w) if not isinstance(x, list) and eligible(pname(x)) else None, i)
                  for i, x in enumerate(col)]
            fast = [(t, i) for t, i in ts if t is not None and base and t < base[0] - 1e-6]
            if fast:
                i = min(fast)[1]; col = [col[i]] + col[:i] + col[i + 1:]
        out[key] = col
    return out

TI = {t: i for i, t in enumerate("SABCDEF")}
def tier_order(PW):
    """Sections Hugo's chart covers are tiered and numbered by finished TTK, fastest first; equal TTKs keep Pride's order
    (his tier, then his rank). Pride's tier sizes for the section stay as the template (his number of S, A, B... filled
    fastest first). A weapon Hugo has no frame data for keeps Pride's tier and sits at the end of it. Every other section
    keeps Pride's tiers and order. Returns {weapon id: (tier, rank)}."""
    out, by = {}, collections.defaultdict(list)
    for w in PW: by[w["arch"]].append(w)
    for arch, ws in by.items():
        pr = {w["id"]: w["pr"] for w in ws}
        best = {w["id"]: b["best"] for w in ws for b in [ttk_box(w)] if b} if arch in TYPE else {}
        if not best:
            for w in ws: out[w["id"]] = tuple(pr[w["id"]])
            continue
        timed = sorted((w for w in ws if w["id"] in best),
                       key=lambda w: (round(best[w["id"]], 3), TI.get(pr[w["id"]][0], 9), pr[w["id"]][1]))
        sizes = collections.Counter(pr[w["id"]][0] for w in timed)
        slots = [t for t in sorted(sizes, key=lambda t: TI.get(t, 9)) for _ in range(sizes[t])]
        tier = {w["id"]: slots[i] for i, w in enumerate(timed)}
        pos = {w["id"]: i for i, w in enumerate(timed)}
        for w in ws: tier.setdefault(w["id"], pr[w["id"]][0])
        final = sorted(ws, key=lambda w: (TI.get(tier[w["id"]], 9), pos.get(w["id"], 10 ** 6), pr[w["id"]][1]))
        for i, w in enumerate(final): out[w["id"]] = (tier[w["id"]], i + 1)
    return out

def audit_order(PW):
    """the finished tiers, ranks and TTK boxes must be exactly what the rules give"""
    bad = []
    if any("pr" not in w for w in PW): return ["Pride's original tier and rank (pr) are missing"]
    exp = tier_order(PW)
    for w in PW:
        tops = column_tops(w)
        for key in ("p1", "p2"):
            if [pname(x) for x in w.get(key, [])] != [pname(x) for x in tops[key]]:
                bad.append(f"{w['name']}: Perk {key[1]} does not lead with its fastest TTK perk ({pname(tops[key][0])})")
        if (w["tier"], w["rank"]) != exp[w["id"]]: bad.append(f"{w['name']}: tier {w['tier']} #{w['rank']} should be {exp[w['id']][0]} #{exp[w['id']][1]}")
        b = ttk_box(w)
        if (b or None) != (w.get("ttk") or None): bad.append(f"{w['name']}: its TTK box is out of date")
    return bad

# ---------- the rules have to keep catching what they are meant to catch ----------
def rule_tests(PW, pools):
    """break each rule on purpose on a copy of a real weapon and make sure audit() notices; if a later code change
    stops a rule from being checked, the build stops here"""
    import copy
    fails = []
    def caught(w, pool, what):
        if not audit(w, pool): fails.append(f"audit no longer catches {what} ({w['name']})")
    ws = [(w, pools[w["id"]]) for w in PW if w["id"] in pools]
    w, pool = ws[0]
    x = copy.deepcopy(w); x["p1"] = x["p1"][:2] + ["Not A Real Perk"]; caught(x, pool, "a perk that does not roll")
    x = copy.deepcopy(w); x["barrel"] = ["Not A Real Barrel"]; caught(x, pool, "a barrel that does not roll")
    x = copy.deepcopy(w); x["p2"] = list(pool[0][1][:4]); caught(x, pool, "more than 3 perks in a column")
    t = next(((w, p) for w, p in ws if w.get("ttk", {}).get("perks")), None)
    if t:
        w, pool = t; x = copy.deepcopy(w)
        for key in ("p1", "p2"): x[key] = [p for p in x[key] if pname(p) not in w["ttk"]["perks"]]
        caught(x, pool, "a column missing its fastest TTK perk")
    t = next(((w, p) for w, p in ws if model(w)[1] and re.search(rf"\d\.\d\d?\s*{ARROW}", w.get("notes") or "")), None)
    if t:
        w, pool = t; x = copy.deepcopy(w)
        x["notes"] = re.sub(rf"(\d\.\d\d?)(\s*{ARROW})", "9.99\\2", x["notes"], count=1); caught(x, pool, "a wrong TTK number in the notes")
    sec = next((a for a in TYPE if sum(1 for w in PW if w["arch"] == a and w.get("ttk")) >= 2), None)
    if sec:
        y = copy.deepcopy(PW); a, b = [w for w in y if w["arch"] == sec and w.get("ttk")][:2]
        a["rank"], b["rank"] = b["rank"], a["rank"]
        if not audit_order(y): fails.append("audit no longer catches a weapon out of TTK order")
        y = copy.deepcopy(PW); c = next(w for w in y if w.get("ttk")); c["ttk"] = dict(c["ttk"], best=0.01)
        if not audit_order(y): fails.append("audit no longer catches a stale TTK box")
        y = copy.deepcopy(PW); c = next(w for w in y if w.get("ttk", {}).get("perks"))
        key = next(k for k in ("p1", "p2") if any(pname(x) in c["ttk"]["perks"] for x in c[k]))
        c[key] = c[key][1:] + c[key][:1] if len(c[key]) > 1 else c[key]
        if len(c[key]) > 1 and not audit_order(y): fails.append("audit no longer catches a fastest perk that is not first in its column")
    return fails

# ---------- run ----------
ok, tot = selftest()
if not tot or ok / tot < 0.9:
    print(f"STOPPING: the TTK model matches only {ok}/{tot} of Hugo's own chart rows. His sheet layout probably changed; check hugo_fetch.py.")
    sys.exit(1)
if not PI: print("WARNING: the Compendium's Precision Instrument numbers were not found; Precision Instrument is left unmodelled")

d = json.load(open(DATA_IN))
PW = [w for w in d["pvp"]["weapons"] if not w.get("exotic")]
pools = {}
for w in PW:
    p = rollable(w)
    if p: pools[w["id"]] = p

if CHECK_ONLY:   # audit a finished build without changing it
    for w in PW:
        if w["id"] in pools: problems += [f"{w['name']}: {p}" for p in audit(w, pools[w["id"]])]
    problems += audit_order(PW)
    if problems:
        print("STOPPING, the PvP lists break the cross check rules:"); [print("  " + p) for p in problems[:40]]; sys.exit(1)
    print(f"Cross check rules hold on all {len(pools)} PvP weapons with random rolls"); sys.exit(0)

report, fixed_roll, changes, moved = [], [], 0, 0
for w in PW:
    w.setdefault("pr", [w["tier"], w["rank"]])        # Pride's own tier and rank, kept for the audit
    pool = pools.get(w["id"])
    if not pool: fixed_roll.append(w["name"])
    else:
        log = []
        fix(w, pool, log)
        if log: changes += len(log); report.append(f"{w['name']} ({w['arch']}): " + " | ".join(log))
        for p in audit(w, pool): problems.append(f"{w['name']}: {p}")
    tops = column_tops(w)
    for key in ("p1", "p2"):
        if [pname(x) for x in w.get(key, [])] != [pname(x) for x in tops[key]]:
            moved += 1; w[key] = tops[key]
    b = ttk_box(w)
    if b: w["ttk"] = b
    else: w.pop("ttk", None)
moves = []
order = tier_order(PW)
for w in PW:
    w["tier"], w["rank"] = order[w["id"]]
    if w["tier"] != w["pr"][0]: moves.append(f"{w['name']} ({w['arch']}) {w['pr'][0]} to {w['tier']}, {w['ttk']['best']:.2f}s")
problems += audit_order(PW)
problems += rule_tests(PW, pools)
checked = len(pools)

if checked < 0.8 * len(PW): problems.append(f"only {checked} of {len(PW)} PvP weapons were found with random rolls on Bungie")
d["pvp"]["xcheck"] = {"hugo": bool(H.get("fetched")), "checked": checked, "changes": changes, "hp": HP}
json.dump(d, open(OUT, "w"), ensure_ascii=False)
ttkw = sum(1 for w in PW if w.get("ttk"))
summary = (f"Cross check: {checked} PvP weapons checked against Bungie's roll pools, {ttkw} against Hugo's TTK data "
           f"(model matches {ok}/{tot} of his chart rows, {HP:g} HP); {changes} changes on {len(report)} weapons"
           + ("" if H.get("fetched") else " (Hugo's chart and the Compendium came from the saved copy)"))
with open(REPORT, "w") as f:
    f.write(summary + "\n")
    if OVERRIDES: f.write("Damage taken from the Compendium's PvP numbers over Hugo's: " + ", ".join(f"{k} {a:.3f} to {b:.3f}" for k, (a, b) in OVERRIDES.items()) + "\n")
    if fixed_roll: f.write(f"Left as listed (only fixed roll copies on Bungie): {', '.join(fixed_roll)}\n")
    f.write(f"Fastest TTK perk moved to the top of its column: {moved} columns\n")
    f.write(f"Tier list by TTK: {len(moves)} weapons changed tier: " + "; ".join(moves) + "\n")
    f.write("\n".join(report) + "\n")
print(summary)
if problems:
    print("STOPPING, the cross check rules are still broken after fixing:"); [print("  " + p) for p in problems[:40]]
    sys.exit(1)
print("All cross check rules hold")
