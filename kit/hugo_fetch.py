"""Download the two data sources the PvP perk cross check (crosscheck.py) follows over Pride's sheet:
  Hugo's Destiny WeaponStat Chart v2.1 (the PvP Weapon Stat Breakpoints linked from the Destiny Data Compendium):
    WeaponStat Chart tab (his published time to kill per frame), WeaponData tab (damage and fire delay per frame),
    Reference tab (damage and fire rate multiplier of every perk and stack)
  Destiny Data Compendium, Weapon Perks tab (what triggers each perk, and its numbers, PvP values in [brackets])
Both are public sheets, read through their public HTML view.
Usage: python3 -I hugo_fetch.py OUT.json FALLBACK.json
If a download fails or a tab no longer looks right, the last good copy in FALLBACK.json is used and a WARNING is
printed, so a sheet hiccup never stops the weekly update. Run with --refresh to also rewrite FALLBACK.json.
Prints "Fingerprint: <code>", a short code of everything read from both sheets; the weekly Claude check stores it in
last_build.json (hugoFingerprint) and rebuilds when it changes, even if Aegis's sheet, Pride's sheet and Bungie did not."""
import json, re, subprocess, sys, hashlib
from html.parser import HTMLParser

HUGO = "1FWMC-Vd_bGEoRkkrn3drWIORCFYyWQVMNlMasa4OE6I"
COMP = "1WaxvbLx7UoSZaBqdFr1u32F2uWVLo-CJunJB4nlGUE4"
TABS = {"chart": (HUGO, "1692216024"), "data": (HUGO, "1678079223"), "ref": (HUGO, "197776868"), "perks": (COMP, "1662574278")}

class Grid(HTMLParser):
    """table cells of a Google Sheets htmlview page, row by row (merged cells padded so columns line up)"""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.rows = []; self.row = None; self.cell = None
    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "tr": self.row = []
        elif tag == "td" and self.row is not None: self.cell = ["", int(a.get("colspan", 1) or 1)]
        elif tag == "br" and self.cell is not None: self.cell[0] += "\n"
    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(self.cell[0].strip()); self.row += [""] * (self.cell[1] - 1); self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row); self.row = None
    def handle_data(self, d):
        if self.cell is not None: self.cell[0] += d

def tab(sheet, gid):
    url = f"https://docs.google.com/spreadsheets/d/{sheet}/htmlview/sheet?headers=true&gid={gid}"
    page = subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "--retry-delay", "5", "--max-time", "180", url],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    g = Grid(); g.feed(page); return g.rows

def shape(raw):
    """keep only what crosscheck.py reads, as plain lists of strings"""
    data = raw["data"]
    head = next(r for r in data if "shot delay" in " ".join(r).lower())
    hi = data.index(head)
    n = head.index("ref RPM") + 1 if "ref RPM" in head else 19
    out = {"data_head": [h.replace("\n", " ") for h in head[:n]],
           "data": [r[:n] for r in data[hi + 1:] if r and r[0] and "_" in r[0]],
           "ref": [r[:9] for r in raw["ref"] if len(r) >= 9 and r[0] and r[0] != "Trait Name"],
           "chart": [r[:13] for r in raw["chart"] if len(r) >= 13 and r[0] and r[12]],
           "perks": {r[0].strip(): r[2] for r in raw["perks"] if len(r) > 2 and r[0].strip() and len(r[2]) > 15}}
    return out

def looks_right(d):
    """the tabs still have the rows crosscheck.py depends on"""
    ref = {r[0] for r in d["ref"]}
    return (len(d["data"]) >= 100 and any(r[0] == "Auto_p_Adaptive" for r in d["data"]) and "shot delay" in d["data_head"]
            and {"Kill Clip", "Rampage x1", "Adagio"} <= ref and len(d["chart"]) >= 40
            and {"Kill Clip", "Rampage", "Desperado"} <= set(d["perks"]))

def fingerprint(d):
    """one short code for everything crosscheck.py reads from both sheets; it changes whenever Hugo or the Compendium
    changes a number, a perk row or a description, so the weekly check knows to rebuild"""
    keep = {k: d[k] for k in ("data_head", "data", "ref", "chart", "perks")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

def main(out, fallback, refresh=False):
    try:
        d = shape({k: tab(*v) for k, v in TABS.items()})
        if not looks_right(d): raise ValueError("a tab is missing rows crosscheck.py needs (renamed or moved?)")
        d["fetched"] = True; d["fingerprint"] = fingerprint(d)
        if refresh: json.dump(d, open(fallback, "w"), ensure_ascii=False)
        print(f"Hugo's chart: {len(d['data'])} frames, {len(d['ref'])} perk rows, {len(d['chart'])} chart rows; Compendium: {len(d['perks'])} perks")
        print(f"Fingerprint: {d['fingerprint']}")
    except Exception as e:
        print(f"WARNING: could not read Hugo's chart or the Compendium ({e}); using the saved copy in {fallback}")
        d = json.load(open(fallback)); d["fetched"] = False; d["fingerprint"] = fingerprint(d)
        print("Fingerprint: unavailable (saved copy used)")
    json.dump(d, open(out, "w"), ensure_ascii=False)

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], "--refresh" in sys.argv)
