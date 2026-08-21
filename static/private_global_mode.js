/* Private global-search overlay. Secrets never exist in browser assets. */
(() => {
  if (window.__nmPrivateGlobal) return;
  window.__nmPrivateGlobal = true;

  const baseStart = startSearch;
  const baseStop = stopSearch;
  const prompt = document.getElementById('prompt');
  const status = document.getElementById('status');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const composer = document.querySelector('.composer');
  const shell = document.querySelector('.shell');
  const brand = document.querySelector('.brand');
  const sessionTitle = document.getElementById('sessionTitle');
  const publicBrand = brand?.textContent || 'NameMachine';
  const publicPlaceholder = prompt?.getAttribute('placeholder') || '';

  let privateMode = false;
  let privateController = null;
  let state = null;

  const labels = {
    all:'Усе', grant:'Гранти', challenge:'Challenges', tender:'Тендери',
    auction:'Аукціони', funding:'Фінансування', benefit:'Допомога / виплати',
    business_aid:'Допомога бізнесу', research:'Research', government:'Державні', private:'Приватні'
  };

  function addStyle(){
    if(document.getElementById('nmPrivateGlobalStyle')) return;
    const s=document.createElement('style');s.id='nmPrivateGlobalStyle';s.textContent=`
      body.nm-private-global .composer>:not(textarea):not(.runbar){display:none!important}
      #nmPrivateGlobalPanel{display:none;margin-top:18px}body.nm-private-global #nmPrivateGlobalPanel{display:block}
      .nmpg-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.nmpg-toolbar select{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:12px;padding:10px;font:inherit}
      .nmpg-grid{display:grid;gap:11px}.nmpg-card{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:15px}.nmpg-title{font-size:18px;font-weight:850}.nmpg-desc{color:#cbd2da;font-size:13px;line-height:1.5;margin:8px 0}.nmpg-meta{display:flex;gap:7px;flex-wrap:wrap;color:var(--muted);font-size:11px}.nmpg-badge{border:1px solid var(--line);border-radius:999px;padding:4px 7px}.nmpg-badge.official{border-color:var(--ok);color:var(--ok)}.nmpg-link{display:inline-block;margin-top:10px;color:var(--text);font-size:12px}.nmpg-empty{border:1px dashed var(--line);border-radius:16px;padding:24px;color:var(--muted);text-align:center}.nmpg-note{margin-top:10px;color:var(--muted);font-size:11px;line-height:1.45}.nmpg-plan{margin-top:10px;color:var(--muted);font-size:11px}.nmpg-plan code{display:block;white-space:pre-wrap;margin-top:6px}
    `;document.head.appendChild(s);
  }

  function panel(){
    let p=document.getElementById('nmPrivateGlobalPanel');if(p)return p;
    p=document.createElement('section');p.id='nmPrivateGlobalPanel';
    p.innerHTML='<div class="nmpg-toolbar"><select id="nmPrivateCategory"></select><select id="nmPrivateCountry"></select></div><div id="nmPrivateResults" class="nmpg-grid"><div class="nmpg-empty">Введи глобальний пошуковий запит.</div></div><div id="nmPrivateTruth" class="nmpg-note"></div><details id="nmPrivatePlan" class="nmpg-plan" hidden><summary>Пошуковий тунель</summary><code></code></details>';
    composer?.insertAdjacentElement('afterend',p);return p;
  }

  function controls(search={}){
    const cat=document.getElementById('nmPrivateCategory'),country=document.getElementById('nmPrivateCountry');if(!cat||!country)return;
    const cats=['all',...(search.categories||[]).filter(x=>x!=='all')].filter((x,i,a)=>labels[x]&&a.indexOf(x)===i);
    cat.replaceChildren(...cats.map(x=>{const o=document.createElement('option');o.value=x;o.textContent=labels[x];return o;}));
    const eu=document.createElement('option');eu.value='EU';eu.textContent='Весь ЄС';
    const opts=[eu,...(search.countries||[]).map(x=>{const o=document.createElement('option');o.value=x.code;o.textContent=`${x.code} · ${x.name}`;return o;})];country.replaceChildren(...opts);
  }

  function hidePublic(on){
    if(!shell)return;const p=panel();
    for(const child of [...shell.children]){
      if(child===p||child===composer||child.classList.contains('topbar'))continue;
      if(on){if(!child.hasAttribute('data-nmpg-display'))child.setAttribute('data-nmpg-display',child.style.display||'');child.style.display='none';}
      else if(child.hasAttribute('data-nmpg-display')){child.style.display=child.getAttribute('data-nmpg-display')||'';child.removeAttribute('data-nmpg-display');}
    }
  }

  function mode(on,payload=null){
    privateMode=!!on;state=payload||state;document.body.classList.toggle('nm-private-global',privateMode);hidePublic(privateMode);
    if(privateMode){if(brand)brand.textContent='Global Search';if(sessionTitle)sessionTitle.textContent='Private mode';if(prompt){prompt.value='';prompt.placeholder='Шукай гранти, challenges, тендери, аукціони, допомогу, фінансування, research або іншу перевірювану можливість…';}if(startBtn)startBtn.textContent='Знайти';if(status)status.textContent='Глобальний пошук активний.';controls(state?.search||{});panel();}
    else {if(privateController)privateController.abort();privateController=null;if(brand)brand.textContent=publicBrand;if(sessionTitle)sessionTitle.textContent=current?.title||'Нова сесія';if(prompt){prompt.value=current?.promptHistory?.at?.(-1)?.text||'';prompt.placeholder=publicPlaceholder;}if(startBtn)startBtn.textContent=current?.results?.length?'Continue':'Start';if(status)status.textContent='Опиши задачу і запусти пошук.';try{render();}catch(_){}}
  }

  function commandLike(v){const t=String(v||'').trim();return t.length>=40&&t.length<=512&&!/\s/u.test(t);}
  async function command(v){
    if(!commandLike(v))return false;
    try{const r=await fetch('/api/private-mode/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:v})});if(!r.ok)return false;const p=await r.json();if(!p?.handled)return false;if(prompt)prompt.value='';if(p.mode==='private'){const s=await fetch('/api/private-mode/state',{cache:'no-store'}).then(x=>x.ok?x.json():null).catch(()=>null);mode(true,s||{mode:'private'});}else mode(false,{mode:'public'});return true;}catch(_){return false;}
  }

  function textNode(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=String(text??'');return n;}
  function renderRows(payload){
    const box=document.getElementById('nmPrivateResults'),truth=document.getElementById('nmPrivateTruth'),plan=document.getElementById('nmPrivatePlan');if(!box)return;box.replaceChildren();const rows=Array.isArray(payload?.results)?payload.results:[];
    if(!rows.length){box.appendChild(textNode('div','nmpg-empty',payload?.provider_status==='unconfigured'?'Приватний режим працює, але live web-provider ще не налаштований.':'За цим запитом результатів не знайдено.'));}
    for(const row of rows){const card=textNode('article','nmpg-card','');card.appendChild(textNode('div','nmpg-title',row.title||'Без назви'));if(row.description)card.appendChild(textNode('div','nmpg-desc',row.description));const meta=textNode('div','nmpg-meta','');if(row.official_source)meta.appendChild(textNode('span','nmpg-badge official','OFFICIAL SOURCE'));meta.appendChild(textNode('span','nmpg-badge',labels[row.category]||row.category||'web'));if(row.source_name)meta.appendChild(textNode('span','nmpg-badge',row.source_name));if(Number.isFinite(Number(row.retrieval_score)))meta.appendChild(textNode('span','nmpg-badge',`relevance ${Number(row.retrieval_score)}/100`));card.appendChild(meta);if(row.url){const a=textNode('a','nmpg-link','Відкрити джерело ↗');a.href=row.url;a.target='_blank';a.rel='noopener noreferrer';card.appendChild(a);}box.appendChild(card);}
    if(truth)truth.textContent=payload?.truth_note||'';const queries=Array.isArray(payload?.search_plan)?payload.search_plan:[];if(plan){plan.hidden=!queries.length;const code=plan.querySelector('code');if(code)code.textContent=queries.join('\n\n');}
  }

  async function privateSearch(){
    const q=String(prompt?.value||'').replace(/\s+/g,' ').trim();if(q.length<2){if(status)status.textContent='Введи пошуковий запит.';return;}if(privateController)return;privateController=new AbortController();if(startBtn)startBtn.disabled=true;if(stopBtn)stopBtn.disabled=false;if(status)status.textContent='Шукаю по глобальному тунелю…';
    try{const category=document.getElementById('nmPrivateCategory')?.value||'all',country=document.getElementById('nmPrivateCountry')?.value||'EU';const r=await fetch('/api/private-mode/search',{method:'POST',signal:privateController.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,category,country})});let p=null;try{p=await r.json();}catch(_){}if(r.status===404){mode(false,{mode:'public'});return;}if(!r.ok)throw new Error(p?.error||`HTTP ${r.status}`);renderRows(p||{});if(status)status.textContent=`Готово · ${(p?.results||[]).length} результатів · ${p?.provider_status||'complete'}`;}catch(e){if(status)status.textContent=e?.name==='AbortError'?'Глобальний пошук зупинено.':(e?.message||'Помилка глобального пошуку.');}finally{privateController=null;if(startBtn)startBtn.disabled=false;if(stopBtn)stopBtn.disabled=true;}
  }

  startSearch=async function(){const v=String(prompt?.value||'').trim();if(await command(v))return;if(privateMode)return privateSearch();return baseStart();};
  stopSearch=function(){if(privateMode){privateController?.abort();return;}return baseStop();};

  addStyle();panel();fetch('/api/private-mode/state',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(p=>{if(p?.mode==='private')mode(true,p);}).catch(()=>{});
})();
