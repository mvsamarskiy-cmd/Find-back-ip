/* Money / Material Opportunity Intelligence v2.1 presentation overlay. */
(() => {
  if (window.__nmMoneyOpportunityUi) return;
  window.__nmMoneyOpportunityUi = true;

  let latest = null;
  const originalFetch = window.fetch.bind(window);

  const familyLabels = {
    funding:'Фінансування без/зі змішаним поверненням', capital:'Капітал / інвестор',
    finance:'Кредит / гарантія / лізинг', savings:'Економія / пільга / компенсація',
    revenue:'Контракти / дохід', assets:'Активи / майно', local:'Локальні пропозиції',
    markets:'Ринки / дисбаланси', off_market:'Off-market public', other:'Інші сигнали'
  };

  function addStyle(){
    if(document.getElementById('nmMoneyV21Style')) return;
    const s=document.createElement('style');s.id='nmMoneyV21Style';s.textContent=`
      #nmMoneySummary{display:grid;gap:9px;margin:0 0 12px;padding:12px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}
      .nmm-summary-title{font-size:12px;font-weight:800}.nmm-summary-grid{display:flex;gap:7px;flex-wrap:wrap}.nmm-summary-chip{border:1px solid var(--line);border-radius:999px;padding:5px 8px;font-size:11px;color:var(--muted)}
      .nmm-v21{margin-top:11px;border-top:1px solid var(--line);padding-top:11px;display:grid;gap:9px}.nmm-topline{display:flex;gap:7px;flex-wrap:wrap}.nmm-tag{border:1px solid var(--line);border-radius:999px;padding:4px 7px;font-size:10px;color:var(--muted)}.nmm-tag.strong{color:var(--ok);border-color:var(--ok)}.nmm-tag.warn{color:#e7b86f;border-color:#8d6d37}.nmm-tag.bad{color:#e7868f;border-color:#82434a}
      .nmm-score-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.nmm-score{border:1px solid var(--line);border-radius:11px;padding:7px;text-align:center}.nmm-score b{display:block;font-size:14px}.nmm-score span{font-size:9px;color:var(--muted)}
      .nmm-section{display:grid;gap:6px}.nmm-section-title{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:800}.nmm-list{display:grid;gap:5px}.nmm-line{font-size:11px;color:var(--muted);line-height:1.4}.nmm-line.bad{color:#e7868f}.nmm-line.warn{color:#e7b86f}
      .nmm-sources{display:grid;gap:6px}.nmm-source-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center}.nmm-source-url{font:10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;color:var(--muted)}.nmm-source-open{border:1px solid var(--line);border-radius:9px;padding:6px 8px;color:var(--text);text-decoration:none;font-size:10px;white-space:nowrap}
      .nmm-actions{margin:0;padding-left:18px;color:var(--muted);font-size:11px;line-height:1.45}.nmm-verified{color:var(--ok);font-weight:800}.nmm-truth{font-size:10px;color:var(--muted);padding:7px 9px;border:1px dashed var(--line);border-radius:10px}
      @media(max-width:680px){.nmm-score-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.nmm-source-row{grid-template-columns:1fr}.nmm-source-open{justify-self:start}}
    `;document.head.appendChild(s);
  }

  function node(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text??'');return n;}
  function isPrivate(){return document.body.classList.contains('nm-private-global');}
  function number(v){const n=Number(v);return Number.isFinite(n)?n:null;}

  function capture(payload){
    if(!payload || !Array.isArray(payload.money_records)) return;
    latest=payload;
    queueMicrotask(enhance);
  }

  window.fetch = async function(input, init){
    const response=await originalFetch(input,init);
    try{
      const raw=typeof input==='string'?input:(input?.url||'');
      const path=new URL(raw,location.href).pathname;
      if(path==='/api/private-mode/search' && response.ok){response.clone().json().then(capture).catch(()=>{});}
    }catch(_){ }
    return response;
  };

  function recordMaps(){
    const byUrl=new Map(),byTitle=new Map();
    for(const record of latest?.money_records||[]){
      for(const url of record?.source_urls||[])if(url)byUrl.set(String(url),record);
      if(record?.title)byTitle.set(String(record.title).trim().toLocaleLowerCase(),record);
    }
    return {byUrl,byTitle};
  }

  function addTag(parent,text,cls=''){if(text)parent.appendChild(node('span',`nmm-tag ${cls}`.trim(),text));}

  function summary(){
    const results=document.getElementById('nmPrivateResults');if(!results||!latest)return;
    let box=document.getElementById('nmMoneySummary');
    if(!box){box=node('section');box.id='nmMoneySummary';results.insertAdjacentElement('beforebegin',box);}
    box.replaceChildren(node('div','nmm-summary-title',`Money Opportunity Intelligence · ${latest.money_records?.length||0} унікальних можливостей`));
    const grid=node('div','nmm-summary-grid');
    for(const [family,data] of Object.entries(latest.money_summary||{})){
      const bits=[`${familyLabels[family]||family}: ${data.found||0}`];
      if(data.open)bits.push(`open ${data.open}`);if(data.upcoming)bits.push(`upcoming ${data.upcoming}`);if(data.likely_eligible)bits.push(`fit ${data.likely_eligible}`);
      grid.appendChild(node('span','nmm-summary-chip',bits.join(' · ')));
    }
    box.appendChild(grid);
  }

  function scoreBox(label,value){const b=node('div','nmm-score');b.append(node('b','',value===null?'?':value),node('span','',label));return b;}

  function renderRecord(card,record){
    card.querySelector('.nmm-v21')?.remove();
    const wrap=node('div','nmm-v21');
    const top=node('div','nmm-topline');
    addTag(top,familyLabels[record.family]||record.family);
    addTag(top,record.opportunity_type);
    addTag(top,record.status,record.status==='closed'?'bad':record.status==='open'?'strong':'');
    if(record.official_source)addTag(top,'OFFICIAL SOURCE','strong');
    if(record.source_observed)addTag(top,'SOURCE OBSERVED','strong');
    if(record.current_call_verified)addTag(top,'CURRENT CALL VERIFIED','strong');
    if(record.likely_eligible)addTag(top,'LIKELY FIT · needs rules check','warn');
    if((record.duplicate_evidence_count||1)>1)addTag(top,`${record.duplicate_evidence_count} джерела`);
    wrap.appendChild(top);

    const components=record.practical_ranking?.components||{};
    const scores=node('div','nmm-score-grid');
    scores.append(
      scoreBox('PRACTICAL',number(record.practical_ranking?.score)),
      scoreBox('EVIDENCE',number(record.evidence_score)),
      scoreBox('FIT',number(record.fit_score)),
      scoreBox('UPSIDE',number(components.economic_upside)),
      scoreBox('FRESHNESS',number(components.status_freshness))
    );wrap.appendChild(scores);

    const econ=record.economics||{};
    const economics=node('div','nmm-section');economics.appendChild(node('div','nmm-section-title','Економіка / механізм'));
    const elist=node('div','nmm-list');
    elist.appendChild(node('div','nmm-line',`Тип: ${econ.economic_kind||'unknown'} · repayable: ${econ.repayable===true?'так':econ.repayable===false?'ні':'невідомо'}`));
    if(econ.cofinancing_mentioned)elist.appendChild(node('div','nmm-line warn','У джерелі згадано співфінансування / власний внесок.'));
    if(econ.rate_percent_observed?.value!==undefined)elist.appendChild(node('div','nmm-line',`Observed rate: ${econ.rate_percent_observed.value}%`));
    economics.appendChild(elist);wrap.appendChild(economics);

    const blockers=record.blockers||[],unknowns=record.unknown_requirements||[];
    if(blockers.length||unknowns.length){const sec=node('div','nmm-section');sec.appendChild(node('div','nmm-section-title','Доступ / невідомі умови'));const list=node('div','nmm-list');for(const x of blockers)list.appendChild(node('div','nmm-line bad',`Блокер: ${x}`));for(const x of unknowns)list.appendChild(node('div','nmm-line warn',`Треба підтвердити: ${x}`));sec.appendChild(list);wrap.appendChild(sec);}

    const dv=record.direct_verification||{};
    if(dv.state){const sec=node('div','nmm-section');sec.appendChild(node('div','nmm-section-title','Direct-source verification'));const list=node('div','nmm-list');list.appendChild(node('div','nmm-line',`State: ${dv.state}${dv.http_status?` · HTTP ${dv.http_status}`:''}`));if(dv.observed_at)list.appendChild(node('div','nmm-line',`Observed: ${new Date(dv.observed_at).toLocaleString('uk-UA')}`));if(dv.snapshot_sha256)list.appendChild(node('div','nmm-line',`Snapshot SHA-256: ${dv.snapshot_sha256}`));if(dv.current_call_verified)list.appendChild(node('div','nmm-line nmm-verified','Офіційна/публічна сторінка прямо підтвердила активний/майбутній call.'));sec.appendChild(list);wrap.appendChild(sec);}

    const urls=record.source_urls||[];
    if(urls.length){const sec=node('div','nmm-section');sec.appendChild(node('div','nmm-section-title',`Оригінальні джерела · ${urls.length}`));const list=node('div','nmm-sources');for(const url of urls){const row=node('div','nmm-source-row');row.appendChild(node('code','nmm-source-url',url));const a=node('a','nmm-source-open','Відкрити ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';row.appendChild(a);list.appendChild(row);}sec.appendChild(list);wrap.appendChild(sec);}

    if(record.action_steps?.length){const sec=node('div','nmm-section');sec.appendChild(node('div','nmm-section-title','Що робити далі'));const ol=node('ol','nmm-actions');for(const step of record.action_steps)ol.appendChild(node('li','',step));sec.appendChild(ol);wrap.appendChild(sec);}
    wrap.appendChild(node('div','nmm-truth','Знайдений кандидат ≠ гарантована доступність, право на фінансування чи прибуток. Перевіряй оригінальне джерело й актуальні правила.'));
    card.appendChild(wrap);
  }

  function enhance(){
    if(!isPrivate()||!latest)return;summary();const maps=recordMaps();
    for(const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')){
      const link=card.querySelector('a.nmpg-link[href]');const title=card.querySelector('.nmpg-title')?.textContent?.trim().toLocaleLowerCase();
      const record=(link&&maps.byUrl.get(link.getAttribute('href')||link.href))||(title&&maps.byTitle.get(title));
      if(record)renderRecord(card,record);
    }
  }

  const observer=new MutationObserver(()=>queueMicrotask(enhance));
  observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
  addStyle();
})();
