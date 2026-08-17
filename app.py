import os, random, re
from flask import Flask, request, jsonify, render_template_string

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

def generate(count=40):
    seen=set(); rows=[]; attempts=0
    while len(rows)<count and attempts<20000:
        attempts+=1; n=candidate(); k=n.lower()
        if k in seen or not 5<=len(k)<=9: continue
        sc=score_name(n)
        if sc<72: continue
        seen.add(k)
        rows.append({"name":n,"score":sc,"length":len(k),
          "domain_query":"https://www.google.com/search?q=%22"+k+".com%22",
          "instagram":"https://www.instagram.com/"+k+"/",
          "telegram":"https://t.me/"+k,
          "note":"Availability NOT verified"})
    return sorted(rows,key=lambda x:(-x["score"],x["length"],x["name"]))

HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NameMachine</title><style>
:root{--bg:#090b0f;--card:#12161d;--line:#262d38;--text:#f5f7fa;--muted:#929cab;--accent:#d6a84b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif}
.wrap{max-width:980px;margin:auto;padding:28px 18px 70px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.18em;text-transform:uppercase}
h1{font-size:clamp(38px,8vw,72px);margin:8px 0 6px;letter-spacing:-.05em}.sub{color:var(--muted);max-width:720px;line-height:1.5}
.controls{display:flex;gap:10px;margin:24px 0;flex-wrap:wrap}button,select{border:1px solid var(--line);border-radius:12px;padding:13px 16px;font-size:16px}
button{background:var(--accent);color:#111;font-weight:800}select{background:var(--card);color:var(--text)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:17px}
.top{display:flex;justify-content:space-between;align-items:center}.name{font-size:26px;font-weight:850}.score{font-size:12px;border:1px solid var(--line);padding:5px 8px;border-radius:999px;color:var(--accent)}
.meta{color:var(--muted);font-size:12px;margin:8px 0 13px}.links{display:flex;gap:10px;flex-wrap:wrap}a{color:var(--text);font-size:13px}.warn{margin-top:22px;color:var(--muted);font-size:12px;line-height:1.5}
</style></head><body><main class="wrap"><div class="eyebrow">Brand discovery engine · v2.0</div><h1>NameMachine</h1>
<p class="sub">Short, international, product-agnostic candidates for a global community-to-physical-product brand.</p>
<div class="controls"><select id="count"><option>20</option><option selected>40</option><option>80</option></select><button onclick="go()">Generate names</button></div>
<div id="grid" class="grid"></div><p class="warn">Scores are internal heuristics, not legal validation. Domain, social-handle and trademark availability must be verified independently.</p>
</main><script>
async function go(){const g=document.getElementById('grid');g.innerHTML='<div class="meta">Generating…</div>';const n=document.getElementById('count').value;
const r=await fetch('/api/generate?count='+n),d=await r.json();g.innerHTML=d.map(x=>`<article class="card"><div class="top"><div class="name">${x.name}</div><div class="score">${x.score}/100</div></div><div class="meta">${x.length} letters · ${x.note}</div><div class="links"><a target="_blank" href="${x.domain_query}">.com search</a><a target="_blank" href="${x.instagram}">Instagram</a><a target="_blank" href="${x.telegram}">Telegram</a></div></article>`).join('')}go();
</script></body></html>"""

@app.get("/")
def home(): return render_template_string(HTML)

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/api/generate")
def api_generate():
    try: count=max(1,min(100,int(request.args.get("count",40))))
    except ValueError: count=40
    return jsonify(generate(count))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
