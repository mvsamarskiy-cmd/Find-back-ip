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

  const PAGE_SIZE = 20;
  let privateMode = false;
  let privateController = null;
  let state = null;
  let latestPayload = null;
  let currentPage = 1;
  let sortMode = 'practical';
  let localType = 'all';

  const labels = {
    all:'Усі можливості', grant:'Гранти', subsidy:'Субсидії', public_aid:'Державна допомога',
    eu_fund:'Фонди ЄС', regional_fund:'Регіональні фонди', competition:'Конкурси', prize:'Грошові призи',
    challenge:'Челенджі', bounty:'Баунті', accelerator:'Акселератори', incubator:'Інкубатори',
    scholarship:'Стипендії', fellowship:'Fellowship / дослідницькі програми', research_funding:'Фінансування досліджень',
    corporate_open_call:'Корпоративні open call', paid_open_call:'Оплачувані open call', vc:'Venture Capital',
    angel:'Бізнес-ангели', equity_program:'Equity-програми', crowdfunding:'Краудфандинг',
    preferential_loan:'Пільгові кредити', guarantee:'Гарантії', leasing:'Лізинг', factoring:'Факторинг',
    equipment_financing:'Фінансування обладнання', tax_relief:'Податкові пільги', reimbursement:'Відшкодування',
    employment_incentive:'Підтримка працевлаштування', training_support:'Фінансування навчання',
    export_support:'Підтримка експорту', innovation_voucher:'Інноваційні ваучери', green_energy_support:'Енергоефективність / green support',
    procurement:'Тендери / закупівлі', tender:'Тендери', job_contract:'Робота / контракт', subcontract:'Субпідряд',
    supplier_demand:'Пошук постачальників', business_for_sale:'Бізнеси на продаж', asset_sale:'Продаж активів',
    liquidation:'Ліквідаційні активи', real_estate_opportunity:'Нерухомість', public_auction:'Публічні аукціони',
    auction:'Аукціони', classified_offer:'Оголошення', wholesale_closeout:'Оптові залишки / closeout',
    import_export_gap:'Імпортно-експортні можливості', market_dislocation:'Цінові / ринкові аномалії',
    off_market_public:'Публічні off-market можливості', other_monetizable_signal:'Інші монетизовані сигнали',
    funding:'Фінансування', benefit:'Допомога / виплати', business_aid:'Допомога бізнесу', research:'Дослідження',
    government:'Державні', private:'Приватні', other:'Інше'
  };
  const familyLabels = {
    funding:'Фінансування без повернення / конкурси', capital:'Капітал / інвестори', finance:'Кредити та фінансові інструменти',
    savings:'Економія / відшкодування', revenue:'Контракти та виручка', assets:'Активи', local:'Локальні пропозиції',
    markets:'Ринкові можливості', off_market:'Публічні off-market', other:'Інше'
  };
  const applicantLabels = {
    individual:'фізособа', startup:'стартап', sme:'МСП', company:'компанія', ngo:'NGO',
    researcher:'дослідник', research_org:'дослідницька організація', student:'студент', public_body:'державна установа'
  };
  const statusLabels = {
    open:'ВІДКРИТО', open_or_upcoming:'ВІДКРИТО / НЕЗАБАРОМ', upcoming:'НЕЗАБАРОМ', closed:'ЗАКРИТО', unknown:'СТАТУС НЕВІДОМИЙ'
  };
  const eligibilityLabels = {
    eligible_candidate:'попередньо відповідає відомим умовам', possible:'можливо підходить — бракує даних',
    ineligible:'не відповідає одній або більше відомим умовам', unknown:'відповідність ще не визначена'
  };

  function addStyle(){
    if(document.getElementById('nmPrivateGlobalStyle')) return;
    const s=document.createElement('style');s.id='nmPrivateGlobalStyle';s.textContent=`
      body.nm-private-global .composer>:not(textarea):not(.runbar){display:none!important}
      #nmPrivateGlobalPanel{display:none;margin-top:18px}body.nm-private-global #nmPrivateGlobalPanel{display:block}
      .nmpg-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;position:sticky;top:0;z-index:4;background:var(--bg);padding:7px 0}
      .nmpg-toolbar select,.nmpg-toolbar button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:12px;padding:10px;font:inherit}.nmpg-toolbar button{cursor:pointer}.nmpg-toolbar button:disabled{opacity:.45;cursor:default}
      .nmpg-transport{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--muted);font-size:11px}.nmpg-transport.on{border-color:var(--ok);color:var(--ok)}
      .nmpg-viewport{max-height:calc(100vh - 250px);min-height:220px;overflow-y:auto;overscroll-behavior:contain;scroll-behavior:smooth;padding-right:4px;scrollbar-gutter:stable}
      .nmpg-grid{display:grid;gap:12px;padding-bottom:10px}.nmpg-card{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:15px}.nmpg-card.high{border-color:rgba(90,220,150,.48)}.nmpg-card.blocked{opacity:.72}
      .nmpg-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.nmpg-title-wrap{display:flex;gap:8px;align-items:flex-start;min-width:0}.nmpg-index{color:var(--muted);font-size:12px;min-width:34px;padding-top:3px}.nmpg-title{font-size:18px;font-weight:850;line-height:1.28}.nmpg-fit{min-width:58px;text-align:center;border:1px solid var(--line);border-radius:14px;padding:6px 8px;font-weight:800}.nmpg-fit.high{border-color:var(--ok);color:var(--ok)}.nmpg-fit.blocked{color:#e7868f}
      .nmpg-desc{color:#d5dbe2;font-size:13px;line-height:1.55;margin:10px 0}.nmpg-original{margin:8px 0;color:var(--muted);font-size:11px}.nmpg-original p{line-height:1.45}
      .nmpg-meta,.nmpg-facts{display:flex;gap:7px;flex-wrap:wrap;color:var(--muted);font-size:11px}.nmpg-facts{margin-top:9px}.nmpg-badge{border:1px solid var(--line);border-radius:999px;padding:4px 7px}.nmpg-badge.official,.nmpg-badge.verified{border-color:var(--ok);color:var(--ok)}.nmpg-badge.closed{border-color:#82434a;color:#e7868f}.nmpg-badge.open{border-color:var(--ok);color:var(--ok)}
      .nmpg-money{font-size:16px;font-weight:800;color:var(--text);margin-top:8px}.nmpg-evidence{margin-top:9px;padding-top:9px;border-top:1px solid var(--line);font-size:11px;color:var(--muted);display:grid;gap:4px}.nmpg-blocker{color:#e7868f}.nmpg-link{display:inline-block;margin-top:10px;color:var(--text);font-size:12px}.nmpg-empty{border:1px dashed var(--line);border-radius:16px;padding:24px;color:var(--muted);text-align:center}.nmpg-note{margin-top:10px;color:var(--muted);font-size:11px;line-height:1.45}.nmpg-plan{margin-top:10px;color:var(--muted);font-size:11px}.nmpg-plan code{display:block;white-space:pre-wrap;margin-top:6px}
      .nmpg-pages{display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;margin:10px 0}.nmpg-pages button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 11px}.nmpg-page-label{color:var(--muted);font-size:12px}.nmpg-result-count{color:var(--muted);font-size:11px;margin-left:auto}
      @media(max-width:640px){.nmpg-head{gap:8px}.nmpg-title{font-size:17px}.nmpg-fit{min-width:52px}.nmpg-toolbar{position:static}.nmpg-viewport{max-height:calc(100vh - 215px)}.nmpg-result-count{width:100%;margin-left:0}}
    `;document.head.appendChild(s);
  }

  function panel(){
    let p=document.getElementById('nmPrivateGlobalPanel');if(p)return p;
    p=document.createElement('section');p.id='nmPrivateGlobalPanel';
    p.innerHTML=`<div class="nmpg-toolbar">
      <select id="nmPrivateCategory" aria-label="Категорія пошуку"></select>
      <select id="nmPrivateCountry" aria-label="Країна"></select>
      <select id="nmPrivateType" aria-label="Тип можливості"></select>
      <select id="nmPrivateSort" aria-label="Сортування">
        <option value="practical">Практичність ↓</option>
        <option value="relevance">Релевантність ↓</option>
        <option value="current">Актуальні спочатку</option>
        <option value="deadline">Найближчий дедлайн</option>
        <option value="observed">Остання перевірка ↓</option>
      </select>
      <button id="nmScrollUp" type="button" title="До початку списку">↑ Вгору</button>
      <button id="nmScrollDown" type="button" title="До кінця сторінки">↓ Вниз</button>
      <span id="nmTorState" class="nmpg-transport">Tor: авто</span>
      <span id="nmResultCount" class="nmpg-result-count"></span>
    </div>
    <div id="nmPrivateViewport" class="nmpg-viewport"><div id="nmPrivateResults" class="nmpg-grid"><div class="nmpg-empty">Введи глобальний пошуковий запит.</div></div></div>
    <div id="nmPrivatePages" class="nmpg-pages"></div>
    <div id="nmPrivateTruth" class="nmpg-note"></div>
    <details id="nmPrivatePlan" class="nmpg-plan" hidden><summary>Пошуковий тунель</summary><code></code></details>`;
    composer?.insertAdjacentElement('afterend',p);
    p.querySelector('#nmPrivateSort')?.addEventListener('change',e=>{sortMode=e.target.value;currentPage=1;renderCurrent();});
    p.querySelector('#nmPrivateType')?.addEventListener('change',e=>{localType=e.target.value;currentPage=1;renderCurrent();});
    p.querySelector('#nmScrollUp')?.addEventListener('click',()=>p.querySelector('#nmPrivateViewport')?.scrollTo({top:0,behavior:'smooth'}));
    p.querySelector('#nmScrollDown')?.addEventListener('click',()=>{const v=p.querySelector('#nmPrivateViewport');v?.scrollTo({top:v.scrollHeight,behavior:'smooth'});});
    return p;
  }

  function moneyTypes(){
    return [
      'grant','subsidy','public_aid','eu_fund','regional_fund','competition','prize','challenge','bounty','accelerator','incubator','scholarship','fellowship','research_funding','corporate_open_call','paid_open_call','vc','angel','equity_program','crowdfunding','preferential_loan','guarantee','leasing','factoring','equipment_financing','tax_relief','reimbursement','employment_incentive','training_support','export_support','innovation_voucher','green_energy_support','procurement','job_contract','subcontract','supplier_demand','business_for_sale','asset_sale','liquidation','real_estate_opportunity','public_auction','classified_offer','wholesale_closeout','import_export_gap','market_dislocation','off_market_public','other_monetizable_signal'
    ];
  }

  function controls(search={}){
    const cat=document.getElementById('nmPrivateCategory'),country=document.getElementById('nmPrivateCountry'),type=document.getElementById('nmPrivateType');if(!cat||!country||!type)return;
    const cats=['all',...(search.categories||[])].filter((x,i,a)=>labels[x]&&a.indexOf(x)===i);
    cat.replaceChildren(...cats.map(x=>{const o=document.createElement('option');o.value=x;o.textContent=labels[x];return o;}));
    const eu=document.createElement('option');eu.value='EU';eu.textContent='Весь ЄС';
    const opts=[eu,...(search.countries||[]).map(x=>{const o=document.createElement('option');o.value=x.code;o.textContent=`${x.code} · ${x.name}`;return o;})];country.replaceChildren(...opts);
    const typeOptions=[['all','Усі 47 типів'],...moneyTypes().map(x=>[x,labels[x]||x])];
    type.replaceChildren(...typeOptions.map(([value,text])=>{const o=document.createElement('option');o.value=value;o.textContent=text;return o;}));
    type.value=localType;
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
    if(privateMode){if(brand)brand.textContent='Global Search';if(sessionTitle)sessionTitle.textContent='Private mode';if(prompt){prompt.value='';prompt.placeholder='Шукай гранти, фінансування, тендери, активи або іншу матеріальну можливість…';}if(startBtn)startBtn.textContent='Знайти';if(stopBtn)stopBtn.textContent='Стоп';if(status)status.textContent='Opportunity Intelligence активний.';controls(state?.search||{});panel();}
    else {if(privateController)privateController.abort();privateController=null;if(brand)brand.textContent=publicBrand;if(sessionTitle)sessionTitle.textContent=current?.title||'Нова сесія';if(prompt){prompt.value=current?.promptHistory?.at?.(-1)?.text||'';prompt.placeholder=publicPlaceholder;}if(startBtn)startBtn.textContent=current?.results?.length?'Continue':'Start';if(status)status.textContent='Опиши задачу і запусти пошук.';try{render();}catch(_){}}
  }

  function commandLike(v){
    const t=String(v||'').trim();
    if(t.length<8||t.length>512)return false;
    return !/\s/u.test(t)||t.length>=24;
  }
  async function command(v){
    if(!commandLike(v))return false;
    try{const r=await fetch('/api/private-mode/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:v})});if(!r.ok)return false;const p=await r.json();if(!p?.handled)return false;if(prompt)prompt.value='';if(p.mode==='private'){const s=await fetch('/api/private-mode/state',{cache:'no-store'}).then(x=>x.ok?x.json():null).catch(()=>null);mode(true,s||{mode:'private'});}else mode(false,{mode:'public'});return true;}catch(_){return false;}
  }

  function textNode(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=String(text??'');return n;}
  function amountText(amount){
    if(!amount?.currency||!Number.isFinite(Number(amount?.max)))return null;
    const nf=new Intl.NumberFormat('uk-UA',{maximumFractionDigits:0});
    const high=nf.format(Number(amount.max));
    const low=Number.isFinite(Number(amount.min))?nf.format(Number(amount.min)):null;
    return low?`${low}–${high} ${amount.currency}`:`до ${high} ${amount.currency}`;
  }
  function fact(meta,text,cls=''){if(text)meta.appendChild(textNode('span',`nmpg-badge ${cls}`.trim(),text));}
  function recordOf(row){return row?.money_record||row?.moneyRecord||null;}
  function opportunityOf(row){return row?.opportunity||recordOf(row)||{};}
  function safeDate(value){const t=Date.parse(String(value||''));return Number.isFinite(t)?t:null;}
  function deadlineOf(row){const r=recordOf(row),o=opportunityOf(row);return r?.deadline?.date||o?.deadline?.date||row?.deadline?.date||null;}
  function observedAt(row){const r=recordOf(row),o=opportunityOf(row);return r?.direct_verification?.observed_at||r?.verification?.checked_at||o?.verification?.checked_at||row?.verification?.checked_at||row?.retrieved_at||null;}
  function practicalScore(row){const r=recordOf(row);return Number(r?.practical_ranking?.score??row?.fit?.score??row?.retrieval_score??0)||0;}
  function freshnessScore(row){const r=recordOf(row);const c=r?.practical_ranking?.components||{};return Number(c.status_freshness??c.freshness??r?.freshness_score??0)||0;}
  function currentScore(row){
    const r=recordOf(row),o=opportunityOf(row);const statusValue=r?.status?.value||o?.status?.value||row?.status?.value||'unknown';
    return (r?.current_call_verified?1000:0)+(r?.source_observed?200:0)+(statusValue==='open'?150:statusValue==='open_or_upcoming'?120:statusValue==='upcoming'?80:statusValue==='closed'?-500:0)+freshnessScore(row);
  }
  function typeOf(row){return recordOf(row)?.opportunity_type||row?.category||'other';}

  function ukOpportunityDescription(row){
    const r=recordOf(row),o=opportunityOf(row),type=typeOf(row),family=r?.family||row?.money_family_hint;
    const parts=[];
    parts.push(`Це ${String(labels[type]||type||'матеріальна можливість').toLowerCase()}${family&&familyLabels[family]?` у напрямі «${familyLabels[family]}»`:''}.`);
    const counterparty=r?.funder_or_counterparty||o?.funder_or_counterparty||row?.source_name;
    if(counterparty)parts.push(`Організатор або джерело: ${counterparty}.`);
    const amount=amountText(r?.amount||o?.amount);if(amount)parts.push(`Заявлена або знайдена сума: ${amount}.`);
    const deadline=deadlineOf(row);if(deadline)parts.push(`Дедлайн: ${deadline}.`);
    const eligibility=r?.eligibility_state||o?.eligibility_state;if(eligibility)parts.push(`Попередня відповідність: ${eligibilityLabels[eligibility]||eligibility}.`);
    if(r?.current_call_verified)parts.push('Система безпосередньо перевірила сторінку та знайшла ознаки актуального або майбутнього набору.');
    else if(r?.source_observed)parts.push('Першоджерело безпосередньо переглянуте системою, але поточна доступність ще не гарантована.');
    else parts.push('Це кандидат, знайдений пошуком; перед дією перевір умови в першоджерелі.');
    return parts.join(' ');
  }

  function rowComparator(a,b){
    if(sortMode==='relevance')return (Number(b?.retrieval_score)||0)-(Number(a?.retrieval_score)||0);
    if(sortMode==='current')return currentScore(b)-currentScore(a)||practicalScore(b)-practicalScore(a);
    if(sortMode==='deadline'){
      const da=safeDate(deadlineOf(a)),db=safeDate(deadlineOf(b));
      if(da===null&&db===null)return practicalScore(b)-practicalScore(a);if(da===null)return 1;if(db===null)return -1;return da-db;
    }
    if(sortMode==='observed'){
      const da=safeDate(observedAt(a))||0,db=safeDate(observedAt(b))||0;return db-da||practicalScore(b)-practicalScore(a);
    }
    return practicalScore(b)-practicalScore(a)||(Number(b?.retrieval_score)||0)-(Number(a?.retrieval_score)||0);
  }

  function filteredRows(){
    const rows=Array.isArray(latestPayload?.results)?latestPayload.results.slice():[];
    return rows.filter(row=>localType==='all'||typeOf(row)===localType).sort(rowComparator);
  }

  function resultCard(row,index){
    const opp=opportunityOf(row),fit=row?.fit||{},verification=opp.verification||row?.verification||{},eligibility=opp.eligibility||{},statusInfo=opp.status||{};
    const card=textNode('article',`nmpg-card ${fit.label||''}`.trim(),'');
    const head=textNode('div','nmpg-head','');const wrap=textNode('div','nmpg-title-wrap','');wrap.appendChild(textNode('span','nmpg-index',`#${index}`));wrap.appendChild(textNode('div','nmpg-title',row.title||'Без назви'));head.appendChild(wrap);
    if(Number.isFinite(Number(fit.score)))head.appendChild(textNode('div',`nmpg-fit ${fit.label||''}`.trim(),`${Number(fit.score)}%`));card.appendChild(head);
    card.appendChild(textNode('div','nmpg-desc',ukOpportunityDescription(row)));
    if(row.description){const details=textNode('details','nmpg-original','');details.appendChild(textNode('summary','', 'Оригінальний фрагмент джерела'));details.appendChild(textNode('p','',row.description));card.appendChild(details);}
    const meta=textNode('div','nmpg-meta','');
    if(row.official_source)fact(meta,'ОФІЦІЙНЕ ДЖЕРЕЛО','official');
    if(verification.source_verified||recordOf(row)?.source_observed)fact(meta,'ДЖЕРЕЛО ПЕРЕВІРЕНО','verified');
    if(recordOf(row)?.current_call_verified)fact(meta,'АКТУАЛЬНИЙ НАБІР ПЕРЕВІРЕНО','verified');
    fact(meta,labels[typeOf(row)]||typeOf(row)||'web');
    if(row.source_name)fact(meta,row.source_name);
    const statusValue=statusInfo.value||recordOf(row)?.status?.value||'unknown';fact(meta,statusLabels[statusValue]||statusValue,statusValue==='closed'?'closed':statusValue==='open'?'open':'');card.appendChild(meta);
    const amount=amountText(opp.amount||recordOf(row)?.amount);if(amount)card.appendChild(textNode('div','nmpg-money',amount));
    const facts=textNode('div','nmpg-facts','');
    const deadline=deadlineOf(row);if(deadline)fact(facts,`дедлайн ${deadline}`);
    for(const applicant of eligibility.applicant_types||recordOf(row)?.applicant_types||[])fact(facts,applicantLabels[applicant]||applicant);
    for(const geo of eligibility.geography||recordOf(row)?.geography||[])fact(facts,geo);
    if(facts.childNodes.length)card.appendChild(facts);
    const evidence=textNode('div','nmpg-evidence','');
    const observed=observedAt(row);if(observed)evidence.appendChild(textNode('div','',`Остання перевірка: ${new Date(observed).toLocaleString('uk-UA')}`));
    if(verification.state)evidence.appendChild(textNode('div','',`Доказовий стан: ${verification.state}`));
    for(const blocker of fit.blockers||recordOf(row)?.blockers||[])evidence.appendChild(textNode('div','nmpg-blocker',`⚠ ${blocker}`));
    card.appendChild(evidence);
    if(row.url){const a=textNode('a','nmpg-link','Відкрити першоджерело ↗');a.href=row.url;a.target='_blank';a.rel='noopener noreferrer';card.appendChild(a);}return card;
  }

  function renderPages(total,pageCount){
    const pages=document.getElementById('nmPrivatePages');if(!pages)return;pages.replaceChildren();if(pageCount<=1)return;
    const prev=textNode('button','','← Попередня');prev.type='button';prev.disabled=currentPage<=1;prev.addEventListener('click',()=>{if(currentPage>1){currentPage--;renderCurrent(true);}});pages.appendChild(prev);
    pages.appendChild(textNode('span','nmpg-page-label',`Сторінка ${currentPage} / ${pageCount} · ${total} результатів`));
    const next=textNode('button','','Наступна →');next.type='button';next.disabled=currentPage>=pageCount;next.addEventListener('click',()=>{if(currentPage<pageCount){currentPage++;renderCurrent(true);}});pages.appendChild(next);
  }

  function updateTor(payload){
    const tor=document.getElementById('nmTorState');if(!tor)return;const info=payload?.tor_retrieval;
    if(!info){tor.textContent='Tor: авто';tor.classList.remove('on');return;}
    if(info.attempted){tor.textContent=`Tor: ${info.provider_status==='complete'?'активний':'використано'}`;tor.classList.add('on');}
    else {tor.textContent='Tor: не запускався';tor.classList.remove('on');}
  }

  function renderCurrent(scrollTop=false){
    const box=document.getElementById('nmPrivateResults'),count=document.getElementById('nmResultCount');if(!box)return;
    const rows=filteredRows(),pageCount=Math.max(1,Math.ceil(rows.length/PAGE_SIZE));currentPage=Math.min(Math.max(1,currentPage),pageCount);
    const start=(currentPage-1)*PAGE_SIZE,pageRows=rows.slice(start,start+PAGE_SIZE);box.replaceChildren();
    if(!pageRows.length)box.appendChild(textNode('div','nmpg-empty',latestPayload?'За цим фільтром результатів немає.':'Введи глобальний пошуковий запит.'));
    pageRows.forEach((row,i)=>box.appendChild(resultCard(row,start+i+1)));
    if(count)count.textContent=`Показано ${pageRows.length} з ${rows.length}`;renderPages(rows.length,pageCount);updateTor(latestPayload);
    if(scrollTop)document.getElementById('nmPrivateViewport')?.scrollTo({top:0,behavior:'smooth'});
  }

  function renderRows(payload){
    latestPayload=payload||{};currentPage=1;renderCurrent(true);
    const truth=document.getElementById('nmPrivateTruth'),plan=document.getElementById('nmPrivatePlan');
    if(truth)truth.textContent=payload?.truth_note||'Результат пошуку є кандидатом, а не гарантією доступності, права на фінансування чи прибутку.';
    const queries=Array.isArray(payload?.search_plan)?payload.search_plan:[];if(plan){plan.hidden=!queries.length;const code=plan.querySelector('code');if(code)code.textContent=queries.join('\n\n');}
  }

  async function privateSearch(){
    const q=String(prompt?.value||'').replace(/\s+/g,' ').trim();if(q.length<2){if(status)status.textContent='Введи пошуковий запит.';return;}if(privateController)return;
    privateController=new AbortController();if(startBtn)startBtn.disabled=true;if(stopBtn)stopBtn.disabled=false;if(status)status.textContent='Шукаю. Уже показані результати залишаються доступними для перегляду; натисни «Стоп», щоб припинити очікування.';
    try{const category=document.getElementById('nmPrivateCategory')?.value||'all',country=document.getElementById('nmPrivateCountry')?.value||'EU';const r=await fetch('/api/private-mode/search',{method:'POST',signal:privateController.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,category,country})});let p=null;try{p=await r.json();}catch(_){}if(r.status===404){mode(false,{mode:'public'});return;}if(!r.ok)throw new Error(p?.error||`HTTP ${r.status}`);renderRows(p||{});if(status)status.textContent=`Готово · ${(p?.results||[]).length} результатів · ${p?.provider_status||'complete'} · ${p?.intelligence_version||'search'}`;}catch(e){if(status)status.textContent=e?.name==='AbortError'?'Пошук зупинено. Уже показані результати залишено на екрані.':(e?.message||'Помилка глобального пошуку.');}finally{privateController=null;if(startBtn)startBtn.disabled=false;if(stopBtn)stopBtn.disabled=true;}
  }

  startSearch=async function(){const v=String(prompt?.value||'').trim();if(await command(v))return;if(privateMode)return privateSearch();return baseStart();};
  stopSearch=function(){if(privateMode){if(privateController){privateController.abort();if(status)status.textContent='Пошук зупинено. Переглядай уже показані результати.';}return;}return baseStop();};

  addStyle();panel();fetch('/api/private-mode/state',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(p=>{if(p?.mode==='private')mode(true,p);}).catch(()=>{});
})();
