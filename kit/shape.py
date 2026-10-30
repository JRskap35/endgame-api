import json, re, collections, sys
d = json.load(open(sys.argv[1]))
AMMO = {'primary':['Autos','Bows','HCs','Pulses','Scouts','Sidearms','SMGs'],
        'special':['BGLs','Fusions','Glaives','Shotguns','Snipers','Rocket Sidearms','Traces'],
        'heavy':['HGLs','LFRs','LMGs','Rockets','Swords'],
        'other':['Other']}
AMMO_OF = {a:k for k,v in AMMO.items() for a in v}
COMPOUND = {'Charge Time','Draw Time','Shield Duration','Cooling Efficiency','Blast Radius','Projectile Speed'}
def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')
FN = re.compile(r'\s*\[(\d+)\]')
def notes_in(s): return FN.findall(s), FN.sub('',s).strip()
def wrap_join(lines):
    out=''
    for l in lines:
        t=l['t']
        if not out: out=t
        elif out.endswith('-'): out+=t
        else: out+=' '+t
    return out
def smart_join(lines):
    """keep sheet line breaks except where a line plainly continues the previous one"""
    out=[]
    for l in lines:
        t=l['t']
        if out and (t[:1].islower() or out[-1].endswith((',','(','/','-',' of',' and',' the')) or t[:1] in '(%'):
            out[-1]+= ('' if out[-1].endswith('-') else ' ')+t
        else: out.append(t)
    return '\n'.join(out)
def items(lines): return [[l['t'],1] if l['s'] else l['t'] for l in lines]
def struck(lines): return 1 if lines and all(l['s'] for l in lines) else 0

weapons=[]; ids=set(); fnotes=set()
for w in d['weapons']:
    sec=w['__sec']
    nm=[l for l in w['Name'] if not l['i']]; var=[l for l in w['Name'] if l['i']]
    name=wrap_join(nm); variant=wrap_join(var)
    nid=slug(sec+' '+name+' '+variant)
    assert nid not in ids, nid; ids.add(nid)
    frame_raw=wrap_join(w.get('Frame',[])); fr_n, frame=notes_in(frame_raw)
    stats=[]
    for k in ('Ammo','Shield','Charge','Impact'):
        if k in w:
            n, v = notes_in(wrap_join(w[k])); fnotes.update(n)
            stats.append([k, v, w.get(k+'__fill') or '', n[0] if n else ''])
    mwl=[l['t'] for l in w['MW']]
    mw = ' '.join(mwl) if ' '.join(mwl) in COMPOUND else ' / '.join(mwl)
    fnotes.update(fr_n)
    weapons.append({
        'id':nid,'a':AMMO_OF[sec],'arch':sec,'name':name,'var':variant,
        'season':wrap_join(w['Season']),'element':wrap_join(w['Energy']),'frame':frame,'frameNote':fr_n[0] if fr_n else '',
        'source':wrap_join(w['Source']),'srcX':struck(w['Source']),
        'stun':w['__stun'][0] if w['__stun'] else '—','stats':stats,'up':wrap_join(w['⬆']),
        'barrel':items(w['Barrel']),'mag':items(w['Mag']),'mw':mw,
        'p1':items(w['Perk 1']),'p2':items(w['Perk 2']),
        'origin':wrap_join(w['Origin Trait']),'oriX':struck(w['Origin Trait']),
        'notes':wrap_join(w['Notes']),'rank':int(wrap_join(w['#'])),'tier':wrap_join(w['Tier']),
        'icon':w['__icon']})
g=collections.OrderedDict()
for s in d['sets']:
    name=s['Set'][0]['t']; src=s['Set'][1]['t']
    k=slug(name+' '+src)
    if k not in g: g[k]={'id':k,'name':name,'source':src,'icon':s['__icon'],'season':wrap_join(s['Season']),'bonuses':[]}
    g[k]['bonuses'].append({'pcs':int(s['Pcs'][0]['t']),'name':wrap_join(s['Bonus']),
        'tags':[l['t'] for l in s['Tags']],'trigger':smart_join(s['Trigger']),'effect':smart_join(s['Effect']),
        'desc':wrap_join(s['Description']),'rank':int(wrap_join(s['#'])),'tier':wrap_join(s['Tier'])})
sets=list(g.values())
for s in sets: s['bonuses'].sort(key=lambda b:b['pcs'])
icons={w['id']:w.pop('icon') for w in weapons}
sicons={s['id']:s.pop('icon') for s in sets}
out={'ammo':AMMO,'weapons':weapons,'sets':sets,'notes':{k:v for k,v in d['notes'].items()},'stun':d['stun_icons']}
json.dump(out,open(sys.argv[2],'w'),separators=(',',':'),ensure_ascii=False)
json.dump({'w':icons,'s':sicons},open(sys.argv[3],'w'),separators=(',',':'))
print(len(weapons),len(sets),sorted(fnotes,key=int))
import os; print(os.path.getsize(sys.argv[2]), os.path.getsize(sys.argv[3]))
print(collections.Counter(w['stun'] for w in weapons))
print(weapons[0]); print(sets[0]['bonuses'][0])
print(collections.Counter(w['mw'] for w in weapons))
