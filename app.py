import os, random, re
from flask import Flask, request, jsonify, render_template_string
from availability import check_all, check_many
from ai_engine import generate_ai_names, trademark_links

app = Flask(__name__)

BANNED_ROOTS = {"idea","product","make","maker","creat","build","factory","forge","foundry","lab","studio","shop","store","market","communit","crowd","vote","preorder","drop","pin","merch","object","reality","real","ai","tech"}
BANNED_SUFFIXES = {"ora","ova","ira","iva","eya","aya","io","ly","ify","verse","works","base","hub","flow","labs"}
ONSETS = ["v","n","m","r","l","s","t","k","d","f","z","b","p","c","g","h","br","cr","dr","fr","gr","kr","pr","tr","vr","st","sk","cl","fl","pl"]
NUCLEI = ["a","e","i","o","u","ae","ai","ea","eo","oa","ui"]
CODAS = ["","n","r","s","l","m","x","v","d","t","k"]

def clean(s): return re.sub(r"[^a-z]", "", s.lower())

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
:root{--bg:#090b0f;--card:#12161d;--line:#262d38;--text:#f5f7fa;--muted:#929cab;--accent:#d6a84b;--ok:#7ee787;--bad:#ff7b72;--unk:#d2a8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif}.wrap{max-width:980px;margin:auto;padding:28px 18px 70px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.18em;text-transform:uppercase}h1{font-size:clamp(38px,8vw,72px);margin:8px 0 6px;letter-spacing:-.05em}.sub{color:var(--muted);max-width:720px;line-height:1.5}.controls{display:flex;gap:10px;margin:24px 0;flex-wrap:wrap}button,select,label,input{border:1px solid var(--line);border-radius:12px;padding:13px 16px;font-size:16px}button{background:var(--accent);color:#111;font-weight:800}select,label,input{background:var(--card);color:var(--text)}input{flex:1;min-width:250px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:17px}.top{display:flex;justify-content:space-between;align-items:center}.name{font-size:26px;font-weight:850}.score{font-size:12px;border:1px solid var(--line);padding:5px 8px;border-radius:999px;color:var(--accent)}.meta{color:var(--muted);font-size:12px;margin:8px 0 13px}.check{font-size:13px;margin:7px 0}.available{color:var(--ok)}.taken{color:var(--bad)}.unknown{color:var(--unk)}a{color:var(--text)}.warn{margin-top:22px;color:var(--muted);font-size:12px;line-height:1.5}
</style></head><body><main class="wrap"><div class="eyebrow">Brand discovery engine · v3.0</div><h1>NameMachine</h1><p class="sub">Generate names and optionally verify .com, Instagram and Telegram availability.</p><div class="controls"><select id="count"><option>10</option><option selected>20</option><option>40</option></select><label><input id="verify" type="checkbox" checked> Live checks</label><button onclick="go()">Generate names</button></div><div class="controls"><input id="brief" maxlength="500" placeholder="Describe the brand"><button onclick="aiGo()">AI generate</button></div><div id="grid" class="grid"></div><p class="warn">.com is checked via Verisign RDAP. Instagram/Telegram checks are best-effort and may return UNKNOWN because of anti-bot controls. Always do a final manual and trademark check.</p></main><script>
function line(label,o){if(!o)return '';return `<div class="check">${label}: <b class="${o.status}">${o.status.toUpperCase()}</b> · <a target="_blank" href="${o.url}">open</a></div>`}
async function go(){const g=document.getElementById('grid');g.innerHTML='<div class="meta">Generating…</div>';const n=document.getElementById('count').value,v=document.getElementById('verify').checked?'1':'0';const r=await fetch('/api/generate?count='+n+'&verify='+v),d=await r.json();g.innerHTML=d.map(x=>`<article class="card"><div class="top"><div class="name">${x.name}</div><div class="score">${x.score}/100</div></div><div class="meta">${x.length} letters${x.all_available?' · ALL AVAILABLE':''}</div>${x.availability?line('.com',x.availability.com)+line('Instagram',x.availability.instagram)+line('Telegram',x.availability.telegram):'<div class="meta">Availability not checked</div>'}</article>`).join('')}go();
async function aiGo(){const g=document.getElementById('grid'),b=document.getElementById('brief').value.trim();if(!b){g.innerHTML='<div class="meta">Describe the brand first.</div>';return}g.innerHTML='<div class="meta">AI generation…</div>';try{const r=await fetch('/api/ai-generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brief:b,count:10})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');g.innerHTML=d.map(function(x){return '<article class="card"><div class="name">'+x.name+'</div><div class="meta">'+x.pronunciation+'</div><p>'+x.reason+'</p><div class="meta">Language risks: '+(x.language_risks.length?x.language_risks.join(', '):'none identified')+'</div></article>'}).join('')}catch(e){g.innerHTML='<div class="meta">'+e.message+'</div>'}}
</script></body></html>"""

@app.get("/")
def home(): return render_template_string(HTML)

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/api/check/<name>")
def api_check(name):
    n=clean(name)
    if not 3<=len(n)<=30: return jsonify({"error":"Name must contain 3-30 latin letters"}),400
    row={"name":n.capitalize(),"score":score_name(n),"length":len(n)}; row.update(check_all(n)); return jsonify(row)

@app.post("/api/ai-generate")
def api_ai_generate():
    data=request.get_json(silent=True) or {}; brief=str(data.get("brief","")).strip()
    if not 3<=len(brief)<=500: return jsonify({"error":"Brief must contain 3-500 characters"}),400
    try: count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError): count=10
    try:
        names=generate_ai_names(brief,count)
        for row in names: row["trademark"]=trademark_links(row["name"])
        return jsonify(names)
    except Exception:
        app.logger.exception("AI generation failed")
        return jsonify({"error":"AI generation is temporarily unavailable"}),503

@app.get("/api/generate")
def api_generate():
    try: count=max(1,min(40,int(request.args.get("count",20))))
    except ValueError: count=20
    verify=request.args.get("verify","0").lower() in {"1","true","yes","on"}
    return jsonify(generate(count,verify))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
