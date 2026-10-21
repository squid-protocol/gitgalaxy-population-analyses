"""Twin browser: the function-level evidence behind the descent heatmap, as an
interactive section of the HTML report.

For every pair of repositories that shares structure (at least ``min_shared``), the
report embeds the twins of the direction that defines the pair's shared structure: each
twin's function, file and size on both sides, its distance, and whether it is an exact
structural clone and whether the names agree. In the page the reader picks a pair (or
clicks a descent cell), filters by name, folder, twins with different names or exact clones, and
sees which folders carry the shared code. ``report.html#pair=A|B`` opens a pair directly,
so a write-up can link to the evidence behind each claim.
"""

from __future__ import annotations

import json

import numpy as np

from .fingerprint import FunctionTable
from .lineage import DescentMatrix

EXACT, SAME_NAME = 1, 2


def payload(tables: dict[str, FunctionTable], descent: DescentMatrix, min_shared: float = 0.02,
            max_rows: int = 6000) -> dict:
    """Compact JSON-ready description of every pair's twins. ``max_rows`` caps a single
    pair (closest twins first) to keep the page light; the cap is reported."""
    names = descent.names
    lb = descent.survival_lower
    shared = descent.shared
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if shared[i, j] < min_shared:
                continue
            q, t = (i, j) if lb[i, j] >= lb[j, i] else (j, i)
            r = descent.results.get((q, t))
            if r is None or not len(r.q_index):
                continue
            qt, tt = tables[names[q]], tables[names[t]]
            order = np.argsort(r.distance, kind="stable")[:max_rows]
            paths: dict[str, int] = {}  # each file path stored once per pair
            rows = []
            for k in order:
                qi, ti = int(r.q_index[k]), int(r.t_index[k])
                qn, tn = str(qt.name[qi]), str(tt.name[ti])
                qp = paths.setdefault(str(qt.path[qi]), len(paths))
                tp = paths.setdefault(str(tt.path[ti]), len(paths))
                flags = (EXACT if r.exact[k] else 0) | (SAME_NAME if qn.strip().lower() == tn.strip().lower() else 0)
                rows.append([qn, qp, int(qt.loc[qi]), tn, tp, int(tt.loc[ti]), round(1000 * float(r.distance[k])), flags])
            pairs.append({
                "q": names[q], "t": names[t], "shared": round(float(shared[i, j]), 4),
                "survival": round(float(descent.survival[q, t]), 4), "twins": len(r.q_index),
                "shown": len(rows), "paths": list(paths), "rows": rows,
            })
    pairs.sort(key=lambda p: -p["shared"])
    return {"min_shared": min_shared, "max_rows": max_rows, "pairs": pairs}


def section(data: dict) -> str:
    if not data["pairs"]:
        return ""
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (
        "<section id=twin-browser><h2>Twin browser</h2><p class=note>The function-level evidence behind the "
        f"descent heatmap, for the {len(data['pairs'])} pairs that share at least "
        f"{100 * data['min_shared']:.0f}% of their structure. Pick a pair, or click a cell in the descent heatmap. "
        "Twins were found without names; <em>same name</em> marks twins whose names agree anyway.</p>"
        "<div class=tb-controls><label>Pair <select id=tb-pair></select></label>"
        "<input id=tb-search type=search placeholder='Filter by function or file' aria-label='Filter twins'>"
        "<label><input type=checkbox id=tb-renamed> different names only</label>"
        "<label><input type=checkbox id=tb-exact> exact clones only</label></div>"
        "<p id=tb-summary class=note></p>"
        "<div class=tb-grid><div><h3>By folder</h3><div class=tablewrap><table id=tb-dirs><thead><tr>"
        "<th>Folder</th><th class=num>Twins</th></tr></thead><tbody></tbody></table></div></div>"
        "<div><h3>Twins</h3><div class=tablewrap><table id=tb-rows><thead><tr><th id=tb-qh>Function</th><th>File</th>"
        "<th class=num>Lines</th><th id=tb-th>Twin</th><th>File</th><th class=num>Lines</th>"
        "<th class=num>Distance</th><th>Match</th></tr></thead><tbody></tbody></table></div>"
        "<button id=tb-more type=button hidden>Show all</button></div></div>"
        f"<script type=application/json id=twins>{blob}</script></section>"
    )


CSS = """
.tb-controls{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;margin:8px 0;font-size:13px}
.tb-controls select,.tb-controls input[type=search]{font:inherit;padding:4px 6px;border:1px solid var(--rule);
border-radius:4px;background:var(--surface);color:var(--text);max-width:100%}
.tb-controls input[type=search]{width:240px}
.tb-grid{display:grid;grid-template-columns:minmax(200px,1fr) 3fr;gap:18px}
@media (max-width:800px){.tb-grid{grid-template-columns:1fr}}
#tb-dirs tbody tr{cursor:pointer}#tb-dirs tbody tr.on{outline:2px solid #0055ff;outline-offset:-2px}
#tb-rows td{font-size:12px;overflow-wrap:anywhere}#tb-rows .tag{font-size:11px;padding:1px 5px;border-radius:3px;
border:1px solid var(--rule);white-space:nowrap}
#tb-more{margin-top:8px;font:inherit;padding:4px 10px;border:1px solid var(--rule);border-radius:4px;
background:var(--surface);color:var(--text);cursor:pointer}
rect[data-pair]{cursor:pointer}
"""

