/* Opportunity Graph v2.3 evidence presentation. */
(() => {
  if (window.__nmMoneyGraphUi) return;
  window.__nmMoneyGraphUi = true;

  let latest = null;
  const originalFetch = window.fetch.bind(window);

  function addStyle(){
    if(document.getElementById('nmMoneyGraphStyle')) return;
    const s=document.createElement('style');s.id='nmMoneyGraphStyle';s.textContent=`
      #nmMoneyGraphSummary{display:grid;gap:7px;margin:0 0 12px;padding:11px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
      .nmg-title{font-size:11px;font-weight:850}.nmg-row{display:flex;gap:6px;flex-wrap:wrap}.nmg-chip{border:1px solid var(--line);border-radius:999px;padding:4px 7px;font-size:10px;color:var(--muted)}
      .nmg-v23{display:grid;gap:7px;margin-top:10px;border-top:1px solid var(--line);padding-top:10px}.nmg-head{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.nmg-id{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);overflow-wrap:anywhere}.nmg-rel{border:1px solid var(--line);border-radius:10px;padding:7px;display:grid;gap:3px}.nmg-rel-title{font-size:10px;font-weight:800}.nmg-rel-meta,.nmg-rel-evidence{font-size:10px;color:var(--muted);line-height:1.35;overflow-wrap:anywhere}.nmg-candidate{color:#e7b86f}.nmg-observed{color:var(--ok)}.nmg-truth{font-size:10px;color:var(--muted);border:1px dashed var(--line);border-radius:10px;padding:7px 9px}
    `;document.head.appendChild(s);
  }
  function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text??'');return n;}
  function clearUi(){document.getElementById('nmMoneyGraphSummary')?.remove();for(const n of document.querySelectorAll('.nmg-v23'))n.remove();}
  function capture(payload){if(!payload?.opportunity_graph?.nodes||!Array.isArray(payload.money_records)){latest=null;queueMicrotask(clearUi);return;}latest=payload;queueMicrotask(enhance);}
  window.fetch=async function(input,init){const response=await originalFetch(input,init);try{const raw=typeof input==='string'?input:(input?.url||'');if(new URL(raw,location.href).pathname==='/api/private-mode/search'&&response.ok)response.clone().json().then(capture).catch(()=>{});}catch(_){}return response;};

  function indexGraph(){const graph=latest?.opportunity_graph||{};const nodes=new Map((graph.nodes||[]).map(n=>[n.id,n]));const outgoing=new Map();const incoming=new Map();for(const e of graph.edges||[]){if(!outgoing.has(e.source))outgoing.set(e.source,[]);outgoing.get(e.source).push(e);if(!incoming.has(e.target))incoming.set(e.target,[]);incoming.get(e.target).push(e);}return {graph,nodes,outgoing,incoming};}
  function recordMaps(){const byUrl=new Map(),byTitle=new Map();for(const record of latest?.money_records||[]){for(const u of record.source_urls||[])if(u)byUrl.set(String(u),record);if(record.title)byTitle.set(String(record.title).trim().toLocaleLowerCase(),record);}return {byUrl,byTitle};}

  function summary(){const results=document.getElementById('nmPrivateResults');if(!results||!latest)return;let box=document.getElementById('nmMoneyGraphSummary');if(!box){box=node('section');box.id='nmMoneyGraphSummary';const eligibility=document.getElementById('nmEligibilitySummary');const money=document.getElementById('nmMoneySummary');(eligibility||money||results).insertAdjacentElement((eligibility||money)?'afterend':'beforebegin',box);}const sum=latest.opportunity_graph?.summary||{};box.replaceChildren(node('div','nmg-title','Opportunity Graph v2.3 · evidence entities'));const row=node('div','nmg-row');row.appendChild(node('span','nmg-chip',`nodes ${sum.nodes||0}`));row.appendChild(node('span','nmg-chip',`edges ${sum.edges||0}`));for(const [type,count] of Object.entries(sum.by_type||{}))row.appendChild(node('span','nmg-chip',`${type} ${count}`));box.appendChild(row);const rel=node('div','nmg-row');for(const [type,count] of Object.entries(sum.by_relation||{}))rel.appendChild(node('span','nmg-chip',`${type} ${count}`));if(rel.childNodes.length)box.appendChild(rel);}

  function relationCard(edge,graphIndex,callId){const otherId=edge.source===callId?edge.target:edge.source;const other=graphIndex.nodes.get(otherId)||{};const box=node('div','nmg-rel');const candidate=String(edge.state||'').includes('candidate')||String(edge.relation||'').includes('candidate');box.appendChild(node('div',`nmg-rel-title ${candidate?'nmg-candidate':'nmg-observed'}`.trim(),edge.relation));box.appendChild(node('div','nmg-rel-meta',`${edge.state||'observed'} · confidence ${edge.confidence??'?'} · ${other.type||'node'} ${other.label||other.name||other.title||other.url||other.id||otherId}`));if(edge.evidence?.length)box.appendChild(node('div','nmg-rel-evidence',`Evidence: ${edge.evidence.join(' | ')}`));return box;}

  function render(card,record,graphIndex){card.querySelector('.nmg-v23')?.remove();const callId=record.graph_call_id;if(!callId)return;const call=graphIndex.nodes.get(callId)||{};const wrap=node('div','nmg-v23');const head=node('div','nmg-head');head.appendChild(node('span','nmg-chip','GRAPH CALL'));head.appendChild(node('code','nmg-id',callId));if(call.explicit_references?.length)for(const ref of call.explicit_references)head.appendChild(node('span','nmg-chip',`REF ${ref}`));wrap.appendChild(head);const edges=[...(graphIndex.outgoing.get(callId)||[]),...(graphIndex.incoming.get(callId)||[])];if(edges.length){const details=node('details');details.appendChild(node('summary','',`Graph relations · ${edges.length}`));for(const edge of edges)details.appendChild(relationCard(edge,graphIndex,callId));wrap.appendChild(details);}wrap.appendChild(node('div','nmg-truth','Program/same-call/same-program relations marked candidate are clustering hypotheses, not factual or legal identity. Pairwise programme compatibility is not inferred without rule evidence.'));card.appendChild(wrap);}

  function enhance(){if(!document.body.classList.contains('nm-private-global')||!latest)return;summary();const maps=recordMaps();const graphIndex=indexGraph();for(const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')){const link=card.querySelector('a.nmpg-link[href]');const title=card.querySelector('.nmpg-title')?.textContent?.trim().toLocaleLowerCase();const record=(link&&maps.byUrl.get(link.getAttribute('href')||link.href))||(title&&maps.byTitle.get(title));if(record)render(card,record,graphIndex);}}
  const observer=new MutationObserver(()=>queueMicrotask(enhance));observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});addStyle();
})();
