#!/usr/bin/env bash
# Rebuild Endgame API from TheAegisRelic's live sheet (PvE), Pride Eternal's PvP sheet and Bungie's Destiny 2 API into site/index.html
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build site
python3 -I kit/fetch.py build/new.pdf build/full.pdf
python3 -I kit/extract.py build/new.pdf build/raw.json
python3 -I kit/shape.py build/raw.json build/data.json build/icons.json
python3 -I kit/extract_icons.py build/full.pdf build/trait_icons.json
python3 -I kit/enrich.py build/data.json build/trait_icons.json build/data_e.json build/ticons.json
python3 -I kit/check.py build/data_e.json build/icons.json
# PvP mode: Pride Eternal / Finnald's Destiny 2 PvP Spreadsheet (legendary + exotic weapons, Shopping List, set bonuses)
python3 -I kit/pvp_fetch.py build/pvp_raw.json
python3 -I kit/pvp.py build/data_e.json build/pvp_raw.json build/data_ep.json
# swap in Bungie's official icons (weapons, frames, perks, barrels, mags, masterwork, origin traits, energy, stun, armor sets)
python3 -I kit/bungie.py build/data_ep.json build/icons.json build/ticons.json assets/elements.json build/bungie "${BUNGIE_CACHE:-build/bungie_cache}"
cat build/bungie/report.txt >> "${GITHUB_STEP_SUMMARY:-/dev/null}" || true
python3 -I kit/assemble.py src/template.html build/bungie/data.json build/bungie/icons.json site/index.html assets/stat_icons.json build/bungie/ticons.json build/bungie/elements.json assets/brand.json firebase/config.json
# what changed since the last published version (shown on the workflow run page)
if [ -n "${SITE_URL:-}" ] && curl -sSfL --max-time 60 "$SITE_URL" -o build/prev.html; then
  { echo '## What changed on the sheet'; echo '```'; python3 -I kit/diff.py build/prev.html build/data.json; echo '```'; } >> "${GITHUB_STEP_SUMMARY:-/dev/null}" || true
fi
