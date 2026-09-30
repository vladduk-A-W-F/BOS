// One-purpose QA-EXCEPTION check for the historical training progress defect.
// It reads the frozen Git object, uses controlled JSX rendering, and never
// starts a browser/server or touches a database or product file.
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const EXPECTED_COMMIT = 'a445ac0584c79c2939269b37ec814b22691711c7';
const rootFlag = process.argv.indexOf('--root');
assert.notEqual(rootFlag, -1, 'Pass --root <candidate-path>.');
const root = path.resolve(process.argv[rootFlag + 1] || '');

function frozenFile(relativePath) {
  return childProcess.execFileSync('git', ['-C', root, 'show', `${EXPECTED_COMMIT}:${relativePath}`], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function sourceSlice(source, prefix, endMarker) {
  const start = source.indexOf(prefix);
  const end = source.indexOf(endMarker, start);
  assert(start !== -1 && end !== -1 && end > start, `Cannot isolate ${prefix}.`);
  return source.slice(start, end);
}

function walk(node, nodes = []) {
  if (node == null || node === false) return nodes;
  if (Array.isArray(node)) {
    node.forEach(value => walk(value, nodes));
    return nodes;
  }
  if (typeof node === 'object') {
    nodes.push(node);
    walk(node.children, nodes);
  }
  return nodes;
}

function text(node) {
  if (node == null || node === false) return '';
  if (Array.isArray(node)) return node.map(text).join(' ');
  return typeof node === 'object' ? text(node.children) : String(node);
}

const html = frozenFile('frontend/boss_app_source.html');
const babel = require(path.join(root, 'assets', 'babel.js'));
const values = new Map();
const localStorage = {
  getItem(key) { return values.get(key) ?? null; },
  setItem(key, value) { values.set(key, String(value)); },
};
const hooks = [];
const queuedEffects = [];
let cursor = 0;
let tree;
let effectsExecuted = 0;
let unmounted = false;
let observation;

const React = {
  Fragment: 'fragment',
  createElement(type, props, ...children) { return { type, props: props || {}, children }; },
};
const context = {
  React,
  Array,
  Blob: class Blob {},
  Button: function Button() {},
  CustomEvent: class CustomEvent { constructor(name, detail) { this.name = name; this.detail = detail; } },
  JSON,
  Math,
  Number,
  Object,
  Select: function Select() {},
  String,
  URL: { createObjectURL() { return 'blob:exception'; }, revokeObjectURL() {} },
  document: { body: { appendChild() {} }, createElement() { return { click() {}, remove() {} }; } },
  localStorage,
  window: {
    BOS_RUNTIME: { mode: 'demo', user_id: 17, role: 'ceo', access_revision: 'b30-progress-exception' },
    dispatchEvent() {},
  },
  bosCan() { return true; },
  bosRole() { return 'ceo'; },
  useEffect(callback) { queuedEffects.push(callback); },
  useState(initial) {
    const index = cursor++;
    if (!hooks[index]) hooks[index] = { value: typeof initial === 'function' ? initial() : initial };
    return [hooks[index].value, value => {
      hooks[index].value = typeof value === 'function' ? value(hooks[index].value) : value;
    }];
  },
};

const helperSource = sourceSlice(html, 'function bosStorageKey(', '// Error Boundary');
const guideSource = sourceSlice(html, 'function BoSProductGuide(', 'function BoSReadOnlyRecords(');
const compiled = babel.transform(helperSource + guideSource, { presets: ['react'], compact: false }).code;
vm.createContext(context);
vm.runInContext(`${compiled}\nglobalThis.Component=BoSProductGuide;`, context);

function render() {
  cursor = 0;
  tree = context.Component({
    onNavigate(section, sub) {
      observation = {
        route: { section, sub },
        storage_at_navigation: localStorage.getItem('bos:demo:17:ceo:bos.training.v3'),
        effects_executed: effectsExecuted,
      };
      unmounted = true;
    },
  });
}

render();
const select = walk(tree).find(node => node.type === context.Select
  && node.props['aria-label'] === 'Оберіть навчальний кейс');
assert(select, 'Expected the actual native training case Select.');
select.props.onChange({ target: { value: 'BOS3-CASE-02' } });
render();

const steps = walk(tree).filter(node => node.type === context.Button && text(node) === 'Відкрити крок');
assert.equal(steps.length, 5, 'BOS3-CASE-02 must expose its five allowed steps.');
steps[3].props.onClick();

assert.equal(unmounted, true, 'The test must simulate immediate navigation/unmount.');
assert.equal(effectsExecuted, 0, 'No React effect may flush before the oracle is read.');
assert.deepEqual(observation.route, { section: 'erp', sub: 'quality' });
assert.deepEqual(JSON.parse(observation.storage_at_navigation), { caseId: 'BOS3-CASE-02', step: 3 });

console.log(JSON.stringify({
  schema: 'bos.b30.progress-exception.v1',
  result: 'PASS',
  candidate_commit: EXPECTED_COMMIT,
  source_sha256: crypto.createHash('sha256').update(html, 'utf8').digest('hex'),
  harness_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),
  checks: ['case-02-quality-progress-is-persisted-inside-onNavigate-before-effects-or-unmount'],
  observation,
  scope: 'one controlled JSX/VM/localStorage oracle; no browser, HTTP/TCP, Django, database, external CRM, or product writes',
}, null, 2));
