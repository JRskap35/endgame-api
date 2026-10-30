"""Safety checks run before every publish. Exits non zero (which stops the deploy) if the sheet looks wrong.
Usage: python3 -I check.py data_e.json icons.json"""
import json, sys, collections
d = json.load(open(sys.argv[1])); icons = json.load(open(sys.argv[2]))
W, SETS = d["weapons"], d["sets"]
problems = []
expected = [a for arr in d["ammo"].values() for a in arr]
by = collections.defaultdict(list)
for w in W: by[w["arch"]].append(w)
for sec in expected:
    if not by.get(sec): problems.append(f"section {sec} has no weapons (renamed or removed on the sheet?)")
for sec, ws in by.items():
    ranks = sorted(w["rank"] for w in ws)
    if ranks != list(range(1, len(ws) + 1)): problems.append(f"section {sec} ranks are not 1..{len(ws)}")
if len(W) < 600: problems.append(f"only {len(W)} weapons (expected roughly 700 or more)")
if len(SETS) < 45: problems.append(f"only {len(SETS)} armor sets (expected roughly 50 or more)")
for s in SETS:
    if sorted(b["pcs"] for b in s["bonuses"]) != [2, 4]: problems.append(f"armor set {s['name']} does not have one 2 piece and one 4 piece bonus")
slots = sum(len(w["p1"]) + len(w["p2"]) for w in W)
hit = sum(len(w.get("pi", {})) for w in W)
if slots and hit / slots < 0.95: problems.append(f"only {hit}/{slots} perks matched an icon")
missing_icons = [w["name"] for w in W if w["id"] not in icons["w"]]
if missing_icons: problems.append(f"{len(missing_icons)} weapons have no icon, for example {missing_icons[:3]}")
print(f"{len(W)} weapons in {len(by)} sections, {len(SETS)} armor sets, perk icons {hit}/{slots}")
if problems:
    print("STOPPING, the sheet looks different than expected:"); [print("  " + p) for p in problems]; sys.exit(1)
print("All checks passed")
