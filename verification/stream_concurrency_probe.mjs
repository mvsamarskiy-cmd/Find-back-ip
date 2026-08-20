const base = (process.env.NAMEMACHINE_PRODUCTION_URL || 'https://web-production-04fec.up.railway.app').replace(/\/$/, '');
const streamController = new AbortController();
const streamBody = JSON.stringify({
  brief: 'Коротка природна назва для каналу про птахів',
  count: 1,
  preferences: {},
  search_context: {mode: 'new_brand', brand_name: '', guidance: ''},
  brand_dna: null,
  resources: ['com'],
  required_resources: ['com'],
  generation_context: {batch_number: 1, exclude_names: [], conflict_names: [], successful_names: []},
});

let streamResponse;
try {
  streamResponse = await fetch(base + '/api/ai-generate-stream', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: streamBody,
    signal: streamController.signal,
  });
  if (!streamResponse.ok) throw new Error(`stream start HTTP ${streamResponse.status}`);
  const reader = streamResponse.body.getReader();
  const first = await Promise.race([
    reader.read(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('stream did not emit initial bytes within 10s')), 10000)),
  ]);
  if (first.done || !first.value?.length) throw new Error('stream emitted no initial bytes');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  const started = Date.now();
  let health;
  try {
    health = await fetch(base + '/health', {signal: controller.signal, cache: 'no-store'});
  } catch (error) {
    const elapsed = Date.now() - started;
    throw new Error(`health blocked behind active stream for >=${elapsed}ms (${error.name})`);
  } finally {
    clearTimeout(timer);
  }
  const elapsed = Date.now() - started;
  if (health.status !== 200) throw new Error(`health HTTP ${health.status} during active stream`);
  console.log(JSON.stringify({active_stream_health_ms: elapsed, status: health.status}, null, 2));
  if (elapsed > 3000) throw new Error(`health took ${elapsed}ms during active stream; expected <=3000ms`);
} finally {
  streamController.abort();
}
