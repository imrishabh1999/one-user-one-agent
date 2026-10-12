"""Build sample_run/explorer.html: one self-contained page to walk any viewer from app open to judged outcome.
No server, no external scripts; the run's data is embedded as JSON."""
import json
import os
from collections import Counter

from .config import iso


def _compact(d):
    g = d.get("goal") or {}
    return {"id": d["decision_id"], "at": d["trigger"]["received_at"], "tr": d["trigger"].get("event"),
            "age": d["trigger"].get("event_age_s"), "st": d["status"], "act": d["action"],
            "goal": g.get("id"), "gname": g.get("name"), "dl": g.get("deadline"), "cont": g.get("continuing"),
            "dia": d["dialect"]["used"], "dsrc": d["dialect"]["source"], "conf": d["dialect"]["conflicts"],
            "content": [c.split(":")[1] for c in d["content"]], "c": d["confidence"], "cr": d["confidence_reason"],
            "why": (d["reason"] or "")[:400], "pass": d["checks"]["passed"],
            "fail": [f"{f['check']}: {f['detail']}"[:160] for f in d["checks"]["failed"]],
            "rej": [f"{r['action']} ✗ {', '.join(x['check'] for x in r['failed'])}" for r in d["rejected_proposals"]],
            "llm": [f"{m['task']}: {m.get('claim') or m.get('proposed')} → {m['why_rejected']}"[:300]
                    for m in d["model"]["outputs_rejected"]],
            "ev": d["evidence"][:8], "ms": d["decided_in_ms"], "mc": d["budget"]["model_calls"],
            "tc": d["budget"]["tool_calls"], "arm": d["arm"],
            "asm": d.get("assumptions", [])[:3]}


