// Focused JSX checks for the v18 start guide and distinct overview routes.
// This is a Babel + controlled-hook test, not a DOM, browser, HTTP, or E2E test.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const rootFlag = process.argv.indexOf('--root');
assert.notEqual(rootFlag, -1, 'Pass --root <candidate-path>.');
const root = path.resolve(process.argv[rootFlag + 1] || '');
const htmlPath = path.join(root, 'frontend', 'boss_app_source.html');
const babelPath = path.join(root, 'assets', 'babel.js');
assert(fs.existsSync(htmlPath), 'Candidate frontend source is missing.');
assert(fs.existsSync(babelPath), 'Candidate Babel runtime is missing.');
const html = fs.readFileSync(htmlPath, 'utf8');
const babel = require(babelPath);

function functionSlice(prefix, endMarker) {
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

function mount(componentSource, componentName, contextValues, props = {}) {
  let tree = null;
  let cursor = 0;
  let dirty = true;
  let unmounted = false;
  const hooks = [];
  const effects = [];
  const events = new Map();
  const React = {
    Fragment: 'fragment',
    createElement(type, elementProps, ...children) {
      const value = { type, props: elementProps || {}, children };
      if (value.props.ref && value.props.ref.current === null) {
        value.props.ref.current = { close() {}, showModal() {} };
      }
      return value;
    },
  };
  const window = {
    BOS_RUNTIME: { user_id: 1, mode: 'demo', role: 'ceo', access_revision: 'r1' },
    addEventListener(name, handler) {
      if (!events.has(name)) events.set(name, new Set());
      events.get(name).add(handler);
    },
    removeEventListener(name, handler) { events.get(name)?.delete(handler); },
  };
  const context = {
    React,
    window,
    console,
    AbortController,
    setTimeout,
    clearTimeout,
    Number,
    Object,
    Array,
    Error,
    Set,
    Math,
    ...contextValues,
    useState(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [hooks[index].value, value => {
        if (unmounted) return;
        hooks[index].value = typeof value === 'function' ? value(hooks[index].value) : value;
        dirty = true;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { current: initial };
      return hooks[index];
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      const old = hooks[index];
      if (!old || dependencies.some((value, position) => value !== old.dependencies[position])) {
        hooks[index] = { dependencies, cleanup: old?.cleanup };
        effects.push(() => {
          hooks[index].cleanup?.();
          hooks[index].cleanup = callback();
        });
      }
    },
  };
  vm.createContext(context);
  const compiled = babel.transform(componentSource, { presets: ['react'], compact: false }).code;
  vm.runInContext(`${compiled}\nthis.Component=${componentName};`, context);
  function render() {
    if (unmounted) return;
    cursor = 0;
    dirty = false;
    tree = context.Component(props);
    while (effects.length) effects.shift()();
  }
  async function flush() {
    for (let index = 0; index < 12; index += 1) {
      await new Promise(resolve => setImmediate(resolve));
      if (dirty) render();
    }
  }
  render();
  return {
    context,
    window,
    flush,
    tree: () => tree,
    all: () => walk(tree),
    destroy() {
      unmounted = true;
      hooks.forEach(hook => hook?.cleanup?.());
    },
  };
}

function gateHarness(mode) {
  const requests = [];
  const source = functionSlice('function AuthGate(', 'ReactDOM.createRoot');
  const response = body => ({ ok: true, status: 200, json: async () => body });
  const harness = mount(source, 'AuthGate', {
    T: { text: '#fff', textMuted: '#aaa', primary: '#9cf', red: '#f99', surface: '#111', font: 'sans-serif' },
    Button: function Button() {},
    Input: function Input() {},
    fetch: async url => {
      requests.push(url);
      if (url === '/api/auth/csrf/') return response({ mode });
      if (url === '/api/auth/me/') return { ok: false, status: 401, json: async () => ({ error: 'not signed in' }) };
      throw new Error(`Unexpected AuthGate request: ${url}`);
    },
  });
  return { ...harness, requests };
}

function overviewHarness(readOnlyOverview) {
  const source = functionSlice('function BoSHome(', 'function BoSProductGuide(');
  const snapshot = {
    as_of: '2026-09-26',
    home: {
      financial: [{ currency: 'UAH', revenue: '100.00' }],
      tasks: [{ id: 1, archived: false, is_overdue: false, status: 'open', title: 'Follow up' }],
    },
    orders: [{ id: 2, code: 'SO-START', customer_id: 3 }],
    lines: [{ id: 4, order_id: 2, quantity: '1', shipped: '0' }],
    lots: [],
    jobs: [],
    invoices: [],
    events: [],
    partners: [{ id: 3, name: 'Demo partner' }],
    employees: [],
  };
  return mount(source, 'BoSHome', {
    homeReadScope: () => '1:demo:ceo:r1',
    homeSnapshotShape: () => true,
    homeKnownNumber: value => typeof value === 'string' && /^-?\d+(?:\.\d+)?$/.test(value),
    homeBusinessDate: value => value,
    bosCan: key => key === 'finance',
    bosCanAction: () => true,
    b03Positive: value => Number(value) > 0,
    b03OpenLine: line => String(Number(line.quantity) - Number(line.shipped)),
    erpNum: value => String(value),
    erpDate: value => value || '-',
    c01Assignee: value => value.title,
    BOS_METRICS: [['revenue', 'Revenue', 'fixture formula']],
    B03_ACTIONS: {},
    ERP_ACTIONS: {},
    Button: function Button() {},
    Select: function Select() {},
    Card: function Card() {},
    ERPTable: function ERPTable() {},
    NextAction: function NextAction() {},
    B03PendingLauncher: function B03PendingLauncher() {},
    WorkpointsPanel: function WorkpointsPanel() {},
    BoSInspector: function BoSInspector() {},
    BoSActionDialog: function BoSActionDialog() {},
    SupplierInvoiceReceipt: function SupplierInvoiceReceipt() {},
    ImpactTable: function ImpactTable() {},
    HttpObservations: function HttpObservations() {},
    fetch: async url => {
      assert.equal(url, '/api/erp/snapshot/');
      return {
        ok: true,
        status: 200,
        headers: { get: name => name === 'X-BoS-Access' ? 'r1' : null },
        json: async () => snapshot,
      };
    },
  }, { onNavigate() {}, refetchTasks() {}, readOnlyOverview });
}

function componentNodes(harness, type) {
  return harness.all().filter(node => node.type === type);
}

async function run() {
  const results = [];
  const test = async (name, callback) => {
    await callback();
    results.push(name);
    console.log(`PASS ${name}`);
  };

  await test('AuthGate demo renders brochure and preserves normal credentials', async () => {
    const harness = gateHarness('demo');
    await harness.flush();
    const nodes = harness.all();
    assert.deepEqual(harness.requests, ['/api/auth/csrf/', '/api/auth/me/']);
    assert(nodes.some(node => node.type === 'form'), 'Normal credential form must remain available in demo mode.');
    assert(nodes.some(node => node.type === 'a' && node.props.href === '/help/start.pdf'),
      'Demo AuthGate must link the fixed start brochure.');
    const inputs = nodes.filter(node => node.type === harness.context.Input);
    assert(inputs.some(node => node.props.autoComplete === 'username'), 'Username field is missing.');
    assert(inputs.some(node => node.props.type === 'password' && node.props.autoComplete === 'current-password'),
      'Password field is missing.');
    assert(nodes.some(node => node.type === harness.context.Button && /навчальну компанію/.test(text(node))),
      'Existing passwordless local demo entry must remain visible in demo mode.');
    harness.destroy();
  });

  await test('AuthGate working mode keeps credentials but does not link unavailable brochure', async () => {
    const harness = gateHarness('working');
    await harness.flush();
    const nodes = harness.all();
    assert(nodes.some(node => node.type === 'form'), 'Normal credential form must remain available in working mode.');
    assert(!nodes.some(node => node.type === 'a' && node.props.href === '/help/start.pdf'),
      'Working AuthGate must not link a demo-only brochure endpoint.');
    assert(!nodes.some(node => node.type === harness.context.Button && /навчальну компанію/.test(text(node))),
      'Demo entry must not appear in working mode.');
    harness.destroy();
  });

  await test('navigation has distinct helicopter and daily labels and props', async () => {
    assert.match(html, /\{id:'heli',label:'Вертоліт',/);
    assert.match(html, /\{id:'dash',label:'Сьогодні',/);
    const heliRoute = html.match(/if\(section==='heli'\)\s*return\s*<BoSHome([^;]+);/);
    const dashRoute = html.match(/if\(section==='dash'\)\s*return\s*<BoSHome([^;]+);/);
    assert(heliRoute && dashRoute, 'Both primary overview routes must render BoSHome.');
    assert.match(heliRoute[1], /readOnlyOverview/);
    assert.doesNotMatch(dashRoute[1], /readOnlyOverview/);
  });

  await test('read-only helicopter renders metrics without actions, recovery, or submit dialog', async () => {
    const helicopter = overviewHarness(true);
    await helicopter.flush();
    assert.match(text(helicopter.tree()), /Вертоліт/);
    assert.equal(componentNodes(helicopter, helicopter.context.NextAction).length, 0);
    assert.equal(componentNodes(helicopter, helicopter.context.B03PendingLauncher).length, 0);
    assert.equal(componentNodes(helicopter, helicopter.context.BoSActionDialog).length, 0);
    assert.equal(componentNodes(helicopter, helicopter.context.WorkpointsPanel).length, 0);
    helicopter.destroy();
  });

  await test('daily workspace remains the operational counterpart', async () => {
    const daily = overviewHarness(false);
    await daily.flush();
    assert.match(text(daily.tree()), /Сьогодні у BoS/);
    assert(componentNodes(daily, daily.context.NextAction).length > 0,
      'Daily view must retain its next-action component.');
    assert(componentNodes(daily, daily.context.B03PendingLauncher).length > 0,
      'Daily view must retain controlled recovery entry.');
    daily.destroy();
  });

  await test('existing snapshot and permission guards remain in the actual BoSHome source', async () => {
    const home = functionSlice('function BoSHome(', 'function BoSProductGuide(');
    assert.match(home, /homeReadScope\(\)/);
    assert.match(home, /homeSnapshotShape\(/);
    assert.match(home, /X-BoS-Access/);
    assert.match(home, /X-BoS-Identity/);
    assert.match(home, /bosCanAction\(type\)/);
    assert.match(home, /if\(readOnlyOverview\|\|!canUse\(\)\)return;/);
  });

  console.log(JSON.stringify({
    schema: 'bos.v18.start-overview-ui-focused.v1',
    result: 'PASS',
    checks: results,
    scope: 'actual JSX via Babel with controlled hooks; no DOM, browser, server, TCP, database, or product writes',
  }, null, 2));
}

run().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
