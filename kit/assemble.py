"""Fill the app template with data and images.
Usage: python3 -I assemble.py template.html data.json icons.json OUT.html stat_icons.json ticons.json elements.json brand.json [firebase.json]
data.json should be the enriched file from enrich.py; ticons.json comes from enrich.py too.
Without firebase.json (or with one containing null) the page is built for Claude: progress saves through Claude.
With a Firebase web config the page is built as a standalone website: Google sign in, Firestore saving, and a full HTML document."""
import sys, json
t, data, icons, out, stat, ticons, elements, brand = sys.argv[1:9]
fb_path = sys.argv[9] if len(sys.argv) > 9 else None
r = lambda p: open(p, encoding="utf-8").read()
safe = lambda s: s.replace("</", "<\\/")
b = json.load(open(brand))
fb = json.load(open(fb_path)) if fb_path else None
site = fb_path is not None   # any config argument, even null, means a standalone website build
html = r(t)
for key, val in (("__DATA__", safe(r(data))), ("__ICONS__", safe(r(icons))), ("__STATICONS__", safe(r(stat))),
                 ("__TICONS__", safe(r(ticons))), ("__ELEMENTS__", safe(r(elements))), ("__FIREBASE__", json.dumps(fb)),
                 ("__LOGO__", b["logo"]), ("__BG__", b["bg"])):
    assert html.count(key) == 1, key
    html = html.replace(key, val, 1)
if site:
    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="description" content="Destiny 2 god roll and armor tracker built on TheAegisRelic\'s Endgame Analysis, updated weekly.">'
            '<meta name="theme-color" content="#0c0e10">'
            f'<link rel="icon" href="{b["logo"]}"><link rel="apple-touch-icon" href="{b["logo"]}">'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
            '</head><body>')
    html = head + html + "</body></html>"
open(out, "w", encoding="utf-8").write(html)
print(round(len(html) / 1e6, 2), "MB", ("(website build, Google sign in on)" if fb else "(website build, sign in not configured yet)") if site else "(Claude build)")
