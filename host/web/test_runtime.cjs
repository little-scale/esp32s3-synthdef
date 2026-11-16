'use strict';
// A page reload during a hardware job must not touch the leased device before
// cached progress completes. Run the real startup function with an unavailable
// device API until that completion, rather than mirroring button implementation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/app.js', 'utf8');
const start = source.slice(source.indexOf('async function startStudio()'), source.indexOf('\ntask(startStudio);'));
async function story(active, pendingCompleted = false) {
  const calls = []; let leased = active;
  const context = {
    config: {runtime_job: {active, job: 'job-1'}, connected: true, module_groups: true, compiler_ready: true},
    sessionStorage: {getItem: () => pendingCompleted ? 'job-1' : null, setItem() {}},
    token: 'test', $: () => ({}),
    ports: async () => { calls.push('ports'); },
    renderNetworks() {}, loadEditor() {}, renderGroups() {}, renderDevice() { calls.push('render'); },
    showView(name) { calls.push(name); },
    async pollRuntimeJob() { calls.push('poll'); leased = false; },
    async api(path) { assert.equal(leased, false, 'device API reached during runtime handoff'); calls.push(path); return {}; },
  };
  vm.createContext(context); vm.runInContext(start + '\nthis.start = startStudio;', context);
  await context.start();
  if (active || pendingCompleted) {
    assert.deepEqual(calls, ['ports', 'runtimes', 'poll', 'ports', 'groups']);
  } else {
    assert.deepEqual(calls, ['ports', 'refresh', 'render', 'groups']);
  }
}
(async () => { await story(true); await story(false); await story(false, true); process.stdout.write('PASS: active/completed runtime-job reload and ordinary Studio startup\n'); })().catch(error => { console.error(error); process.exitCode = 1; });
