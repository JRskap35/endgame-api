"""Download Pride Eternal / Finnald's "Destiny 2 PvP Spreadsheet" and turn the tabs Endgame API uses into grids.
Usage: python3 -I pvp_fetch.py OUT.json
The sheet is view-by-link with downloads turned off, so it is read through Google's public HTML view
(htmlview/sheet?gid=...), the same page anyone with the link sees. Each tab becomes a list of rows; each cell is
{"t": text (line breaks kept), "x": true if the whole cell is struck through}."""
import json, re, sys, subprocess, html
from html.parser import HTMLParser

SHEET = "1TVgtTRWNGEPi6OMlTLxXFSKUTi_ycwykhwuw8EW_jJ0"
TABS = ["Shopping List", "Legendary Weapons", "Exotic Weapons", "Set Bonuses", "Status"]
BASE = f"https://docs.google.com/spreadsheets/d/{SHEET}/htmlview"

def get(url):
    r = subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "--retry-delay", "5", "--max-time", "180", url], capture_output=True, check=True)
    return r.stdout.decode("utf-8", "replace")

class Grid(HTMLParser):
    def __init__(self, struck):
        super().__init__(convert_charrefs=True); self.struck = struck
        self.rows = []; self.row = None; self.cell = None; self.depth_strike = 0; self.in_td = False
    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "tr": self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"t": "", "x": a.get("class", "") in self.struck, "span": int(a.get("colspan", 1) or 1), "parts": []}; self.in_td = True
        elif tag == "br" and self.in_td: self.cell["t"] += "\n"
        elif tag in ("span", "s", "strike") and self.in_td:
            st = a.get("style", "") or ""; cls = a.get("class", "")
            self.cell["parts"].append(("line-through" in st) or tag in ("s", "strike") or cls in self.struck)
    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            c = self.cell; c["t"] = c["t"].strip(); c.pop("parts")
            self.row.append(c)
            for _ in range(c.pop("span") - 1): self.row.append({"t": "", "x": False})
            self.in_td = False; self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row); self.row = None
    def handle_data(self, d):
        if self.in_td: self.cell["t"] += d

def tab(gid):
    page = get(f"{BASE}/sheet?headers=true&gid={gid}")
    struck = set(re.findall(r"\.(s\d+)\{[^}]*text-decoration:[^;}]*line-through", page))
    g = Grid(struck); g.feed(page)
    return g.rows

def main(out):
    index = get(BASE)
    gids = {html.unescape(n.encode().decode("unicode_escape")): g for n, g in re.findall(r'items\.push\(\{name: "([^"]+)", pageUrl: "[^"]+", gid: "(\d+)"', index)}
    missing = [t for t in TABS if t not in gids]
    if missing: print("WARNING: tabs not found on the PvP sheet:", ", ".join(missing)); sys.exit(1)
    data = {t: tab(gids[t]) for t in TABS}
    json.dump(data, open(out, "w"), ensure_ascii=False)
    for t, rows in data.items(): print(f"{t}: {len(rows)} rows")

if __name__ == "__main__": main(sys.argv[1])
