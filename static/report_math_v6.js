/* NameMachine report math v6.
 *
 * Every high-level conclusion in the client report should expose its denominator,
 * rate, uncertainty, and (when available) the same ranking equations used by the
 * runtime. This file is presentation-only: it never changes verification truth,
 * feedback, ranking, or candidate state.
 */
(() => {
  if (window.nameMachineReportMath) return;

  const RESOURCE_ORDER = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
  const CONFLICT = new Set(['taken', 'reserved', 'invalid']);
  const UNRESOLVED = new Set(['unknown', 'rate_limited', 'available']);
  const UTILITY = {
    claimable: 1.00,
    purchasable: 0.82,
    not_found: 0.55,
    unknown: 0.18,
    rate_limited: 0.14,
    available: 0.18,
    taken: 0.00,
    reserved: 0.00,
    invalid: 0.00,
  };
  const STATE_PENALTY = {
    claimable: 0.0,
    purchasable: -1.5,
    promising: 0.0,
    unresolved: -5.0,
    conflict: -18.0,
    unverified: 0.0,
  };
  const FAMILY_LABELS = {
    root_blend: 'злиті / гібридні слова',
    invented_phonetic: 'вигадані милозвучні слова',
    semantic_compound: 'смислові сполучення',
    abstract: 'абстрактні короткі назви',
    evocative_metaphor: 'образні / метафоричні назви',
    unknown: 'невизначена сім’я',
  };

  const clean = (value, limit = 1000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const escapeHtml = value => clean(value, 5000).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const clamp = (value, low = 0, high = 100) => Math.max(low, Math.min(high, Number(value) || 0));
  const pct = (n, d, digits = 1) => d > 0 ? (100 * n / d).toFixed(digits) + '%' : '—';
  const num = (value, digits = 1) => finite(value) === null ? '—' : Number(value).toFixed(digits);

  function statusOf(payload) {
    const status = String(payload?.status || 'unknown').toLowerCase();
    return Object.prototype.hasOwnProperty.call(UTILITY, status) ? status : 'unknown';
  }

  function resourcesForRow(row) {
    const availability = row?.availability && typeof row.availability === 'object' ? row.availability : {};
    const keys = Object.keys(availability);
    return RESOURCE_ORDER.filter(key => keys.includes(key)).concat(keys.filter(key => !RESOURCE_ORDER.includes(key)).sort());
  }

  function strictState(row) {
    const explicit = String(row?.bundle_availability_state || '');
    if (['claimable', 'purchasable', 'promising', 'unresolved', 'conflict', 'unverified'].includes(explicit)) return explicit;
    const resources = resourcesForRow(row);
    if (!resources.length) return 'unverified';
    const statuses = resources.map(key => statusOf(row?.availability?.[key]));
    if (statuses.some(status => CONFLICT.has(status))) return 'conflict';
    if (statuses.some(status => UNRESOLVED.has(status))) return 'unresolved';
    if (statuses.every(status => status === 'claimable')) return 'claimable';
    if (statuses.some(status => status === 'not_found')) return 'promising';
    if (statuses.every(status => status === 'claimable' || status === 'purchasable') && statuses.some(status => status === 'purchasable')) return 'purchasable';
    return 'unresolved';
  }

  function feedbackFor(row) {
    if (typeof sessionFeedback === 'function') return sessionFeedback(row?.name);
    return current?.feedback?.[String(row?.name || '').toLowerCase()] || { vote: 0, comment: '' };
  }

  function voteOf(row) {
    const vote = Number(feedbackFor(row)?.vote || 0);
    return vote > 0 ? 1 : vote < 0 ? -1 : 0;
  }

  function wilson(successes, trials, z = 1.96) {
    if (!trials) return null;
    const p = successes / trials;
    const z2 = z * z;
    const denom = 1 + z2 / trials;
    const center = (p + z2 / (2 * trials)) / denom;
    const margin = z * Math.sqrt((p * (1 - p) + z2 / (4 * trials)) / trials) / denom;
    return {
      rate: p,
      low: Math.max(0, center - margin),
      high: Math.min(1, center + margin),
    };
  }

  function evidenceConfidence(events) {
    return 1 - Math.exp(-Math.max(0, events) / 5);
  }

  function familyStats(rows) {
    const map = new Map();
    for (const row of rows) {
      const family = String(row?.family || 'unknown');
      if (!map.has(family)) map.set(family, { family, total: 0, liked: 0, disliked: 0, rated: 0, names: [] });
      const item = map.get(family);
      item.total += 1;
      const vote = voteOf(row);
      if (vote > 0) {
        item.liked += 1;
        item.rated += 1;
        if (item.names.length < 5) item.names.push(row?.name || '?');
      } else if (vote < 0) {
        item.disliked += 1;
        item.rated += 1;
      }
    }
    return [...map.values()].map(item => {
      const interval = wilson(item.liked, item.rated);
      const net = item.rated ? (item.liked - item.disliked) / item.rated : 0;
      let inference = 'немає оцінених прикладів';
      if (interval) {
        if (interval.low > 0.5) inference = 'позитивний сигнал підтверджується 95% Wilson-інтервалом';
        else if (interval.high < 0.5) inference = 'негативний сигнал підтверджується 95% Wilson-інтервалом';
        else inference = 'даних ще недостатньо для стійкого висновку';
      }
      return {
        ...item,
        interval,
        approval: item.rated ? item.liked / item.rated : null,
        coverage: item.total ? item.rated / item.total : 0,
        net,
        confidence: evidenceConfidence(item.rated),
        inference,
      };
    }).filter(item => item.rated > 0).sort((a, b) => b.rated - a.rated || b.net - a.net);
  }

  function overallFeedback(rows) {
    let liked = 0, disliked = 0, commentOnly = 0, selected = 0;
    for (const row of rows) {
      const fb = feedbackFor(row);
      const vote = voteOf(row);
      if (vote > 0) liked += 1;
      else if (vote < 0) disliked += 1;
      else if (clean(fb?.comment || '')) commentOnly += 1;
      if ((current?.shortlist || []).includes(row?.name) || (current?.directionAnchors || []).includes(row?.name)) selected += 1;
    }
    const rated = liked + disliked;
    return {
      liked,
      disliked,
      rated,
      commentOnly,
      selected,
      interval: wilson(liked, rated),
      confidence: evidenceConfidence(rated),
    };
  }

  function availabilityStats(rows) {
    const bundles = { claimable: 0, purchasable: 0, promising: 0, unresolved: 0, conflict: 0, unverified: 0 };
    const resources = new Map();
    const providers = new Map();
    for (const row of rows) {
      const state = strictState(row);
      bundles[state] = (bundles[state] || 0) + 1;
      for (const resource of resourcesForRow(row)) {
        if (!resources.has(resource)) resources.set(resource, { total: 0, claimable: 0, purchasable: 0, not_found: 0, conflict: 0, unresolved: 0 });
        const item = resources.get(resource);
        const payload = row?.availability?.[resource] || {};
        const status = statusOf(payload);
        item.total += 1;
        if (status === 'claimable') item.claimable += 1;
        else if (status === 'purchasable') item.purchasable += 1;
        else if (status === 'not_found') item.not_found += 1;
        else if (CONFLICT.has(status)) item.conflict += 1;
        else item.unresolved += 1;
        const source = clean(payload?.source || 'unknown', 80) || 'unknown';
        const providerKey = resource + '|' + source;
        providers.set(providerKey, (providers.get(providerKey) || 0) + 1);
      }
    }
    return { bundles, resources, providers };
  }

  function opportunityFromRow(row) {
    const resources = resourcesForRow(row);
    if (!resources.length) return null;
    const values = resources.map(key => UTILITY[statusOf(row?.availability?.[key])] ?? UTILITY.unknown);
    return 100 * values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function evidenceConfidenceFromRow(row) {
    const resources = resourcesForRow(row);
    if (!resources.length) return null;
    const values = resources.map(key => {
      const raw = finite(row?.availability?.[key]?.confidence);
      return raw === null ? 0.5 : Math.max(0, Math.min(1, raw));
    });
    return 100 * values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function coverageFromRow(row) {
    const resources = resourcesForRow(row);
    if (!resources.length) return 0;
    const resolved = resources.filter(key => !UNRESOLVED.has(statusOf(row?.availability?.[key]))).length;
    return 100 * resolved / resources.length;
  }

  function rankingAudit(row) {
    const structural = finite(row?.structural_quality_score);
    const linguistic = finite(row?.linguistic_quality_score);
    const quality = finite(row?.name_quality_score);
    const userFit = finite(row?.user_fit_score);
    const adaptive = finite(row?.adaptive_relevance_score);
    const identityStored = finite(row?.identity_relevance_score);
    const opportunityStored = finite(row?.availability_opportunity_score);
    const confidenceStored = finite(row?.availability_evidence_confidence_score);
    const coverageStored = finite(row?.verification_coverage_score);
    const finalStored = finite(row?.final_score);
    const state = strictState(row);
    const opportunity = opportunityStored === null ? opportunityFromRow(row) : opportunityStored;
    let identity = identityStored;
    let identityFormula = 'identity: недостатньо компонентів';
    if (quality !== null && adaptive !== null) {
      identity = 0.45 * quality + 0.55 * adaptive;
      identityFormula = `I = 0.45×Q(${num(quality)}) + 0.55×A(${num(adaptive)}) = ${num(identity)}`;
    } else if (quality !== null && userFit !== null) {
      identity = 0.68 * quality + 0.32 * userFit;
      identityFormula = `I = 0.68×Q(${num(quality)}) + 0.32×U(${num(userFit)}) = ${num(identity)}`;
    } else if (quality !== null) {
      identity = quality;
      identityFormula = `I = Q = ${num(identity)}`;
    }
    const penalty = STATE_PENALTY[state] ?? -5;
    const recomputedFinal = identity === null
      ? null
      : opportunity === null
        ? clamp(identity)
        : clamp(0.72 * identity + 0.28 * opportunity + penalty);
    const delta = finalStored !== null && recomputedFinal !== null ? finalStored - recomputedFinal : null;
    return {
      name: row?.name || '?',
      state,
      structural,
      linguistic,
      quality,
      userFit,
      adaptive,
      identity,
      opportunity,
      evidenceConfidence: confidenceStored === null ? evidenceConfidenceFromRow(row) : confidenceStored,
      coverage: coverageStored === null ? coverageFromRow(row) : coverageStored,
      finalStored,
      recomputedFinal,
      delta,
      penalty,
      identityFormula,
    };
  }

  function runStats(rows) {
    const groups = new Map();
    const runMeta = new Map((current?.runs || []).map(run => [String(run?.id || ''), run]));
    for (const row of rows) {
      const id = String(row?.run_id || 'без-run-id');
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(row);
    }
    const output = [];
    for (const [id, items] of groups.entries()) {
      const states = { claimable: 0, purchasable: 0, promising: 0, unresolved: 0, conflict: 0, unverified: 0 };
      const finals = [];
      const userFits = [];
      for (const row of items) {
        const state = strictState(row);
        states[state] = (states[state] || 0) + 1;
        const final = finite(row?.final_score);
        if (final !== null) finals.push(final);
        const fit = finite(row?.user_fit_score);
        if (fit !== null) userFits.push(fit);
      }
      const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
      const meta = runMeta.get(id) || {};
      output.push({
        id,
        status: clean(meta?.status || 'unknown', 30),
        prompt: clean(meta?.prompt || '', 180),
        count: items.length,
        states,
        avgFinal: mean(finals),
        avgUserFit: mean(userFits),
        started: clean(meta?.started || '', 40),
      });
    }
    return output.sort((a, b) => String(a.started).localeCompare(String(b.started)) || a.id.localeCompare(b.id));
  }

  function model(rowsInput) {
    const rows = Array.isArray(rowsInput) ? rowsInput : (current?.results || []);
    return {
      rows,
      feedback: overallFeedback(rows),
      families: familyStats(rows),
      availability: availabilityStats(rows),
      rankings: [...rows]
        .filter(row => finite(row?.final_score) !== null || finite(row?.name_quality_score) !== null)
        .sort((a, b) => (finite(b?.final_score) ?? -1) - (finite(a?.final_score) ?? -1))
        .slice(0, 12)
        .map(rankingAudit),
      runs: runStats(rows),
    };
  }

  function familyText(item) {
    const interval = item.interval;
    const ci = interval ? `${(interval.low * 100).toFixed(1)}–${(interval.high * 100).toFixed(1)}%` : '—';
    return `- ${FAMILY_LABELS[item.family] || item.family}: оцінено ${item.rated}/${item.total} (${pct(item.rated, item.total)} покриття); ` +
      `👍 ${item.liked}, 👎 ${item.disliked}; approval = ${item.liked}/${item.rated} = ${pct(item.liked, item.rated)}; ` +
      `net = (${item.liked}−${item.disliked})/${item.rated} = ${item.net.toFixed(3)}; 95% Wilson CI = ${ci}; ` +
      `confidence(n)=1−e^(−n/5)=${item.confidence.toFixed(3)}; висновок: ${item.inference}.`;
  }

  function text(rowsInput) {
    const m = model(rowsInput);
    const f = m.feedback;
    const lines = [
      '',
      'МАТЕМАТИЧНА ОСНОВА ВИСНОВКІВ',
      '- Правило: кожен висновок нижче має чисельник, знаменник або формулу. Якщо вибірки недостатньо, звіт прямо каже «недостатньо даних».',
      '',
      'A. ФІДБЕК І НАВЧАННЯ СМАКУ',
      `- Явні оцінки: n=${f.rated}; 👍 ${f.liked}, 👎 ${f.disliked}; approval=${f.rated ? `${f.liked}/${f.rated}=${pct(f.liked, f.rated)}` : '—'}; comment-only=${f.commentOnly}; shortlist/direction selections=${f.selected}.`,
      `- Сила явної вибірки: confidence(n)=1−e^(−n/5)=${f.confidence.toFixed(3)}. Це показник обсягу сигналу, а не ймовірність «правильності» смаку.`,
    ];
    if (f.interval) lines.push(`- 95% Wilson-інтервал загальної частки лайків: ${(f.interval.low * 100).toFixed(1)}–${(f.interval.high * 100).toFixed(1)}%.`);
    if (!m.families.length) lines.push('- По сім’ях назв: немає достатньо оцінених прикладів.');
    else m.families.forEach(item => lines.push(familyText(item)));

    const b = m.availability.bundles;
    const total = m.rows.length;
    lines.push('', 'B. МАТЕМАТИКА ДОСТУПНОСТІ');
    lines.push(`- Усього кандидатів: N=${total}. Strict-free=${b.claimable} (${pct(b.claimable, total)}); paid/purchasable=${b.purchasable} (${pct(b.purchasable, total)}); promising=${b.promising} (${pct(b.promising, total)}); conflict=${b.conflict} (${pct(b.conflict, total)}); unresolved=${b.unresolved} (${pct(b.unresolved, total)}); unverified=${b.unverified} (${pct(b.unverified, total)}).`);
    for (const [resource, item] of m.availability.resources.entries()) {
      lines.push(`- ${window.labels?.[resource] || resource}: N=${item.total}; claimable ${item.claimable} (${pct(item.claimable, item.total)}); purchasable ${item.purchasable} (${pct(item.purchasable, item.total)}); not_found ${item.not_found} (${pct(item.not_found, item.total)}); conflict ${item.conflict} (${pct(item.conflict, item.total)}); unresolved ${item.unresolved} (${pct(item.unresolved, item.total)}).`);
    }
    lines.push('- Opportunity utility для ранжування: claimable=1.00, purchasable=0.82, not_found=0.55, unknown=0.18, rate_limited=0.14, taken/reserved/invalid=0.00. Це лише ranking utility; вона не змінює істинний статус.');

    lines.push('', 'C. ФОРМУЛА РАНЖУВАННЯ КАНДИДАТІВ');
    lines.push('- Q(name) ≈ 0.56×structural + 0.44×linguistic (для local-source може бути окремий штраф).');
    lines.push('- Якщо є adaptive relevance: I = 0.45×Q + 0.55×A. Інакше, якщо є user-fit: I = 0.68×Q + 0.32×U.');
    lines.push('- Якщо доступність перевірялась: Final = clamp(0.72×I + 0.28×Opportunity + state_penalty, 0, 100). Penalty: claimable 0; purchasable −1.5; promising 0; unresolved −5; conflict −18.');
    if (!m.rankings.length) lines.push('- У збережених рядках немає ranking-компонентів для числового аудиту.');
    m.rankings.forEach(item => {
      const finalCheck = item.recomputedFinal === null ? '—' : num(item.recomputedFinal);
      const stored = item.finalStored === null ? '—' : num(item.finalStored);
      const drift = item.delta === null ? '—' : (Math.abs(item.delta) <= 0.2 ? 'OK' : `Δ=${item.delta.toFixed(2)}`);
      lines.push(`- ${item.name}: S=${num(item.structural)}, L=${num(item.linguistic)}, Q=${num(item.quality)}, U=${num(item.userFit)}, A=${num(item.adaptive)}, I=${num(item.identity)}, Opportunity=${num(item.opportunity)}, EvidenceConfidence=${num(item.evidenceConfidence)}, Coverage=${num(item.coverage)}%, state=${item.state}, penalty=${item.penalty}; Final stored=${stored}, recomputed=${finalCheck} [${drift}]. ${item.identityFormula}`);
    });

    lines.push('', 'D. ДИНАМІКА МІЖ ЗАПУСКАМИ');
    if (!m.runs.length) lines.push('- Немає run_id у кандидатів — порівняння партій неможливе.');
    m.runs.forEach((run, index) => {
      const s = run.states;
      lines.push(`- RUN ${run.id} | status=${run.status} | N=${run.count} | strict-free=${s.claimable} (${pct(s.claimable, run.count)}) | promising=${s.promising} (${pct(s.promising, run.count)}) | conflict=${s.conflict} (${pct(s.conflict, run.count)}) | avg Final=${num(run.avgFinal)} | avg user-fit=${num(run.avgUserFit)}${run.prompt ? ` | prompt=${run.prompt}` : ''}`);
      if (index > 0) {
        const prev = m.runs[index - 1];
        if (run.avgFinal !== null && prev.avgFinal !== null) lines.push(`  Δ avg Final vs previous run = ${(run.avgFinal - prev.avgFinal).toFixed(1)}.`);
        if (run.avgUserFit !== null && prev.avgUserFit !== null) lines.push(`  Δ avg user-fit vs previous run = ${(run.avgUserFit - prev.avgUserFit).toFixed(1)}.`);
        if (run.status !== 'complete' && run.status !== 'completed') lines.push('  Поточний run не завершений: його дельти не можна трактувати як фінальний ефект адаптації.');
      }
    });

    lines.push('', 'E. ПРАВИЛО ДОКАЗОВОСТІ');
    lines.push('- «Подобається напрям» дозволено писати як стійкий висновок лише коли 95% Wilson-інтервал частки лайків повністю вище 50%. Якщо інтервал перетинає 50%, формулювання має бути «попередній сигнал / недостатньо даних».');
    lines.push('- «Вільне» дозволено лише для status=claimable. not_found, browser-absence або purchasable не можуть математично чи текстово перетворюватися на strict-green.');
    return lines.join('\n');
  }

  function html(rowsInput) {
    const m = model(rowsInput);
    const f = m.feedback;
    const familyRows = m.families.length ? m.families.map(item => {
      const ci = item.interval ? `${(item.interval.low * 100).toFixed(1)}–${(item.interval.high * 100).toFixed(1)}%` : '—';
      return `<tr><td>${escapeHtml(FAMILY_LABELS[item.family] || item.family)}</td><td>${item.rated}/${item.total}</td><td>${pct(item.liked, item.rated)}</td><td>${item.net.toFixed(3)}</td><td>${ci}</td><td>${item.confidence.toFixed(3)}</td><td>${escapeHtml(item.inference)}</td></tr>`;
    }).join('') : '<tr><td colspan="7">Немає достатньо оцінених прикладів.</td></tr>';
    const rankingRows = m.rankings.length ? m.rankings.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${num(item.quality)}</td><td>${num(item.userFit)}</td><td>${num(item.identity)}</td><td>${num(item.opportunity)}</td><td>${escapeHtml(item.state)}</td><td>${num(item.finalStored)}</td><td>${num(item.recomputedFinal)}</td></tr>`).join('') : '<tr><td colspan="8">Ranking-компоненти відсутні.</td></tr>';
    const runRows = m.runs.length ? m.runs.map(run => `<tr><td>${escapeHtml(run.id)}</td><td>${escapeHtml(run.status)}</td><td>${run.count}</td><td>${pct(run.states.claimable, run.count)}</td><td>${pct(run.states.promising, run.count)}</td><td>${pct(run.states.conflict, run.count)}</td><td>${num(run.avgFinal)}</td><td>${num(run.avgUserFit)}</td></tr>`).join('') : '<tr><td colspan="8">Run-дані відсутні.</td></tr>';
    const interval = f.interval ? `${(f.interval.low * 100).toFixed(1)}–${(f.interval.high * 100).toFixed(1)}%` : '—';
    return `<section class="nm-math-report"><div class="section-title"><div><h2>Математична основа висновків</h2><p>Чисельники, знаменники, невизначеність і формули замість неаргументованих висновків.</p></div></div>
      <div class="searchbox"><strong>Явний фідбек:</strong> n=${f.rated}; 👍 ${f.liked}; 👎 ${f.disliked}; approval=${pct(f.liked, f.rated)}; 95% Wilson CI=${interval}; confidence(n)=1−e^(−n/5)=${f.confidence.toFixed(3)}.</div>
      <h3>Смак за сім’ями</h3><div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr><th>Сім’я</th><th>оцінено/всього</th><th>approval</th><th>net</th><th>95% CI</th><th>confidence</th><th>висновок</th></tr></thead><tbody>${familyRows}</tbody></table></div>
      <h3>Аудит ranking-формули</h3><p>Final = 0.72×Identity + 0.28×Opportunity + penalty; семантичний статус не виводиться зі score.</p><div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr><th>Назва</th><th>Q</th><th>U</th><th>I</th><th>Opportunity</th><th>state</th><th>Final</th><th>recalc</th></tr></thead><tbody>${rankingRows}</tbody></table></div>
      <h3>Динаміка run-ів</h3><div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr><th>Run</th><th>status</th><th>N</th><th>strict-free</th><th>promising</th><th>conflict</th><th>avg Final</th><th>avg user-fit</th></tr></thead><tbody>${runRows}</tbody></table></div>
      <div class="warning">Стійкий висновок про смак дозволений лише коли 95% Wilson-інтервал не перетинає 50%. «Вільне» — лише status=claimable.</div>
    </section>`;
  }

  window.nameMachineReportMath = { model, text, html, wilson, version: 'report-math-v6' };
})();
