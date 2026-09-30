// Focused BOS3-TRAINING-01 check. Actual JSX is Babel-compiled and rendered
// with controlled hooks and local-storage simulation only: no browser, HTTP,
// database, external CRM, or product writes.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const rootFlag = process.argv.indexOf('--root');
assert.notEqual(rootFlag, -1, 'Pass --root <candidate-path>.');
const root = path.resolve(process.argv[rootFlag + 1] || '');
const html = fs.readFileSync(path.join(root, 'frontend', 'boss_app_source.html'), 'utf8');
const guideDoc = fs.readFileSync(path.join(root, 'docs', 'learning', 'BOS_3_0_UA.md'), 'utf8');
const versionSource = fs.readFileSync(path.join(root, 'boss_project', 'version.py'), 'utf8');
const babel = require(path.join(root, 'assets', 'babel.js'));

function slice(prefix, endMarker) {
  const start = html.indexOf(prefix);
  const end = html.indexOf(endMarker, start);
  assert(start !== -1 && end !== -1 && end > start, `Cannot isolate ${prefix}.`);
  return html.slice(start, end);
}

function walk(node, out = []) {
  if (node == null || node === false) return out;
  if (Array.isArray(node)) {
    node.forEach(value => walk(value, out));
    return out;
  }
  if (typeof node === 'object') {
    out.push(node);
    walk(node.children, out);
  }
  return out;
}

function text(node) {
  if (node == null || node === false) return '';
  if (Array.isArray(node)) return node.map(text).join(' ');
  return typeof node === 'object' ? text(node.children) : String(node);
}

function actualNav() {
  const source = slice('const NAV=[', 'const THEMES=');
  const context = {};
  vm.createContext(context);
  const compiled = babel.transform(source, { presets: ['react'], compact: false }).code;
  vm.runInContext(`${compiled}\nglobalThis.value=NAV;`, context);
  return context.value;
}