JS = r"""
(()=>{const el=document.getElementById('twins');if(!el)return;
const D=JSON.parse(el.textContent),P=D.pairs,$=id=>document.getElementById(id);
const sel=$('tb-pair'),q=$('tb-search'),ren=$('tb-renamed'),ex=$('tb-exact');
let cur=0,dir=null,all=false;
P.forEach((p,i)=>{const o=document.createElement('option');o.value=i;
o.textContent=`${p.q} → ${p.t} · ${p.twins} twins · ${(100*p.shared).toFixed(1)}% shared`;sel.appendChild(o)});
const folder=s=>{const i=s.lastIndexOf('/');return i<0?'(root)':s.slice(0,i)};
const cell=(tr,t,cls)=>{const td=document.createElement('td');td.textContent=t;if(cls)td.className=cls;tr.appendChild(td);return td};
function rows(){const p=P[cur],term=q.value.trim().toLowerCase();
return p.rows.filter(r=>{if(ex.checked&&!(r[7]&1))return false;if(ren.checked&&(r[7]&2))return false;
if(dir!==null&&folder(p.paths[r[1]])!==dir)return false;
if(term&&!(r[0]+' '+p.paths[r[1]]+' '+r[3]+' '+p.paths[r[4]]).toLowerCase().includes(term))return false;return true})}
function render(){const p=P[cur];$('tb-qh').textContent=p.q;$('tb-th').textContent='Twin in '+p.t;
const R=rows(),exact=p.rows.filter(r=>r[7]&1).length,same=p.rows.filter(r=>r[7]&2).length;
$('tb-summary').textContent=`${p.q}: ${(100*p.survival).toFixed(1)}% of its functions have a twin in ${p.t} (${p.twins} twins`+
(p.shown<p.twins?`, the ${p.shown} closest shown`:'')+`). ${exact} exact clones, ${same} with the same name. `+
`${R.length} match the current filter.`;
const counts={};p.rows.forEach(r=>{const f=folder(p.paths[r[1]]);counts[f]=(counts[f]||0)+1});
const tb=$('tb-dirs').tBodies[0];tb.replaceChildren();
Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,25).forEach(([f,n])=>{const tr=document.createElement('tr');
if(f===dir)tr.className='on';cell(tr,f);cell(tr,n,'num');tr.onclick=()=>{dir=(dir===f?null:f);all=false;render()};tb.appendChild(tr)});
const body=$('tb-rows').tBodies[0];body.replaceChildren();const lim=all?R.length:300;
R.slice(0,lim).forEach(r=>{const tr=document.createElement('tr');cell(tr,r[0]);cell(tr,p.paths[r[1]]);cell(tr,r[2],'num');
cell(tr,r[3]);cell(tr,p.paths[r[4]]);cell(tr,(r[6]/1000).toFixed(3),'num');
const m=cell(tr,'');const s=document.createElement('span');s.className='tag';
s.textContent=(r[7]&1?'exact clone':'twin')+(r[7]&2?' · same name':' · different name');m.appendChild(s);body.appendChild(tr)});
const more=$('tb-more');more.hidden=R.length<=lim;more.textContent=`Show all ${R.length}`}
sel.onchange=()=>{cur=+sel.value;dir=null;all=false;render()};
[q,ren,ex].forEach(x=>x.addEventListener('input',()=>{all=false;render()}));
$('tb-more').onclick=()=>{all=true;render()};
const key={};P.forEach((p,i)=>{key[p.q+'|'+p.t]=i;key[p.t+'|'+p.q]=i});
document.addEventListener('click',e=>{const c=e.target.closest('rect[data-pair]');if(!c)return;const i=key[c.dataset.pair];
if(i===undefined)return;cur=i;sel.value=i;dir=null;all=false;render();
document.getElementById('twin-browser').scrollIntoView({behavior:'smooth'});history.replaceState(null,'','#pair='+encodeURIComponent(P[i].q+'|'+P[i].t))});
const h=decodeURIComponent(location.hash);if(h.startsWith('#pair=')&&key[h.slice(6)]!==undefined){cur=key[h.slice(6)];sel.value=cur;
setTimeout(()=>document.getElementById('twin-browser').scrollIntoView(),0)}
sel.addEventListener('change',()=>history.replaceState(null,'','#pair='+encodeURIComponent(P[cur].q+'|'+P[cur].t)));
render()})();
"""

