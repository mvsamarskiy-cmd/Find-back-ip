/* Money Source Expansion v2.4 presentation overlay. */
(() => {
  if (window.__nmMoneySourceExpansionUi) return;
  window.__nmMoneySourceExpansionUi = true;

  let latest = null;
  const originalFetch = window.fetch.bind(window);

  function addStyle(){
    if(document.getElementById('nmSourceExpansionStyle')) return;
    const s=document.createElement('style');s.id='nmSourceExpansionStyle';s.textContent=`
      #nmSourceExpansionSummary{display:grid;gap:7px;margin:0 0 12px;padding:11px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
      .nms-title{font-size:11px;font-weight:850}.nms-row{display:flex;gap:6px;flex-wrap:wrap}.nms-chip{border:1px solid var(--line);border-radius:999px;padding:4px 7px;font-size:10px;color:var(--muted)}.nms-chip.good{color:var(--ok);border-color:var(--ok)}.nms-chip.warn{color:#e7b86f;border-color:#8d6d37}
      .nms-v24{display:grid;gap:6px;margin-top:10px;border-top:1px solid var(--line);padding-top:10px}.nms-source-class{font-size:10px;font-weight:850;color:#e7b86f}.nms-note{font-size:10px;color:var(--muted);line-height:1.4}.nms-lanes{display:grid;gap:5px}.nms-lane{border:1px solid var(--line);border-radius:10px;padding:7px;display:grid;gap:3px}.nms-lane-title{font-size:10px;font-weight:800}.nms-lane-query{font:9px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);overflow-wrap:anywhere}.nms-truth{font-size:10px;color:var(--muted);border:1px dashed var(--line);border-radius:10px;padding:7px 9px}
    `;document.head.appendChild(s);
  }
  function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text??'');return n;}
  function clearUi(){document.getElementById('nmSourceExpansionSummary')?.remove();for(const n of document.querySelectorAll('.nms-v24'))n.remove();}
  function capture(payload){if(!payload?.source_expansion||!Array.isArray(payload.money_records)){latest=null;queueMicrotask(clearUi);return;}latest=payload;queueMicrotask(enhance);}
  window.fetch=async function(input,init){const response=await originalFetch(input,init);try{const raw=typeof input==='string'?input:(input?.url||'');if(new URL(raw,location.href).pathname==='/api/private-mode/search'&&response.ok)response.clone().json().then(capture).catch(()=>{});}catch(_){}return response;};

  function recordMaps(){const byUrl=new Map(),byTitle=new Map();for(const record of latest?.money_records||[]){for(const u of record.source_urls||[])if(u)byUrl.set(String(u),record);if(record.title)byTitle.set(String(record.title).trim().toLocaleLowerCase(),record);}return {byUrl,byTitle};}

  function summary(){
    const results=document.getElementById('nmPrivateResults');if(!results||!latest)return;
    let box=document.getElementById('nmSourceExpansionSummary');
    if(!box){box=node('section');box.id='nmSourceExpansionSummary';const eligibility=document.getElementById('nmEligibilitySummary');const money=document.getElementById('nmMoneySummary');(eligibility||money||results).insertAdjacentElement((eligibility||money)?'afterend':'beforebegin',box);}
    const meta=latest.source_expansion||{};box.replaceChildren(node('div','nms-title','Source Expansion v2.4 · deep source-class discovery'));
    const row=node('div','nms-row');row.appendChild(node('span',`nms-chip ${meta.attempted?'good':''}`.trim(),meta.attempted?'SEARCHED':'NOT ATTEMPTED'));row.appendChild(node('span','nms-chip',`lanes ${(meta.lanes||[]).length}`));row.appendChild(node('span','nms-chip',`raw ${meta.raw_candidate_count||0}`));row.appendChild(node('span','nms-chip',`normalized ${meta.normalized_candidate_count||0}`));row.appendChild(node('span','nms-chip good',`unique +${meta.unique_added_count||0}`));row.appendChild(node('span','nms-chip',`direct verify ${meta.direct_verification_attempted_count||0}`));box.appendChild(row);
    if(meta.lanes?.length){const details=node('details');details.appendChild(node('summary','','Показати source-class search lanes'));const lanes=node('div','nms-lanes');meta.lanes.forEach((lane,index)=>{const l=node('div','nms-lane');l.appendChild(node('div','nms-lane-title',`${index+1}. ${lane.source_class||'source_class'} · ${lane.trust||'discovery'} · ${(meta.provider_statuses||[])[index]||'?'}`));l.appendChild(node('div','nms-lane-query',lane.query||''));lanes.appendChild(l);});details.appendChild(lanes);box.appendChild(details);}
    box.appendChild(node('div','nms-truth','Source registry/class match is a discovery signal only. It does not prove a specific listing/call is current, authentic, eligible or profitable.'));
  }

  function render(card,record){card.querySelector('.nms-v24')?.remove();const classes=record.source_classes||((record.source_class)?[record.source_class]:[]);if(!record.source_expansion_evidence&&!classes.length)return;const wrap=node('div','nms-v24');wrap.appendChild(node('div','nms-source-class',`SOURCE EXPANSION · ${classes.join(', ')||'expanded discovery'}`));wrap.appendChild(node('div','nms-note',`Цей кандидат був знайдений або додатково підтверджений через Source Expansion. Original source URLs: ${(record.source_urls||[]).length}.`));wrap.appendChild(node('div','nms-truth','Expanded-source evidence не підвищує результат до VERIFIED автоматично; direct-source/status/eligibility залишаються окремими шарами.'));card.appendChild(wrap);}

  function enhance(){if(!document.body.classList.contains('nm-private-global')||!latest)return;summary();const maps=recordMaps();for(const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')){const link=card.querySelector('a.nmpg-link[href]');const title=card.querySelector('.nmpg-title')?.textContent?.trim().toLocaleLowerCase();const record=(link&&maps.byUrl.get(link.getAttribute('href')||link.href))||(title&&maps.byTitle.get(title));if(record)render(card,record);}}
  const observer=new MutationObserver(()=>queueMicrotask(enhance));observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});addStyle();
})();