function localStore(seed = {}) {
  const values = new Map(Object.entries(seed));
  return {
    values,
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
}

function trainingHarness({ role = 'ceo', storage = localStore() } = {}) {
  let cursor = 0;
  let dirty = true;
  let tree = null;
  const hooks = [];
  const effects = [];
  const navigations = [];
  let exported = null;
  const document = {
    body: { appendChild() {} },
    createElement(name) {
      assert.equal(name, 'a');
      return { click() { this.clicked = true; }, remove() {} };
    },
  };
  class TestBlob {
    constructor(parts, options) {
      this.parts = parts;
      this.options = options;
      exported = this;
    }
  }
  const React = {
    Fragment: 'fragment',
    createElement(type, props, ...children) { return { type, props: props || {}, children }; },
  };
  const window = {
    BOS_RUNTIME: { mode: 'demo', user_id: 17, role, access_revision: 'training-r1' },
    dispatchEvent() {},
  };
  const context = {
    React,
    window,
    document,
    localStorage: storage,
    CustomEvent: class CustomEvent { constructor(name, detail) { this.name = name; this.detail = detail; } },
    Object,
    Array,
    String,
    Number,
    Math,
    JSON,
    Blob: TestBlob,
    URL: { createObjectURL: () => 'blob:training-check', revokeObjectURL() {} },
    setTimeout() { return 1; },
    Button: function Button() {},
    Select: function Select() {},
    bosRole: () => role,
    bosCan(key) {
      if (['finance', 'hr_private'].includes(key)) return role === 'ceo';
      if (key === 'write') return ['ceo', 'manager'].includes(role);
      return false;
    },
    useState(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [hooks[index].value, value => {
        hooks[index].value = typeof value === 'function' ? value(hooks[index].value) : value;
        dirty = true;
      }];
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      const old = hooks[index];
      if (!old || dependencies.some((value, position) => value !== old.dependencies[position])) {
        hooks[index] = { dependencies, cleanup: old?.cleanup };
        effects.push(() => { hooks[index].cleanup?.(); hooks[index].cleanup = callback(); });
      }
    },
  };
  const helperSource = slice('function bosStorageKey(', '// Error Boundary');
  const guideSource = slice('function BoSProductGuide(', 'function BoSReadOnlyRecords(')
    .replace(' const fallbackProgress=', ' globalThis.trainingCases=cases;\n const fallbackProgress=')
    .replace(' const previewFields=', ' globalThis.trainingPreview=preview;\n const previewFields=');
  const compiled = babel.transform(helperSource + guideSource, { presets: ['react'], compact: false }).code;
  vm.createContext(context);
  vm.runInContext(`${compiled}\nglobalThis.Component=BoSProductGuide;`, context);
  function render() {
    cursor = 0;
    dirty = false;
    tree = context.Component({ onNavigate: (section, sub) => navigations.push({ section, sub }) });
    while (effects.length) effects.shift()();
  }
  function flush() {
    for (let index = 0; index < 8 && dirty; index += 1) render();
  }
  render();
  flush();
  return {
    context,
    storage,
    cases: () => JSON.parse(JSON.stringify(context.trainingCases)),
    preview: () => JSON.parse(JSON.stringify(context.trainingPreview)),
    nodes: () => walk(tree),
    currentText: () => text(tree),
    selectCase(id) {
      const select = walk(tree).find(node => node.type === context.Select && node.props['aria-label'] === 'Оберіть навчальний кейс');
      assert(select, 'Missing native Select for educational case choice.');
      select.props.onChange({ target: { value: id } });
      flush();
    },
    stepButtons() { return walk(tree).filter(node => node.type === context.Button && /Відкрити крок|Недоступно цій ролі/.test(text(node))); },
    openAllAllowedSteps() {
      const steps = this.stepButtons();
      steps.filter(node => !node.props.disabled).forEach(node => { node.props.onClick(); flush(); });
    },
    download() {
      const button = walk(tree).find(node => node.type === context.Button && text(node) === 'Завантажити JSON-чернетку');
      assert(button, 'Missing CRM draft download button.');
      button.props.onClick();
      return exported;
    },
    navigations,
  };
}

function navAllows(nav, step) {
  const section = nav.find(item => item.id === step.section);
  return !!section && (step.sub === null || section.subs.some(item => item.id === step.sub));
}

const requiredRoutes = {
  'BOS3-CASE-01': [['erp', 'sales'], ['erp', 'stock'], ['dash', null]],
  'BOS3-CASE-02': [['erp', 'production'], ['erp', 'purchase'], ['erp', 'stock'], ['erp', 'quality'], ['dash', null]],
  'BOS3-CASE-03': [['heli', null], ['erp', 'costs'], ['hr', 'tasks']],
};
const passed = [];
function test(name, callback) {
  callback();
  passed.push(name);
  console.log(`PASS ${name}`);
}

const nav = actualNav();
const harness = trainingHarness();
const cases = harness.cases();

test('three uniquely coded fictional cases have owner, handoffs, next action, and semantic NAV routes', () => {
  assert.deepEqual(cases.map(item => item.id), ['BOS3-CASE-01', 'BOS3-CASE-02', 'BOS3-CASE-03']);
  assert.equal(new Set(cases.map(item => item.id)).size, 3);
  for (const item of cases) {
    assert.equal(typeof item.owner_role, 'string');
    assert(item.owner_role.length > 0, `${item.id} has no owner role.`);
    assert.equal(typeof item.next_action, 'string');
    assert(item.next_action.length > 0, `${item.id} has no next action.`);
    assert(Array.isArray(item.handoffs) && item.handoffs.length > 0, `${item.id} has no department handoffs.`);
    assert(item.handoffs.every(value => typeof value === 'string' && value.includes('→')),
      `${item.id} handoffs must identify department transfer.`);
    assert.deepEqual(item.steps.map(({ section, sub }) => [section, sub]), requiredRoutes[item.id]);
    assert(item.steps.every(step => navAllows(nav, step)), `${item.id} contains a destination absent from NAV.`);
  }
});

test('each rendered case exposes human CRM labels and calls only its permitted destinations', () => {
  for (const item of cases) {
    harness.selectCase(item.id);
    const rendered = harness.currentText();
    assert(rendered.includes(item.owner_role), `${item.id} owner is not rendered.`);
    assert(rendered.includes(item.next_action), `${item.id} next action is not rendered.`);
    assert(item.handoffs.every(value => rendered.includes(value)), `${item.id} handoff is not rendered.`);
    for (const label of ['Клієнт', 'Потреба', 'Відповідальна роль', 'Наступна дія', 'Етап чернетки', 'Коди джерел']) {
      assert(rendered.includes(label), `Human CRM label is missing: ${label}`);
    }
    const before = harness.navigations.length;
    harness.openAllAllowedSteps();
    assert.deepEqual(harness.navigations.slice(before), item.steps.map(({ section, sub }) => ({ section, sub })));
  }
});

test('CRM preview and exported JSON are schema-matched, synthetic, and non-creating', () => {
  for (const item of cases) {
    harness.selectCase(item.id);
    const preview = harness.preview();
    assert.deepEqual(Object.keys(preview), [
      'schema', 'synthetic', 'crm_record_created', 'case_id', 'client', 'need',
      'owner_role', 'next_action', 'stage', 'source_codes',
    ]);
    assert.equal(preview.schema, 'bos.training.crm-handoff.v1');
    assert.equal(preview.synthetic, true);
    assert.equal(preview.crm_record_created, false);
    assert.equal(preview.case_id, item.id);
    assert.equal(preview.client, item.client);
    assert.equal(preview.need, item.need);
    assert.equal(preview.owner_role, item.owner_role);
    assert.equal(preview.next_action, item.next_action);
    assert.equal(preview.stage, item.stage);
    assert.deepEqual(preview.source_codes, item.source_codes);
    const blob = harness.download();
    assert.equal(blob.options.type, 'application/json');
    assert.deepEqual(JSON.parse(blob.parts.join('')), preview);
  }
});

test('role-isolated local progress validates shape and unavailable actions stay disabled', () => {
  const shared = localStore();
  const ceo = trainingHarness({ storage: shared });
  ceo.selectCase('BOS3-CASE-02');
  const ceoSteps = ceo.stepButtons();
  assert.equal(ceoSteps.length, 5);
  ceoSteps[3].props.onClick();
  const ceoKey = 'bos:demo:17:ceo:bos.training.v3';
  assert.deepEqual(JSON.parse(shared.getItem(ceoKey)), { caseId: 'BOS3-CASE-02', step: 3 });
  const observer = trainingHarness({ storage: shared, role: 'observer' });
  assert.equal(observer.preview().case_id, 'BOS3-CASE-01', 'Observer must not inherit CEO lesson progress.');
  observer.selectCase('BOS3-CASE-03');
  const blocked = observer.stepButtons().filter(node => node.props.disabled);
  assert(blocked.length > 0, 'Observer needs unavailable learning actions to be visibly disabled.');
  assert(blocked.every(node => text(node) === 'Недоступно цій ролі'), 'Disabled actions must state the role limit.');
  const observerKey = 'bos:demo:17:observer:bos.training.v3';
  shared.setItem(observerKey, JSON.stringify({ caseId: 'not-a-case', step: 999 }));
  const normalized = trainingHarness({ storage: shared, role: 'observer' });
  assert.equal(normalized.preview().case_id, 'BOS3-CASE-01');
  assert.deepEqual(JSON.parse(shared.getItem(observerKey)), { caseId: 'BOS3-CASE-01', step: 0 });
});

test('BoS 3.0 remains learning-only, with no runtime version change or transport', () => {
  assert.match(guideDoc, /BoS 3\.0 тут є назвою навчальної моделі, а не заявою про випуск технічної версії 3\.0\./);
  assert.match(versionSource, /VERSION = '0\.2\.18-current'/);
  const guide = slice('function BoSProductGuide(', 'function BoSReadOnlyRecords(');
  assert.match(guide, /Навчальна модель BoS 3\.0/);
  assert.match(guide, /не технічна версія 3\.0: основа застосунку лишається v18/);
  assert.match(guide, /лише в цьому браузері для поточного облікового запису/);
  assert.doesNotMatch(guide, /fetch\s*\(/);
  assert.match(slice('function App(', 'function AuthGate('), /if\(section==='info'\) return <BoSProductGuide/);
});

console.log(JSON.stringify({
  schema: 'bos3.training.focused.v2',
  result: 'PASS',
  checks: passed,
  scope: 'actual JSX Babel parse, controlled hooks, and local export simulation; no DOM, browser, HTTP, database, external CRM, or product writes',
}, null, 2));
