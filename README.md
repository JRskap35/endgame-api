# Endgame API

A Destiny 2 weapon and armor tracker with a PvE mode built on **TheAegisRelic's** [Destiny 2: Endgame Analysis](https://docs.google.com/spreadsheets/d/1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY/edit) and a PvP mode built on **Pride Eternal / Finnald's** [Destiny 2 PvP Spreadsheet](https://docs.google.com/spreadsheets/d/1TVgtTRWNGEPi6OMlTLxXFSKUTi_ycwykhwuw8EW_jJ0/edit).

**Live site:** https://jrskap35.github.io/endgame-api/

Made by SteelToe.

## Credit

Every weapon tier, ranking, god roll perk, analysis note and armor set bonus rating in Endgame API comes from TheAegisRelic's Endgame Analysis. All credit for that work goes to him. PvP tiers, perks, notes, the Shopping List and PvP set bonus ratings come from Pride Eternal / Finnald's Destiny 2 PvP Spreadsheet, and all credit for that work goes to him. Endgame API only reorganizes their sheets into a tracker.

PvP time to kill numbers come from Hugo's Destiny WeaponStat Chart v2.1, and perk triggers and PvP perk numbers from the Destiny Data Compendium. Where either disagrees with a PvP pick, their data is followed (see below).

Weapon images and the frame, barrel, magazine, masterwork, perk, origin trait, energy, stun and armor set icons come from Bungie's public Destiny 2 API.

Fan made and not affiliated with Bungie. Destiny 2 and its icons and artwork belong to Bungie.

## What it does

1. Browse all 700+ weapons by ammo type and archetype, with stacked sorting and filters for activity, energy, frame, stun type, tier and season.
2. Mark weapons as God Roll, Semi-God Roll or Looking for.
3. Click any weapon's picture to see Bungie's full artwork of it.
4. Log armor set pieces by stat type, and keep a Looking for list for armor.
5. Track everything in the Vault page.
6. Sign in with Google to save progress to your own account and use it on any device. Without signing in, progress is saved in that browser only.

## How it stays up to date

A GitHub Actions job (`.github/workflows/deploy.yml`) runs every Wednesday evening, downloads the live spreadsheet, pulls the matching icons from Bungie's Destiny 2 API (`kit/bungie.py`), rebuilds the site and publishes it to GitHub Pages. New weapons Aegis adds get their Bungie icons on the same run; anything Bungie doesn't have yet keeps the sheet's icon until it does. It can also be run on demand from the Actions tab with **Run workflow**.

Before publishing, `kit/check.py` checks that every weapon section, rank and armor set looks right. If the sheet changes shape, the job stops without publishing and GitHub emails the repo owner. Each run's summary lists what changed on the sheet: new weapons, removals, tier moves and perk changes.

### PvP cross check

Pride's PvP sheet is the baseline, and `kit/crosscheck.py` checks it against three other sources on every run, following them where they disagree:

1. **Bungie's roll pools.** Every listed barrel, magazine and perk has to roll on the weapon in Bungie's manifest. Spellings follow Bungie, a perk listed under the wrong column moves to the right one, and anything that cannot roll is removed.
2. **Hugo's time to kill (TTK) data.** For autos, hand cannons, pulses, scouts, sidearms and SMGs, each perk column that has a perk which lowers the TTK on its first activation has to list one that reaches the fastest TTK. A perk only counts when the Compendium says a duel can switch it on, such as a weapon kill or a kill reload. If none is listed, the fastest one is added.
3. **TTK numbers in the notes** are rewritten to Hugo's numbers where they differ.
4. **The tier list follows TTK.** For those same six weapon types, tiers and #ranks are set by each weapon's finished TTK (the fastest its final perks reach on first activation), fastest first. Equal TTKs keep Pride's order, and each section keeps Pride's number of S, A, B and so on tier weapons. Other weapon types keep Pride's tiers and order.
5. **The fastest perk leads its column.** In each perk column, the listed perk with the fastest TTK is shown first, so the perk behind a weapon's TTK is always at the top.

Every change is listed in the run summary; the weapon's details panel shows only its finished TTK. The step stops the deploy if a rule still breaks after fixing, if its TTK math stops matching Hugo's own chart, or if its audit stops catching a rule it breaks on purpose. The job rebuilds every Wednesday whether or not the sheets changed, so a change to Hugo's chart or the Compendium alone still updates the PvP perks, tiers and TTK numbers that week. `kit/hugo_fetch.py` downloads Hugo's chart and the Compendium, falling back to the saved copy in `assets/hugo_cache.json` if either is unreachable.

Saved progress is keyed to each weapon's archetype and name, so tier changes and re-rankings never affect anyone's marks.

## Layout

| Path | What it is |
| --- | --- |
| `src/template.html` | The app: layout, sorting, filters, marking, saving |
| `kit/` | The rebuild pipeline: download the sheet, extract weapons, armor and notes, check, swap in Bungie's icons, assemble |
| `assets/` | Armor stat icons, logo, background and sound (plus fallback energy icons) |
| `firebase/config.json` | Firebase web config (public by design; access is controlled by the rules) |
| `firebase/firestore.rules` | Database rules: each person can read and write only their own data |

## Building locally

```
pip install -r requirements.txt
bash kit/build.sh        # writes site/index.html
```
