"""Compare the data inside two Vault builds and report what changed.
Usage: python3 -I diff.py OLD NEW   (each is a data.json or a built the-vault.html)"""
import json, re, sys
def load(p):
    s = open(p, encoding="utf-8").read()
    if p.endswith(".html"):
        m = re.search(r'<script id="vault-data" type="application/json">(.*?)</script>', s, re.S)
        s = m.group(1).replace("<\\/", "</")
    return json.loads(s)
old, new = load(sys.argv[1]), load(sys.argv[2])
ow = {w["id"]: w for w in old["weapons"]}; nw = {w["id"]: w for w in new["weapons"]}
os_ = {s["id"]: s for s in old["sets"]}; ns = {s["id"]: s for s in new["sets"]}
added = [nw[k] for k in nw if k not in ow]; removed = [ow[k] for k in ow if k not in nw]
print(f"Weapons: {len(ow)} -> {len(nw)}   Sets: {len(os_)} -> {len(ns)}")
print(f"\nNEW WEAPONS ({len(added)})"); [print(f"  {w['arch']}: {w['name']} {w['var']} [{w['tier']}]") for w in added]
print(f"\nREMOVED OR RENAMED WEAPONS ({len(removed)})  <- saved marks on these ids would be orphaned"); [print(f"  {w['arch']}: {w['name']} {w['var']}") for w in removed]
print("\nTIER CHANGES")
for k in nw:
    if k in ow and ow[k]["tier"] != nw[k]["tier"]:
        print(f"  {nw[k]['arch']}: {nw[k]['name']}  {ow[k]['tier']} -> {nw[k]['tier']}")
print("\nPERK / ORIGIN / SOURCE CHANGES")
for k in nw:
    if k in ow:
        diffs = [f for f in ("p1","p2","barrel","mag","origin","source","frame","element") if ow[k].get(f) != nw[k].get(f)]
        if diffs: print(f"  {nw[k]['arch']}: {nw[k]['name']}  ({', '.join(diffs)})")
print(f"\nNEW SETS: {[ns[k]['name'] for k in ns if k not in os_]}")
print(f"REMOVED SETS: {[os_[k]['name'] for k in os_ if k not in ns]}")
for k in ns:
    if k in os_:
        a = [(b['pcs'], b['tier']) for b in os_[k]['bonuses']]; b = [(x['pcs'], x['tier']) for x in ns[k]['bonuses']]
        if a != b: print(f"  bonus tier change: {ns[k]['name']} {a} -> {b}")
