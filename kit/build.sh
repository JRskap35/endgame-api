#!/usr/bin/env bash
# Rebuild Endgame API from TheAegisRelic's live sheet into site/index.html
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build site
python3 -I kit/fetch.py build/new.pdf build/full.pdf
python3 -I kit/extract.py build/new.pdf build/raw.json
python3 -I kit/shape.py build/raw.json build/data.json build/icons.json
python3 -I kit/extract_icons.py build/full.pdf build/trait_icons.json
python3 -I kit/enrich.py build/data.json build/trait_icons.json build/data_e.json build/ticons.json
python3 -I kit/check.py build/data_e.json build/icons.json
python3 -I kit/assemble.py src/template.html build/data_e.json build/icons.json site/index.html assets/stat_icons.json build/ticons.json assets/elements.json assets/brand.json firebase/config.json
# what changed since the last published version (shown on the workflow run page)
if [ -n "${SITE_URL:-}" ] && curl -sSfL --max-time 60 "$SITE_URL" -o build/prev.html; then
  { echo '## What changed on the sheet'; echo '```'; python3 -I kit/diff.py build/prev.html build/data.json; echo '```'; } >> "${GITHUB_STEP_SUMMARY:-/dev/null}" || true
fi
