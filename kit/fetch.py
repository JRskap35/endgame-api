"""Download Aegis's live "Destiny 2: Endgame Analysis" sheet and keep only the tabs The Vault uses.
Usage: python3 -I fetch.py OUT.pdf [FULL.pdf]
OUT.pdf keeps only the tabs the weapon and armor tables use. FULL.pdf (optional) keeps the whole sheet, which
extract_icons.py needs for the Archetypes, Perks and Origin Traits tabs.
Needs docs.google.com and *.googleusercontent.com in the account's allowed domains."""
import sys, subprocess, tempfile, os, pdfplumber
from pypdf import PdfReader, PdfWriter
SHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"
URL = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=pdf&size=letter&portrait=false"
       "&fitw=true&sheetnames=true&printtitle=true&pagenum=UNDEFINED&gridlines=true&fzr=true")
KEEP = ["Autos","Bows","HCs","Pulses","Scouts","Sidearms","SMGs","BGLs","Fusions","Glaives","Shotguns",
        "Snipers","Rocket Sidearms","Traces","HGLs","LFRs","LMGs","Rockets","Swords","Other","Set Bonuses","Notes"]
out = sys.argv[1]
tmp = tempfile.mkdtemp()
full = os.path.join(tmp, "full.pdf")
subprocess.run(["curl","-sS","-L","--fail","--retry","3","--retry-delay","20","--max-time","280","-o",full,URL], check=True)
pdf = pdfplumber.open(full)
tabs = []
for p in pdf.pages:
    ws = p.extract_words()
    if not ws: tabs.append(""); continue
    top = min(w["top"] for w in ws)
    tabs.append(" ".join(w["text"] for w in ws if abs(w["top"]-top) < 3 and w["x0"] > 500))
found = sorted(set(tabs) & set(KEEP), key=KEEP.index)
missing = [t for t in KEEP if t not in found]
w = PdfWriter(); r = PdfReader(full)
for i, t in enumerate(tabs):
    if t in KEEP: w.add_page(r.pages[i])
with open(out, "wb") as f: w.write(f)
if len(sys.argv) > 2:
    import shutil; shutil.copy(full, sys.argv[2])
for t in ("Archetypes", "Perks", "Origin Traits"):
    if t not in tabs: print("WARNING, icon tab not found (renamed or removed?):", t)
print(f"kept {sum(t in KEEP for t in tabs)} of {len(tabs)} pages")
print("tabs on the sheet that The Vault does not use:", sorted(set(t for t in tabs if t and t not in KEEP)))
if missing: print("WARNING, expected tabs not found (renamed or removed?):", missing)
