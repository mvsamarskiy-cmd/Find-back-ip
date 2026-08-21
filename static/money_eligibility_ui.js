/* Money Eligibility Engine v2.2 presentation overlay. */
(() => {
  if (window.__nmMoneyEligibilityUi) return;
  window.__nmMoneyEligibilityUi = true;

  let latest = null;
  const originalFetch = window.fetch.bind(window);
  const stateLabels = {
    eligible_candidate:'ELIGIBLE CANDIDATE', possible:'POSSIBLE · NEEDS FACTS',
    unknown:'UNKNOWN', ineligible:'INELIGIBLE ON OBSERVED RULE'
  };

  function addStyle(){
    if(document.getElementById('nmEligibilityV22Style')) return;
    const s=document.createElement('style');s.id='nmEligibilityV22Style';s.textContent=`
      #nmEligibilitySummary{display:grid;gap:8px;margin:0 0 12px;padding:11px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
      .nme-summary-title{font-size:11px;font-weight:850}.nme-summary-row{display:flex;gap:6px;flex-wrap:wrap}.nme-chip{border:1px solid var(--line);border-radius:999px;padding:4px 7px;font-size:10px;color:var(--muted)}.nme-chip.good{color:var(--ok);border-color:var(--ok)}.nme-chip.bad{color:#e7868f;border-color:#82434a}.nme-chip.warn{color:#e7b86f;border-color:#8d6d37}
      .nme-v22{margin-top:10px;border-top:1px solid var(--line);padding-top:10px;display:grid;gap:8px}.nme-head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.nme-state{font-size:10px;font-weight:900;border:1px solid var(--line);border-radius:999px;padding:5px 8px}.nme-state.eligible_candidate{color:var(--ok);border-color:var(--ok)}.nme-state.possible{color:#e7b86f;border-color:#8d6d37}.nme-state.ineligible{color:#e7868f;border-color:#82434a}.nme-score{font-size:11px;color:var(--muted)}
      .nme-facts{display:flex;gap:6px;flex-wrap:wrap}.nme-fact{font-size:10px;border:1px solid var(--line);border-radius:999px;padding:4px 7px;color:var(--muted)}
      .nme-missing{font-size:11px;color:#e7b86f;line-height:1.45}.nme-fail{font-size:11px;color:#e7868f;line-height:1.45}
      .nme-rules{display:grid;gap:6px}.nme-rule{border:1px solid var(--line);border-radius:11px;padding:8px;display:grid;gap:4px}.nme-rule-top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.nme-rule-title{font-size:10px;font-weight:800}.nme-rule-state{font-size:9px;font-weight:800}.nme-rule-state.pass{color:var(--ok)}.nme-rule-state.fail{color:#e7868f}.nme-rule-state.unknown{color:#e7b86f}.nme-rule-values,.nme-rule-evidence{font-size:10px;color:var(--muted);line-height:1.4;overflow-wrap:anywhere}
      .nme-truth{font-size:10px;color:var(--muted);padding:7px 9px;border:1px dashed var(--line);border-radius:10px}
      @media(max-width:680px){.nme-head{align-items:flex-start}.nme-rule-top{display:grid}}
    `;document.head.appendChild(s);
  }

  function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text??'');return n;}
  function privateMode(){return document.body.classList.contains('nm-private-global');}
  function clearUi(){document.getElementById('nmEligibilitySummary')?.remove();for(const n of document.querySelectorAll('.nme-v22'))n.remove();}

  function capture(payload){
    if(!payload || !payload.eligibility_summary || !Array.isArray(payload.money_records)){
      latest=null;queueMicrotask(clearUi);return;
    }
    latest=payload;queueMicrotask(enhance);
  }

  window.fetch=async function(input,init){
    const response=await originalFetch(input,init);
    try{
      const raw=typeof input==='string'?input:(input?.url||'');
      const path=new URL(raw,location.href).pathname;
      if(path==='/api/private-mode/search' && response.ok)response.clone().json().then(capture).catch(()=>{});
    }catch(_){ }
    return response;
  };

  function maps(){
    const byUrl=new Map(),byTitle=new Map();
    for(const record of latest?.money_records||[]){
      for(const url of record?.source_urls||[])if(url)byUrl.set(String(url),record);
      if(record?.title)byTitle.set(String(record.title).trim().toLocaleLowerCase(),record);
    }
    return {byUrl,byTitle};
  }

  function summary(){
    const results=document.getElementById('nmPrivateResults');if(!results||!latest)return;
    let box=document.getElementById('nmEligibilitySummary');if(!box){box=node('section');box.id='nmEligibilitySummary';const money=document.getElementById('nmMoneySummary');(money||results).insertAdjacentElement(money?'afterend':'beforebegin',box);}
    box.replaceChildren(node('div','nme-summary-title','Eligibility Engine v2.2 · observed rules × explicit profile facts'));
    const row=node('div','nme-summary-row');const states=latest.eligibility_summary?.states||{};
    for(const state of ['eligible_candidate','possible','unknown','ineligible']){
      const cls=state==='eligible_candidate'?'good':state==='ineligible'?'bad':state==='possible'?'warn':'';
      row.appendChild(node('span',`nme-chip ${cls}`.trim(),`${stateLabels[state]}: ${states[state]||0}`));
    }
    box.appendChild(row);
    const missing=latest.eligibility_summary?.missing_profile_fields||{};const entries=Object.entries(missing);
    if(entries.length){const r=node('div','nme-summary-row');r.appendChild(node('span','nme-chip warn','Найчастіше бракує:'));for(const [field,count] of entries.slice(0,8))r.appendChild(node('span','nme-chip',`${field} · ${count}`));box.appendChild(r);}
    const known=latest.eligibility_profile?.known_fields||[];if(known.length){const r=node('div','nme-summary-row');r.appendChild(node('span','nme-chip good','Відомі факти профілю:'));for(const field of known)r.appendChild(node('span','nme-chip',field));box.appendChild(r);}
  }

  function stringify(value){if(value===null||value===undefined)return '?';if(typeof value==='object')try{return JSON.stringify(value);}catch(_){return String(value);}return String(value);}

  function render(card,record){
    card.querySelector('.nme-v22')?.remove();const e=record.eligibility||{};const wrap=node('div','nme-v22');
    const head=node('div','nme-head');head.appendChild(node('span',`nme-state ${record.eligibility_state||'unknown'}`.trim(),stateLabels[record.eligibility_state]||'UNKNOWN'));head.appendChild(node('span','nme-score',`Eligibility ${record.eligibility_score??'?'} · ${record.eligibility_evidence_level||'unknown evidence'}`));wrap.appendChild(head);
    const facts=node('div','nme-facts');facts.appendChild(node('span','nme-fact',`rules ${e.rules_observed||0}`));facts.appendChild(node('span','nme-fact',`pass ${e.passed||0}`));facts.appendChild(node('span','nme-fact',`fail ${e.failed||0}`));facts.appendChild(node('span','nme-fact',`unknown ${e.unknown||0}`));wrap.appendChild(facts);
    if(e.missing_profile_fields?.length)wrap.appendChild(node('div','nme-missing',`Треба додати в профіль/запит: ${e.missing_profile_fields.join(', ')}`));
    const failed=(e.checks||[]).filter(x=>x?.state==='fail');if(failed.length)wrap.appendChild(node('div','nme-fail',`Не проходить за побаченими правилами: ${failed.map(x=>x.rule_id).join(', ')}`));
    if(e.checks?.length){const details=node('details');const summaryNode=node('summary','','Показати всі eligibility rules');details.appendChild(summaryNode);const list=node('div','nme-rules');for(const check of e.checks){const r=node('div','nme-rule');const top=node('div','nme-rule-top');top.appendChild(node('div','nme-rule-title',`${check.field} · ${check.operator}`));top.appendChild(node('div',`nme-rule-state ${check.state||'unknown'}`,String(check.state||'unknown').toUpperCase()));r.appendChild(top);r.appendChild(node('div','nme-rule-values',`Очікується: ${stringify(check.expected)} · Профіль: ${stringify(check.profile_value)}`));const evidence=Array.isArray(check.evidence)?check.evidence.join(' | '):check.evidence;if(evidence)r.appendChild(node('div','nme-rule-evidence',`Evidence: ${evidence}`));list.appendChild(r);}details.appendChild(list);wrap.appendChild(details);}
    wrap.appendChild(node('div','nme-truth','ELIGIBLE CANDIDATE означає лише: всі обов’язкові правила, які система реально побачила, збігаються з відомими фактами профілю. Це не юридичне підтвердження eligibility і не гарантія отримання грошей.'));
    card.appendChild(wrap);
  }

  function enhance(){
    if(!privateMode()||!latest)return;summary();const m=maps();
    for(const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')){
      const link=card.querySelector('a.nmpg-link[href]');const title=card.querySelector('.nmpg-title')?.textContent?.trim().toLocaleLowerCase();const record=(link&&m.byUrl.get(link.getAttribute('href')||link.href))||(title&&m.byTitle.get(title));if(record)render(card,record);
    }
  }

  const observer=new MutationObserver(()=>queueMicrotask(enhance));observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});addStyle();
})();
