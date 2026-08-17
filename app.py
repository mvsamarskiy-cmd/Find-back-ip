import os, random, re
from flask import Flask, request, jsonify, render_template
from availability import check_all, check_many
from ai_engine import generate_ai_names, trademark_links

app = Flask(__name__)

BANNED_ROOTS = {"idea","product","make","maker","creat","build","factory","forge","foundry","lab","studio","shop","store","market","communit","crowd","vote","preorder","drop","pin","merch","object","reality","real","ai","tech"}
BANNED_SUFFIXES = {"ora","ova","ira","iva","eya","aya","io","ly","ify","verse","works","base","hub","flow","labs"}
ONSETS = ["v","n","m","r","l","s","t","k","d","f","z","b","p","c","g","h","br","cr","dr","fr","gr","kr","pr","tr","vr","st","sk","cl","fl","pl"]
NUCLEI = ["a","e","i","o","u","ae","ai","ea","eo","oa","ui"]
CODAS = ["","n","r","s","l","m","x","v","d","t","k"]

def clean(s): return re.sub(r"[^a-z]", "", s.lower())

def clean_preferences(value):
    """Bound browser-supplied feedback before it reaches the model prompt."""
    if not isinstance(value, dict):
        return {"liked": [], "disliked": [], "reasons": {}}

    def examples(key):
        raw = value.get(key, [])
        if not isinstance(raw, list):
            return []
        output = []
        for item in raw[:20]:
            name = clean(str(item))[:30]
            if name and name not in output:
                output.append(name)
        return output

    raw_reasons = value.get("reasons", {})
    reasons = {}
    if isinstance(raw_reasons, dict):
        for key, score in list(raw_reasons.items())[:20]:
            safe_key = re.sub(r"[^a-z_]", "", str(key).lower())[:30]
            if not safe_key:
                continue
            try:
                reasons[safe_key] = max(-20, min(20, int(score)))
            except (TypeError, ValueError):
                continue
    return {"liked": examples("liked"), "disliked": examples("disliked"), "reasons": reasons}

def score_name(name):
    n=clean(name); score=100
    if not 5 <= len(n) <= 8: score-=18
    if len(n) in (5,6,7): score+=8
    vowels=sum(c in "aeiouy" for c in n)
    if vowels < 2: score-=35
    if re.search(r"[^aeiouy]{4,}",n): score-=35
    if any(x in n for x in BANNED_ROOTS): score-=100
    if any(n.endswith(x) for x in BANNED_SUFFIXES): score-=100
    if re.search(r"(.)\1",n): score-=5
    return max(0,min(100,score))

def candidate():
    s=""
    for _ in range(random.choice([2,2,2,3])):
        s += random.choice(ONSETS)+random.choice(NUCLEI)+random.choice(CODAS)
    return re.sub(r"(.)\1+",r"\1",clean(s)).capitalize()

def generate(count=40, verify=False):
    seen=set(); rows=[]; attempts=0
    while len(rows)<count and attempts<20000:
        attempts+=1; n=candidate(); k=n.lower()
        if k in seen or not 5<=len(k)<=9: continue
        sc=score_name(n)
        if sc<72: continue
        row={"name":n,"score":sc,"length":len(k)}
        rows.append(row); seen.add(k)
    if verify and rows:
        checks=check_many(row["name"] for row in rows)
        for row, result in zip(rows, checks): row.update(result)
    return sorted(rows,key=lambda x:(not x.get("all_available",False),-x["score"],x["length"],x["name"]))

HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NameMachine</title><style>
:root{--bg:#090b0f;--card:#12161d;--line:#29313d;--text:#f5f7fa;--muted:#929cab;--accent:#ddb04d;--ok:#7ee787;--bad:#ff7b72;--unk:#d2a8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif}.shell{max-width:1380px;margin:auto;padding:26px 18px 70px;display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:22px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.18em;text-transform:uppercase}h1{font-size:clamp(42px,7vw,76px);margin:8px 0 6px;letter-spacing:-.055em}.sub{color:var(--muted);max-width:760px;line-height:1.5}.controls{display:grid;grid-template-columns:100px minmax(250px,1fr) auto;gap:10px;margin:24px 0}button,select,input,a.action{border:1px solid var(--line);border-radius:12px;padding:13px 15px;font-size:16px}button{background:var(--accent);color:#111;font-weight:800;cursor:pointer}button.secondary{background:var(--card);color:var(--text)}select,input{background:var(--card);color:var(--text)}.status{color:var(--muted);min-height:26px;margin:0 0 14px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:17px}.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.name{font-size:28px;font-weight:850;overflow-wrap:anywhere}.score{font-size:12px;border:1px solid var(--line);padding:6px 9px;border-radius:999px;color:var(--accent);white-space:nowrap}.meta{color:var(--muted);font-size:12px;margin:8px 0 12px;line-height:1.4}.check{display:flex;align-items:center;gap:7px;font-size:13px;margin:8px 0}.check a{margin-left:auto;color:var(--text)}.available{color:var(--ok)}.taken{color:var(--bad)}.unknown{color:var(--unk)}.pending{color:var(--muted)}.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.actions button,.actions a{font-size:12px;padding:8px 10px;text-decoration:none}.history{position:sticky;top:18px;height:calc(100vh - 36px);background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px;overflow:auto}.history-head{display:flex;align-items:center;justify-content:space-between}.history h2{margin:0;font-size:20px}.history-list{display:grid;gap:9px;margin-top:14px}.history-item{display:block;width:100%;text-align:left;background:#0d1117;color:var(--text);border:1px solid var(--line);padding:11px;border-radius:12px}.history-item b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.history-item span{display:block;color:var(--muted);font-size:11px;margin-top:5px}.warn{margin-top:22px;color:var(--muted);font-size:12px;line-height:1.5}
@media(max-width:860px){.shell{display:block}.controls{grid-template-columns:88px 1fr}.controls button{grid-column:1/-1}.history{position:static;height:auto;max-height:340px;margin:16px 0 20px}.grid{grid-template-columns:1fr}}.history-toggle{display:none}
</style></head><body><div class="shell"><main><div class="eyebrow">AI brand discovery · v4.2</div><h1>NameMachine</h1><p class="sub">Describe your project. AI generates names, then every candidate is checked live across .com and six major platforms.</p>
<div class="controls"><select id="aiCount" aria-label="Number of names"><option>5</option><option selected>10</option><option>20</option></select><input id="brief" maxlength="500" placeholder="Describe your project"><button id="generate" onclick="startSearch()">Generate + live check</button></div>
<div id="status" class="status"></div><div id="grid" class="grid"></div><p class="warn">AVAILABLE means the public check found evidence of availability. UNKNOWN means the platform blocked or obscured the check and must be opened manually. A result is not a trademark clearance.</p></main>
<aside id="history" class="history"><div class="history-head"><h2>Search history</h2><button class="secondary" onclick="clearHistory()">Clear</button></div><div id="historyList" class="history-list"></div></aside></div><button class="history-toggle" onclick="toggleHistory()">History</button>
<script>
const labels={com:'.com',instagram:'Instagram',telegram:'Telegram',tiktok:'TikTok',youtube:'YouTube',facebook:'Facebook',x:'X'};
let current=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function histories(){try{return JSON.parse(localStorage.getItem('namemachine_history')||'[]')}catch(e){return[]}}
function saveHistory(item){const all=histories().filter(x=>x.id!==item.id);all.unshift(item);localStorage.setItem('namemachine_history',JSON.stringify(all.slice(0,25)));renderHistory()}
function renderHistory(){const box=document.getElementById('historyList'),all=histories();box.innerHTML=all.length?all.map(x=>'<button class="history-item" data-id="'+esc(x.id)+'" onclick="loadHistory(this.dataset.id)"><b>'+esc(x.brief)+'</b><span>'+esc(x.created)+' · '+x.results.length+' names'+(x.done?' · complete':' · checking')+'</span></button>').join(''):'<div class="meta">No searches yet.</div>'}
function loadHistory(id){const x=histories().find(v=>v.id===id);if(!x)return;current=x;document.getElementById('brief').value=x.brief;renderResults();document.getElementById('status').textContent=x.done?'Loaded from history.':'This saved search was interrupted.';document.getElementById('history').classList.remove('open')}
function clearHistory(){localStorage.removeItem('namemachine_history');renderHistory()}
function toggleHistory(){document.getElementById('history').classList.toggle('open')}
async function copyName(name){await navigator.clipboard.writeText(name)}
function checkLine(key,o){if(!o)return '<div class="check pending">'+labels[key]+': checking…</div>';return '<div class="check">'+labels[key]+': <b class="'+esc(o.status)+'">'+esc(o.status.toUpperCase())+'</b><a target="_blank" rel="noopener" href="'+esc(o.url)+'">open</a></div>'}
function registerUrl(name,key,o){if(key==='com')return 'https://www.namecheap.com/domains/registration/results/?domain='+encodeURIComponent(name.toLowerCase()+'.com');return o&&o.url?o.url:'#'}
function card(x){const a=x.availability||{};const checks=Object.keys(labels).map(k=>checkLine(k,a[k])).join('');const free=x.available_count??0,total=x.total_resources??7;const actions='<div class="actions"><button class="secondary copy-btn" data-name="'+esc(x.name)+'">Copy name</button>'+Object.keys(labels).filter(k=>a[k]&&a[k].status==='available').map(k=>'<a class="action available" target="_blank" rel="noopener" href="'+registerUrl(x.name,k,a[k])+'">Claim '+labels[k]+'</a>').join('')+'</div>';return '<article class="card"><div class="top"><div class="name">'+esc(x.name)+'</div><div class="score">'+(x.checked?free+'/'+total+' free':'checking')+'</div></div><div class="meta">'+esc(x.pronunciation||'')+'</div><p>'+esc(x.reason||'')+'</p>'+checks+actions+'<div class="meta">Language risks: '+esc((x.language_risks||[]).join(', ')||'none identified')+'</div></article>'}
function renderResults(){if(!current)return;const rows=[...current.results].sort((a,b)=>(Number(b.checked)-Number(a.checked))||((b.available_count||0)-(a.available_count||0))||((a.unknown_count||7)-(b.unknown_count||7)));document.getElementById('grid').innerHTML=rows.map(card).join('')}
async function startSearch(){const brief=document.getElementById('brief').value.trim(),count=Number(document.getElementById('aiCount').value),status=document.getElementById('status'),btn=document.getElementById('generate');if(brief.length<3){status.textContent='Describe the project with at least 3 characters.';return}btn.disabled=true;status.textContent='AI is generating names…';try{const r=await fetch('/api/ai-names',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brief,count})});const names=await r.json();if(!r.ok)throw new Error(names.error||'AI request failed');current={id:Date.now().toString(),brief,created:new Date().toLocaleString(),done:false,results:names.map(x=>({...x,checked:false}))};saveHistory(current);renderResults();let finished=0;status.textContent='Generated '+names.length+' names. Checking 7 resources live…';await Promise.all(current.results.map(async row=>{try{const cr=await fetch('/api/check/'+encodeURIComponent(row.name)),data=await cr.json();if(cr.ok)Object.assign(row,data,{checked:true});else row.check_error=data.error||'Check failed'}catch(e){row.check_error='Network error'}finished++;status.textContent='Checked '+finished+' of '+current.results.length+' names';saveHistory(current);renderResults()}));current.done=true;saveHistory(current);status.textContent='Complete: '+current.results.length+' names checked across 7 resources.'}catch(e){status.textContent=e.message}finally{btn.disabled=false}}
renderHistory();
document.addEventListener('click',e=>{const b=e.target.closest('.copy-btn');if(b)copyName(b.dataset.name)});
if(window.matchMedia('(max-width:860px)').matches){document.querySelector('.controls').after(document.getElementById('history'))}
</script></body></html>"""

@app.get("/")
def home(): return render_template("index.html")

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/api/check/<name>")
def api_check(name):
    n=clean(name)
    if not 3<=len(n)<=30: return jsonify({"error":"Name must contain 3-30 latin letters"}),400
    row={"name":n.capitalize(),"score":score_name(n),"length":len(n)}; row.update(check_all(n)); return jsonify(row)

@app.post("/api/ai-names")
def api_ai_names():
    data=request.get_json(silent=True) or {}
    brief=str(data.get("brief","")).strip()
    if not 3<=len(brief)<=500:
        return jsonify({"error":"Brief must contain 3-500 characters"}),400
    try:
        count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError):
        count=10
    last_error=None
    for attempt in range(3):
        try:
            names=generate_ai_names(brief,count,clean_preferences(data.get("preferences")))
            for row in names:
                row["trademark"]=trademark_links(row["name"])
            return jsonify(names)
        except Exception as error:
            last_error=error
            app.logger.warning("AI names attempt %s failed: %s",attempt+1,type(error).__name__)
    app.logger.exception("AI names failed",exc_info=last_error)
    return jsonify({"error":"Temporary AI error. Please try again.","error_type":type(last_error).__name__}),503


@app.post("/api/ai-generate")
def api_ai_generate():
    data=request.get_json(silent=True) or {}; brief=str(data.get("brief","")).strip()
    if not 3<=len(brief)<=500: return jsonify({"error":"Brief must contain 3-500 characters"}),400
    try: count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError): count=10
    try:
        last_error = None
        for attempt in range(3):
            try:
                names=generate_ai_names(brief,count,clean_preferences(data.get("preferences")))
                break
            except Exception as error:
                last_error = error
                app.logger.warning("AI generation attempt %s failed: %s", attempt + 1, type(error).__name__)
        else:
            raise last_error
        checks=check_many(row["name"] for row in names)
        for row, availability in zip(names, checks):
            row.update(availability)
            row["trademark"]=trademark_links(row["name"])
        names.sort(key=lambda row: (-row["available_count"], row["unknown_count"], row["taken_count"], row["name"].lower()))
        return jsonify(names)
    except Exception as error:
        app.logger.exception("AI generation failed")
        return jsonify({"error":"Temporary AI error. Please tap Generate again.","error_type":type(error).__name__}),503

@app.get("/api/generate")
def api_generate():
    try: count=max(1,min(40,int(request.args.get("count",20))))
    except ValueError: count=20
    verify=request.args.get("verify","0").lower() in {"1","true","yes","on"}
    return jsonify(generate(count,verify))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
