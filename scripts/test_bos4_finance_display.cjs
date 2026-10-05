const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const compiled = fs.readFileSync(path.join(root, 'assets/app.js'), 'utf8');
const source = fs.readFileSync(path.join(root, 'frontend/boss_app_source.html'), 'utf8');
function part(start, end) {
  const a = compiled.indexOf(start), b = compiled.indexOf(end, a);
  assert(a >= 0 && b > a, start);
  return compiled.slice(a, b);
}
let data, slot, search = '', refreshes = 0;
const context = {
  React: {Fragment: 'fragment', createElement: (type, props, ...children) => ({type, props: {...props, children}})},
  useState: initial => [slot++ === 0 ? data : slot === 6 ? search : initial, () => {}],
  useRef: () => ({current: 0}), useEffect() {},
  bosCanView: () => true, bosCan: () => true, bosCanAction: () => false, bosRole: () => 'ceo',
  Card: 'Card', ERPTable: 'ERPTable', Input: 'Input', Button: 'Button',
  B03Ledger: 'B03Ledger', B03PendingLauncher: 'B03PendingLauncher',
  ERP_LABELS: {}, flowPositive: value => Number(value) > 0,
  erpFetch: async () => {refreshes++; return data;},
};
vm.createContext(context);
vm.runInContext(
  part('const erpDate =', 'async function erpFetch(') + '\n' +
  part('function b03FindRecord(', 'function b03OpenPurchase(') + '\n' +
  part('function erpRecordName(', 'function ERPWorkspace(') + '\n' +
  part('function ERPWorkspace(', 'const BOS_METRICS =') + '\n' +
  part('function BoSReadOnlyRecords(', 'function WorkspaceTabs('), context);
const allZero = vm.runInContext('erpAllZero', context);
assert.equal(allZero([], 'credit'), false);
for (const value of [0, -0, '0', '0.00', '-0.000', '+0', '.000', ' 0.00 ']) assert(allZero([{credit: value}], 'credit'));
for (const value of [null, undefined, '', ' ', 'bad', false, [], {}, NaN, Infinity, '0x0', '1e-999', '0.0000000001', '-0.01', 1]) {
  assert.equal(allZero([{credit: 0}, {credit: value}], 'credit'), false, String(value));
}
function nodes(tree) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return [tree, ...nodes(tree.props?.children)];
}
function render(invoices, query = '') {
  data = {invoices, events: [], items: [], orders: [], locations: [], employees: [], jobs: [], lots: []};
  slot = 0; search = query;
  const before = JSON.stringify(data);
  const tree = vm.runInContext('ERPWorkspace({view:"costs"})', context);
  assert.equal(JSON.stringify(data), before, 'display must not change source data');
  const table = nodes(tree).find(n => n.type === 'ERPTable');
  return {tree, table, labels: Array.from(table.props.columns, c => c[0])};
}
const invoice = (credit, customer, code = 'INV-1') => ({code, amount: '777700.00', paid: '0', open: '777700', currency: 'UAH', effective_credit: credit, customer_credit: customer});
let result = render([invoice('0.00', 0)]);
assert(!result.labels.includes('Чинний кредит') && !result.labels.includes('Кредит клієнта'));
result = render([invoice(0, 3)]);
assert(!result.labels.includes('Чинний кредит') && result.labels.includes('Кредит клієнта'));
result = render([invoice(-1, 0)]);
assert(result.labels.includes('Чинний кредит') && !result.labels.includes('Кредит клієнта'));
for (const value of [null, undefined, 'invalid', '']) {
  result = render([invoice(value, value)]);
  assert(result.labels.includes('Чинний кредит') && result.labels.includes('Кредит клієнта'));
}
result = render([invoice(0, 0, 'ZERO'), invoice(2, 4, 'NONZERO')], 'ZERO');
assert.equal(result.table.props.rows.length, 2); // Both codes contain ZERO.
result = render([invoice(0, 0, 'MATCH'), invoice(2, 4, 'HIDDEN')], 'MATCH');
assert.equal(result.table.props.rows.length, 1);
assert(result.labels.includes('Чинний кредит') && result.labels.includes('Кредит клієнта'), 'search must not hide credits in other source rows');
const toolbar = nodes(result.tree).find(n => n.props.className === 'erp-search-row');
assert(toolbar);
assert.deepEqual(nodes(toolbar).filter(n => ['Input', 'Button'].includes(n.type)).map(n => n.type), ['Input', 'Button']);
assert.equal(nodes(toolbar).find(n => n.type === 'Input').props['aria-label'], 'Пошук ERP');
assert.equal(typeof nodes(toolbar).find(n => n.type === 'Button').props.onClick, 'function');
// Native flex contract keeps search and refresh on one row and lets search shrink.
assert.match(source, /\.erp-search-row\{[^}]*display:flex[^}]*min-width:0[^}]*width:100%/);
assert.match(source, /\.erp-search-row>input,\.erp-search-row>label\{flex:1;min-width:0;width:100%\}/);
assert.match(source, /\.erp-search-row>button\{flex:none;white-space:nowrap\}/);
assert.match(source, /@media\(max-width:480px\)\{\.erp-search-row/);
assert.doesNotMatch(source.match(/\.erp-search-row\{[^}]*\}/)[0], /flex-wrap/);
slot = 0; data = ''; search = '';
const readonly = vm.runInContext('BoSReadOnlyRecords({title:"Журнал",rows:[],columns:[],onRefresh:()=>{}})', context);
const readonlyToolbar = nodes(readonly).find(n => n.props.className === 'erp-search-row');
assert.deepEqual(nodes(readonlyToolbar).filter(n => ['Input', 'Button'].includes(n.type)).map(n => n.type), ['Input', 'Button']);
for (const label of ['Пошук журналу', 'Пошук контрагентів', 'Пошук договорів', 'Пошук зарплат']) {
  assert(source.includes('className="erp-search-row"><Input aria-label="' + label + '"'), label);
}
console.log('U3 compiled finance display: credit visibility, unknowns, search, unchanged data and adaptive toolbar PASS');