def build(store, out_dir, decisions, lat, imp, audits):
    by_v = {}
    for d in decisions:
        by_v.setdefault(d["viewer_id"], []).append(_compact(d))
    outs = {}
    for r in store.db.execute("SELECT data FROM outcomes"):
        o = json.loads(r["data"])
        outs.setdefault(o["viewer_id"], []).append(
            {"g": o["goal_id"], "d": o["decision_id"], "v": o["verdict"], "why": o["reason"][:240],
             "attr": o.get("attribution"), "old": o.get("verdict_under_rule_at_open"), "at": o["judged_at"]})
    learn = {}
    for r in store.db.execute("SELECT viewer_id, ts, kind FROM learnings ORDER BY ts"):
        learn.setdefault(r["viewer_id"], []).append(f"{iso(r['ts'])[:16]} {r['kind']}")
    featured = [{"k": k.replace("_", " "), "v": v} for k, v in audits.items() if v]
    data = {"viewers": by_v, "outcomes": outs, "learn": learn, "featured": featured,
            "kpi": {"decisions": len(decisions), "status": Counter(d["status"] for d in decisions),
                    "p95": lat["decided_in_ms"]["p95"], "over60": lat["over_60s"],
                    "itt": imp["itt_complete_3d"], "naive": imp["pilot"]["naive_served_vs_rest"],
                    "pilot_itt": imp["pilot"]["itt"]}}
    html = PAGE.replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    path = os.path.join(out_dir, "explorer.html")
    open(path, "w", encoding="utf-8").write(html)
    return path


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Audit Explorer</title>
<style>
:root{--bg:#f6f4ef;--panel:#fffdf8;--ink:#1c1b19;--mute:#6b675f;--line:#e2ddd2;--accent:#b4441f;--ok:#2f7a4a;--no:#8a6d1f;--bad:#a3322a;--hold:#4a5f8a;--chip:#efe9dc}
@media (prefers-color-scheme:dark){:root{--bg:#151412;--panel:#1d1c19;--ink:#ece8df;--mute:#a19b90;--line:#2f2d29;--accent:#e2774f;--ok:#6bbf86;--no:#d2b25a;--bad:#e27a70;--hold:#8fa6d6;--chip:#28261f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:20px 24px 8px;border-bottom:1px solid var(--line)}h1{margin:0;font:600 20px/1.2 Georgia,serif;letter-spacing:.2px}
header p{margin:4px 0 0;color:var(--mute)}
.kpis{display:flex;flex-wrap:wrap;gap:10px;padding:12px 24px}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px;min-width:140px}
.kpi b{display:block;font:600 18px/1.2 Georgia,serif}.kpi span{color:var(--mute);font-size:12px}
main{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:8px 24px 40px}
@media (max-width:760px){main{grid-template-columns:1fr;padding:8px 16px 40px}.kpis{padding:12px 16px}header{padding:16px}}
aside{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;align-self:start;position:sticky;top:12px}
input,select{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:12px 0 6px}
.feat button{display:block;width:100%;text-align:left;border:0;background:transparent;color:var(--ink);padding:6px 8px;border-radius:6px;cursor:pointer;font:inherit}
.feat button:hover,.feat button.on{background:var(--chip)}.feat small{color:var(--mute)}
#list{max-height:240px;overflow:auto;margin-top:6px}#list div{padding:3px 8px;cursor:pointer;border-radius:6px;font-family:ui-monospace,monospace;font-size:12px}#list div:hover{background:var(--chip)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:12px;position:relative}
.timeline{border-left:2px solid var(--line);margin-left:6px;padding-left:18px}
.timeline .card:before{content:"";position:absolute;left:-26px;top:18px;width:10px;height:10px;border-radius:50%;background:var(--dot,var(--mute));border:2px solid var(--bg)}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.tag{background:var(--chip);border-radius:999px;padding:1px 9px;font-size:12px}
.st{font-weight:600}.PUBLISHED{color:var(--ok)}.NO_ACTION{color:var(--no)}.HOLDOUT_SUPPRESSED{color:var(--hold)}.EXPIRED{color:var(--bad)}
.SUCCEEDED{color:var(--ok)}.FAILED{color:var(--bad)}.INCONCLUSIVE{color:var(--no)}
dl{display:grid;grid-template-columns:120px 1fr;gap:3px 10px;margin:10px 0 0}dt{color:var(--mute)}dd{margin:0;overflow-wrap:anywhere}
.mono{font-family:ui-monospace,monospace;font-size:12px}.warn{color:var(--bad)}
h2{font:600 16px/1.3 Georgia,serif;margin:4px 0 12px}h3{font:600 13px/1.3 inherit;margin:0;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
.empty{color:var(--mute);padding:30px;text-align:center}
</style></head><body>
<header><h1>Agent Audit Explorer</h1><p>Pick any viewer to see what the agent knew, decided and observed, from app open to judged outcome.</p></header>
<div class="kpis" id="kpis"></div>
<main><aside>
<input id="q" placeholder="Viewer id, e.g. V-0005" autocomplete="off">
<div class="lbl">Surprise walk-throughs</div><div class="feat" id="feat"></div>
<div class="lbl">Browse by status</div>
<select id="f"><option value="">All viewers</option><option>PUBLISHED</option><option>NO_ACTION</option><option>HOLDOUT_SUPPRESSED</option><option value="REJ">Model output rejected</option><option value="CONF">Dialect conflict</option></select>
<div id="list"></div></aside>
<section id="view"><div class="empty">Choose a viewer on the left.</div></section></main>
<script>
const D=/*DATA*/null;
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const k=D.kpi,pct=r=>`${r.diff_pp>0?"+":""}${r.diff_pp} pp`;
$("#kpis").innerHTML=[["Decisions",k.decisions],["Published",k.status.PUBLISHED||0],["No action",k.status.NO_ACTION||0],["Holdout (shadow)",k.status.HOLDOUT_SUPPRESSED||0],["p95 latency",(k.p95/1000).toFixed(1)+" s"],["Over 60 s",k.over60],["ITT: episode in 3 d",pct(k.itt)],["Pilot claim → ITT",pct(k.naive)+" → "+pct(k.pilot_itt)]].map(([a,b])=>`<div class="kpi"><b>${esc(b)}</b><span>${esc(a)}</span></div>`).join("");
$("#feat").innerHTML=D.featured.map(x=>`<button data-v="${x.v}">${esc(x.k)}<br><small class="mono">${x.v}</small></button>`).join("");
$("#feat").onclick=e=>{const b=e.target.closest("button");if(b)show(b.dataset.v)};
const ids=Object.keys(D.viewers).sort();
function listFor(f){return ids.filter(v=>{const ds=D.viewers[v];if(!f)return true;if(f=="REJ")return ds.some(d=>d.llm.length);if(f=="CONF")return ds.some(d=>d.conf.length);return ds.some(d=>d.st==f)}).slice(0,300)}
function renderList(){const L=listFor($("#f").value);$("#list").innerHTML=L.map(v=>`<div data-v="${v}">${v} · ${D.viewers[v].length}</div>`).join("")}
$("#f").onchange=renderList;$("#list").onclick=e=>{const d=e.target.closest("div[data-v]");if(d)show(d.dataset.v)};
$("#q").oninput=e=>{const v=e.target.value.trim().toUpperCase();if(D.viewers[v])show(v)};
const dot={PUBLISHED:"var(--ok)",NO_ACTION:"var(--no)",HOLDOUT_SUPPRESSED:"var(--hold)",EXPIRED:"var(--bad)"};
function show(v){document.querySelectorAll(".feat button").forEach(b=>b.classList.toggle("on",b.dataset.v==v));
 const ds=D.viewers[v]||[],os=D.outcomes[v]||[],ls=D.learn[v]||[];
 let h=`<h2>${v} <span class="tag">${ds[0]?.arm||""} arm</span></h2><h3>Decisions</h3><div class="timeline">`;
 for(const d of ds){h+=`<div class="card" style="--dot:${dot[d.st]||"var(--mute)"}"><div class="row"><span class="mono">${d.id}</span><span class="tag">${esc(d.at)}</span><span class="tag">${esc(d.tr)}${d.age!=null?" · "+d.age+" s old":""}</span><span class="st ${d.st}">${d.st}</span><b>${d.act}</b></div><dl>
 <dt>Goal</dt><dd>${d.goal?`${d.goal} ${esc(d.gname)} · deadline ${esc(d.dl)} · ${d.cont?"continuing":"new"}`:"none"}</dd>
 <dt>Why</dt><dd>${esc(d.why)}</dd>
 <dt>Dialect</dt><dd>${esc(d.dia)} from ${esc(d.dsrc)}${d.conf.length?` <span class="warn">conflicts: ${esc(d.conf.join(", "))}</span>`:""}</dd>
 ${d.content.length?`<dt>Content</dt><dd class="mono">${esc(d.content.join("  "))}</dd>`:""}
 ${d.c!=null?`<dt>Confidence</dt><dd>${d.c} · ${esc(d.cr)}</dd>`:""}
 ${d.asm.length?`<dt>Assumptions</dt><dd>${esc(d.asm.join(" · "))}</dd>`:""}
 <dt>Checks</dt><dd>${d.pass.length} passed${d.fail.length?` · <span class="warn">${esc(d.fail.join("; "))}</span>`:""}</dd>
 ${d.rej.length?`<dt>Walked down</dt><dd>${esc(d.rej.join(" · "))}</dd>`:""}
 ${d.llm.length?`<dt>Model rejected</dt><dd class="warn">${esc(d.llm.join(" | "))}</dd>`:""}
 <dt>Evidence</dt><dd class="mono">${esc(d.ev.join("  "))}</dd>
 <dt>Cost</dt><dd>${d.ms} ms · ${d.mc} model / ${d.tc} tool calls</dd></dl></div>`}
 h+=`</div><h3>Outcomes</h3>`+(os.length?os.map(o=>`<div class="card"><div class="row"><span class="mono">${o.d}</span><b>${o.g}</b><span class="st ${o.v}">${o.v}</span>${o.attr?`<span class="tag">${esc(o.attr)}</span>`:""}${o.old?`<span class="tag">old rule: ${o.old}</span>`:""}</div><div style="margin-top:6px">${esc(o.why)}</div></div>`).join(""):`<div class="card">No goal judged.</div>`);
 h+=`<h3>Learned</h3><div class="card mono">${ls.length?ls.map(esc).join("<br>"):"Nothing yet."}</div>`;
 $("#view").innerHTML=h;$("#q").value=v;}
renderList();if(D.featured[0])show(D.featured[0].v);
</script></body></html>"""
