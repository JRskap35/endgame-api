# Endgame API

A Destiny 2 weapon and armor tracker built on **TheAegisRelic's** [Destiny 2: Endgame Analysis](https://docs.google.com/spreadsheets/d/1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY/edit) spreadsheet.

**Live site:** https://jrskap35.github.io/endgame-api/

Made by SteelToe.

## Credit

Every weapon tier, ranking, god roll perk, analysis note and armor set bonus rating in Endgame API comes from TheAegisRelic's Endgame Analysis, along with the frame, perk and origin trait icons. All credit for that work goes to him. Endgame API only reorganizes his sheet into a tracker.

Fan made and not affiliated with Bungie. Destiny 2 and its icons and artwork belong to Bungie.

## What it does

1. Browse all 700+ weapons by ammo type and archetype, with stacked sorting and filters for activity, energy, frame, stun type, tier and season.
2. Mark weapons as God Roll, Semi-God Roll or Looking for.
3. Log armor set pieces by stat type, and keep a Looking for list for armor.
4. Track everything in the Vault page.
5. Sign in with Google to save progress to your own account and use it on any device. Without signing in, progress is saved in that browser only.

## How it stays up to date

A GitHub Actions job (`.github/workflows/deploy.yml`) runs every Wednesday evening, downloads the live spreadsheet, rebuilds the site and publishes it to GitHub Pages. It can also be run on demand from the Actions tab with **Run workflow**.

Before publishing, `kit/check.py` checks that every weapon section, rank and armor set looks right. If the sheet changes shape, the job stops without publishing and GitHub emails the repo owner. Each run's summary lists what changed on the sheet: new weapons, removals, tier moves and perk changes.

Saved progress is keyed to each weapon's archetype and name, so tier changes and re-rankings never affect anyone's marks.

## Layout

| Path | What it is |
| --- | --- |
| `src/template.html` | The app: layout, sorting, filters, marking, saving |
| `kit/` | The rebuild pipeline: download the sheet, extract weapons, armor, icons and notes, check, assemble |
| `assets/` | Element icons, armor stat icons, logo and background |
| `firebase/config.json` | Firebase web config (public by design; access is controlled by the rules) |
| `firebase/firestore.rules` | Database rules: each person can read and write only their own data |

## Building locally

```
pip install -r requirements.txt
bash kit/build.sh        # writes site/index.html
```
