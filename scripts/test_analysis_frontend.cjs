// Offline frontend race tests: node --test scripts/test_analysis_frontend.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');

const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/app.js'), 'utf8');
const helpers = source.slice(source.indexOf('let currentAbortController'), source.indexOf('let currentMode'));
const polling = source.slice(source.indexOf('let analysisStatusTimer'), source.indexOf('function setAnalysisRunning'));

function setup(fetch) {
  const elements = new Map();
  const states = [];
  const calls = [];
  let interval;
  const context = vm.createContext({
    crypto: { randomUUID }, AbortController, Headers, DOMException, console,
    fetch: (...args) => { calls.push(args); return fetch(...args); },
    setInterval: fn => { interval = fn; return 1; }, clearInterval() {},
    document: { getElementById: id => {
      if (!elements.has(id)) elements.set(id, { textContent: '', classList: { add() {}, remove() {} } });
      return elements.get(id);
    } },
    setAnalysisRunning: value => states.push(value),
    setAnalysisStep: () => {}, setSubtitles: () => {}, applyLanguageState: () => {},
    renderMarkdownNote: () => {}, loadLibrary: () => {},
  });
  vm.runInContext(`let mediaGeneration = 0; let currentNoteId = null; let currentVideoId = null; let currentVideoInfo = {};
    ${helpers}\n${polling}`, context);
  return { context, states, calls, elements, poll: () => interval(), run: code => vm.runInContext(code, context) };
}

test('an old finally cannot clear the controller or hide a new analysis', () => {
  const env = setup(async () => ({ ok: true, json: async () => ({}) }));
  env.run('var old = beginAnalysis(); var next = beginAnalysis(); finishAnalysis(old);');
  assert.equal(env.run('currentAnalysisJob === next && currentAbortController === next.controller'), true);
  assert.deepEqual(env.states, []);
  assert.match(env.calls[0][0], /job_id=/);
  assert.equal(env.run('old.controller.signal.aborted'), true);
});

test('late polling cannot write a new jobs loading screen', async () => {
  let release;
  const env = setup(async url => {
    if (url.includes('/cancel')) return { ok: true, json: async () => ({}) };
    return new Promise(resolve => { release = resolve; });
  });
  env.run('var old = beginAnalysis(); startAnalysisStatusPolling();');
  const pending = env.poll();
  env.run('var next = beginAnalysis();');
  release({ ok: true, json: async () => ({ job_id: env.run('old.id'), status: 'processing', message: 'stale', step: 3 }) });
  await pending;
  assert.equal(env.elements.get('loading-desc'), undefined);
});

test('late fetch responses are rejected even when HTTP succeeded', async () => {
  let release;
  const env = setup(async url => {
    if (url.includes('/cancel')) return { ok: true };
    return new Promise(resolve => { release = resolve; });
  });
  env.run('var old = beginAnalysis();');
  const pending = env.run('analysisFetch(old, "/api/local/analyze", {method: "POST"})');
  env.run('beginAnalysis();');
  release({ ok: true });
  await assert.rejects(pending, { name: 'AbortError' });
});

test('the analysis id and its own signal travel with each request', async () => {
  const env = setup(async () => ({ ok: true }));
  env.run('var job = beginAnalysis();');
  await env.run('analysisFetch(job, "/api/local/analyze", {method: "POST"})');
  assert.equal(env.calls[0][1].headers.get('X-Analysis-Id'), env.run('job.id'));
  assert.equal(env.calls[0][1].signal, env.run('job.controller.signal'));
});

test('oversized local video is rejected before uploading', async () => {
  const env = setup(async () => ({ ok: true, json: async () => ({ max_local_video_bytes: 10 }) }));
  await assert.rejects(env.run('validateLocalVideoFile({size: 11})'));
  assert.equal(env.calls.length, 1);
  assert.equal(env.calls[0][0], '/api/config');
});

test('checkpoint recovery cannot overwrite a newer media context', async () => {
  let release;
  const env = setup(async () => new Promise(resolve => { release = resolve; }));
  env.run('var job = beginAnalysis();');
  const pending = env.run('recoverAnalysisCheckpoint(job, {checkpoint_note_id: "checkpoint"})');
  env.run('mediaGeneration++;');
  release({ ok: true, json: async () => ({ metadata: { video_id: 'old', subtitles: [] }, markdown: 'old' }) });
  await pending;
  assert.equal(env.run('currentNoteId'), null);
});
