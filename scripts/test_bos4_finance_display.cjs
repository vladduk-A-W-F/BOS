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
let data, slot, search = '', refreshes = 0, role = 'ceo';
const context = {
  React: {Fragment: 'fragment', createElement: (type, props, ...children) => ({type, props: {...props, children}})},
  useState: initial => [slot++ === 0 ? data : slot === 6 ? search : initial, () => {}],
  useRef: () => ({current: 0}), useEffect() {},
  bosCanView: () => true, bosCan: permission => permission !== 'finance' || role !== 'observer', bosCanAction: () => false, bosRole: () => role,
  Card: 'Card', ERPTable: 'ERPTable', Input: 'Input', Button: 'Button',
  B03Ledger: 'B03Ledger', B03PendingLauncher: 'B03PendingLauncher', B03Settlement: 'B03Settlement', B03Facts: 'B03Facts',
  BoSLink: 'BoSLink', DocViewer: 'DocViewer', NextAction: 'NextAction', OrderTrace: 'OrderTrace',
  OrderSupplyOptions: 'OrderSupplyOptions', OrderSettlement: 'OrderSettlement', T: {primary: '#000'},
  ERP_LABELS: {}, B03_KINDS: {}, c03Scope: () => 'test', flowPositive: value => Number(value) > 0,
  erpFetch: async () => {refreshes++; return data;},
};
vm.createContext(context);
vm.runInContext(
  part('const erpDate =', 'async function erpFetch(') + '\n' +
  part('function b03FindRecord(', 'function b03OpenPurchase(') + '\n' +
  part('function erpRecordName(', 'function ERPWorkspace(') + '\n' +
  part('function ERPWorkspace(', 'const BOS_METRICS =') + '\n' +
  part('const BOS_METRICS =', 'function BoSReadOnlyRecords(') + '\n' +
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
// Sales unit prices use the same exact monetary display as purchase and invoice facts.
search = '';
for (const [price, currency, expected] of [
  ['1234.50', 'UAH', '1\u00a0234,50\u00a0грн'],
  ['9007199254740993.12', 'UAH', '9\u00a0007\u00a0199\u00a0254\u00a0740\u00a0993,12\u00a0грн'],
  ['5.10', 'EUR', '5,10\u00a0EUR'], ['0.00', 'UAH', '0\u00a0грн'],
  [null, 'UAH', 'Недоступно'],
]) {
  data = {events: [], items: [], partners: [], locations: [], employees: [], jobs: [], lots: [],
    orders: [{id: 20, code: 'ORDER', currency}],
    lines: [{id: 21, order_id: 20, quantity: '1', shipped: '0', price}]};
  const before = JSON.stringify(data);
  slot = 0; role = 'ceo';
  const table = nodes(vm.runInContext('ERPWorkspace({view:"sales"})', context)).find(n => n.type === 'ERPTable');
  assert.equal(table.props.columns.find(c => c[0] === 'Ціна')[1](table.props.rows[0]), expected);
  slot = 0; role = 'observer';
  const hidden = nodes(vm.runInContext('ERPWorkspace({view:"sales"})', context)).find(n => n.type === 'ERPTable');
  assert(!hidden.props.columns.some(c => c[0] === 'Ціна'), 'observer must still have no price column');
  assert.equal(JSON.stringify(data), before, 'display must preserve order currency and line values');
}
assert.equal(refreshes, 0, 'rendering facts must not request or mutate data');
function textOf(tree) {
  if (tree == null || typeof tree === 'boolean') return '';
  if (Array.isArray(tree)) return tree.map(textOf).join('');
  return typeof tree === 'object' ? textOf(tree.props?.children) : String(tree);
}
function table(tree, label) {
  const found = nodes(tree).filter(n => n.type === 'ERPTable')
    .find(n => n.props.columns.some(([name]) => name === label));
  assert(found, `missing ${label} table`);
  return found;
}
function column(found, name, row = found.props.rows[0]) {
  const renderer = found.props.columns.find(([label]) => label === name)?.[1];
  assert(renderer, `missing ${name} column`);
  return typeof renderer === 'function' ? renderer(row) : row[renderer];
}
const huge = '9007199254740993.12';
const hugeUAH = '9\u00a0007\u00a0199\u00a0254\u00a0740\u00a0993,12\u00a0грн';
const eur = '1\u00a0234,50\u00a0EUR';
const item = {id: 1, code: 'ITEM', name: 'Виріб', unit: 'шт.', method: 'make', revision: 'A',
  material: '', external_codes: {}, required_documents: [], minimum: '1', bom: [], routing: [],
  planned_cost: huge, currency: 'UAH'};
const job = {id: 2, code: 'JOB', item_id: 1, location_id: 3, owner_id: 4, quantity: '2', produced: '0',
  revision: 'A', status: 'planned', needs_review: false, routing: [], bom: [],
  planned_cost: '1234.50', actual_cost: huge, currency: 'EUR'};
const order = {id: 5, code: 'ORDER', customer_id: 6, owner_id: 4, status: 'confirmed', currency: 'UAH'};
const bill = {...invoice('0', '0'), invoice_id: 7, order_id: 5, paid: huge, open: null,
  lines: [{line_id: 8, quantity: '2', price: huge}], retained: '0', collectible: '0'};
const cost = {order_id: 5, code: 'ORDER', currency: 'UAH', order_value: huge,
  shipped_value: '1234.50', shipped_cost: null, gross_margin: huge};
const facts = {items: [item], jobs: [job], orders: [order], invoices: [bill], costs: [cost],
  lines: [{id: 8, order_id: 5, item_id: 1, quantity: '2', shipped: '1', price: huge}],
  locations: [{id: 3, name: 'Склад'}], employees: [{id: 4, full_name: 'Власник'}],
  partners: [{id: 6, name: 'Клієнт'}], events: [], lots: [], purchases: [], reservations: [],
  operator_entries: [], invoice_adjustments: [], source_movements: [], replenishment: [],
  home: {financial: [{currency: 'UAH', order_value: huge}]}};
function show(view, currentRole = 'ceo') {
  data = facts; slot = 0; role = currentRole;
  const before = JSON.stringify(data);
  const tree = vm.runInContext(`ERPWorkspace({view:${JSON.stringify(view)}})`, context);
  assert.equal(JSON.stringify(data), before, 'workspace must preserve monetary source data');
  return tree;
}
function inspect(selection, currentRole = 'ceo') {
  role = currentRole; slot = 0;
  const before = JSON.stringify(facts);
  const tree = context.BoSInspector({selection, data: facts, onSelect() {}, onClose() {}});
  assert.equal(JSON.stringify(facts), before, 'inspector must preserve monetary source data');
  return tree;
}
assert(textOf(column(table(show('catalog'), 'Коди й вимоги'), 'Коди й вимоги', item)).includes(hugeUAH));
assert(textOf(show('production')).includes('1\u00a0234,50\u00a0EUR; факт: '+ '9\u00a0007\u00a0199\u00a0254\u00a0740\u00a0993,12\u00a0EUR'));
assert(!textOf(column(table(show('catalog', 'observer'), 'Коди й вимоги'), 'Коди й вимоги', item)).includes(hugeUAH), 'observer cannot see catalog cost');
assert(!textOf(show('production', 'observer')).includes('1\u00a0234,50\u00a0EUR'), 'observer cannot see job cost');
let billTable = table(show('costs'), 'До оплати');
assert.equal(column(billTable, 'Сплачено'), hugeUAH);
assert.equal(column(billTable, 'До оплати'), 'Недоступно');
assert(!nodes(show('costs', 'observer')).some(n => n.type === 'ERPTable' && n.props.columns.some(([name]) => name === 'Сплачено')));
let metric = inspect({kind: 'metric', key: 'order_value', currency: 'UAH'});
assert(textOf(metric).includes(hugeUAH));
let costTable = table(metric, 'Портфель');
assert.equal(column(costTable, 'Портфель'), hugeUAH);
assert.equal(column(costTable, 'Відвантажено'), '1\u00a0234,50\u00a0грн');
assert.equal(column(costTable, 'Собівартість'), 'Недоступно');
assert(textOf(inspect({kind: 'metric', key: 'order_value', currency: 'UAH'}, 'observer')).includes('Показник недоступний'));
let orderFacts = inspect({kind: 'orders', id: 5});
assert(textOf(orderFacts).includes(hugeUAH));
assert.equal(column(table(orderFacts, 'Ціна'), 'Ціна'), hugeUAH);
let invoiceFacts = inspect({kind: 'invoices', id: 7});
assert.equal(column(table(invoiceFacts, 'Ціна'), 'Ціна'), hugeUAH);
assert.equal(refreshes, 0, 'rendering facts must not request or mutate data');
console.log('U3 compiled finance display: exact workspace and inspector money, unavailable, role guards, unchanged data PASS');
