const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/boss_app_source.html'), 'utf8');
const begin = source.indexOf('function structureCounts(');
const end = source.indexOf('function NetworkStructure(', begin);
assert(begin >= 0 && end > begin);
const count = vm.runInNewContext(source.slice(begin, end) + '\nstructureCounts');
const rows = {
  lots: [{location_id: 1}, {location_id: 1}, {location_id: 2}],
  orders: [{location_id: 1, open_line_count: 2}, {location_id: 1, open_line_count: 0}, {location_id: 2, open_line_count: 1}],
  jobs: [{location_id: 1, status: 'running'}, {location_id: 1, status: 'done'}, {location_id: 2, status: 'planned'}],
};
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, [1]))), {lots: 2, orders: 1, jobs: 1});
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, [1, 2]))), {lots: 3, orders: 2, jobs: 2});
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, []))), {lots: 0, orders: 0, jobs: 0});
const component = source.slice(end, source.indexOf('function ERPNetwork(', end));
assert(!/inventory_value|receivable|retained/.test(component), 'structure cells must not infer money or debt');

const babel = require(path.join(__dirname, '../assets/babel.js'));
const jsx = babel.transform(source.slice(begin, source.indexOf('function ERPNetwork(', begin)), {presets: ['react']}).code;
const state = [], effects = []; let slot = 0, effectSlot = 0, changed = false;
const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => value === b[i]);
const context = {
  React: {Fragment: 'fragment', createElement: (type, props, ...children) => ({type, props: {...props, children}})},
  useState(initial) {
    const index = slot++;
    if (!(index in state)) state[index] = initial;
    return [state[index], update => {
      const next = typeof update === 'function' ? update(state[index]) : update;
      if (next !== state[index]) {state[index] = next; changed = true;}
    }];
  },
  useEffect(run, deps) {
    const index = effectSlot++;
    if (!same(effects[index]?.deps, deps)) effects[index] = {deps, run, pending: true};
  },
  Card() {}, NetworkMap() {}, ERPTable() {}, Button() {}, BoSLink() {}, ERP_LABELS: {},
};
vm.createContext(context);
vm.runInContext(jsx, context);
const NetworkStructure = vm.runInContext('NetworkStructure', context);
const network = {
  branches: [{id: 1, name: 'Філія', short_name: 'Місто'}],
  locations: [{id: 11, branch_id: 1}, {id: 12, branch_id: 1}],
  rows: {...rows, points: [{id: 11, branch_id: 1, name: 'Склад А'}, {id: 12, branch_id: 1, name: 'Склад Б'}]},
};
function render(branch, point) {
  let tree;
  for (let pass = 0; pass < 4; pass++) {
    changed = false; slot = 0; effectSlot = 0;
    tree = NetworkStructure({network, branch, point, onPoint() {}, onRelatedPoint() {}, onSelect() {}});
    for (const effect of effects) if (effect?.pending) {effect.pending = false; effect.run();}
    if (!changed) return tree;
  }
  throw Error('structure did not settle');
}
function detail(tree, key) {
  if (!tree || typeof tree !== 'object') return null;
  if (tree.type === 'details' && String(tree.props.key) === String(key)) return tree;
  for (const child of tree.props?.children || []) {
    const found = Array.isArray(child) ? child.map(item => detail(item, key)).find(Boolean) : detail(child, key);
    if (found) return found;
  }
  return null;
}
assert.equal(detail(render('', ''), 1).props.open, false);
assert.equal(detail(render('1', ''), 1).props.open, true);
detail(render('1', ''), 1).props.onToggle({currentTarget: {open: false}});
assert.equal(detail(render('1', ''), 1).props.open, false, 'manual branch collapse persists');
let tree = render('1', '11');
assert.equal(detail(tree, 1).props.open, true);
assert.equal(detail(tree, 11).props.open, true);
detail(tree, 11).props.onToggle({currentTarget: {open: false}});
assert.equal(detail(render('1', '11'), 11).props.open, false, 'manual point collapse persists');
tree = render('1', '12');
assert.equal(detail(tree, 1).props.open, true);
assert.equal(detail(tree, 12).props.open, true, 'newly selected point opens');
const NetworkWarnings = vm.runInContext('NetworkWarnings', context);
const warnings = [
  'Фільтр філії застосовано до фізичних точок.',
  'Точки без координат лишаються в таблиці.',
  'Лінії позначають зв’язки, а не дороги.',
  'Митне оформлення не виконується.',
];
const warningTree = NetworkWarnings({warnings});
const paragraphs = warningTree.props.children.filter(child => Array.isArray(child)).flat().filter(child => child.type === 'p');
assert.equal(warningTree.type, 'details');
assert.deepEqual(paragraphs.map(p => p.props.children[0]), warnings, 'every server warning stays available');
console.log('M6 scoped counts, controlled disclosure and all server warnings: PASS');
