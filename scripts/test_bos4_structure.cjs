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

// Supplier lines use the actual filtered purchase and two visible, mapped points.
const mapStart = source.indexOf('function networkProject(');
const mapEnd = source.indexOf('function NetworkDocuments(', mapStart);
const mapContext = {
  React: context.React, Button: context.Button,
  window: {BOS_NETWORK_MAP: {paths: [], translate: [480, 285], scale: 200, sourceUrl: '#', source: 'Тест', license: 'MIT'}},
  useState: () => [null, () => {}], useEffect: () => {},
};
vm.createContext(mapContext);
vm.runInContext(babel.transform(source.slice(mapStart, mapEnd), {presets: ['react']}).code, mapContext);
const supplier = {id: 1, name: 'Постачальник', kind: 'supplier', map_lat: 50, map_lng: 20};
const destination = {id: 2, name: 'Склад', kind: 'warehouse', map_lat: 50, map_lng: 30};
const order = {id: 41, code: 'PO-41', location_id: 2, origin_location_id: 1, destination_id: 2};
const lines = (points, purchases) => mapContext.networkSupplierLines(points, purchases);
assert.equal(lines([supplier, destination], [order]).length, 1);
assert.equal(lines([destination], [order]).length, 0, 'hidden supplier point');
assert.equal(lines([supplier], [order]).length, 0, 'hidden destination point');
assert.equal(lines([supplier, {...destination, map_lat: 95}], [order]).length, 0, 'invalid coordinate');
assert.equal(lines([supplier, {...destination, map_lng: 20}], [order]).length, 0, 'coincident coordinates');
assert.equal(lines([supplier, destination], [{...order, origin_location_id: null}]).length, 0, 'no invented origin');
const mapRowsStart = source.indexOf('function moduleMapRows(');
const mapRowsEnd = source.indexOf('function modulePointSelection(', mapRowsStart);
const moduleMapRows = vm.runInNewContext(source.slice(mapRowsStart, mapRowsEnd) + '\nmoduleMapRows');
const networkForMap = {locations: [supplier, destination], rows: {points: [supplier, destination]}};
assert.deepEqual(Array.from(moduleMapRows(networkForMap, {id:'purchases'}, [order]).points, p=>p.id), [1, 2]);
assert.deepEqual(Array.from(moduleMapRows({...networkForMap, rows:{points:[destination]}}, {id:'purchases'}, [order]).points, p=>p.id), [2], 'branch filter hides supplier');
assert.deepEqual(Array.from(moduleMapRows(networkForMap, {id:'purchases'}, []).points), [], 'search excludes purchase');
const walk = node => !node || typeof node !== 'object' ? [] : [node, ...(node.props?.children||[]).flatMap(child=>Array.isArray(child)?child.flatMap(walk):walk(child))];
const opened = [];
const transfer = {id: 9, code: 'TR-9', status: 'in_transit', source_location_id: 1, destination_id: 2};
const rendered = mapContext.NetworkMap({points:[supplier,destination],locations:[supplier,destination],transfers:[transfer],purchases:[order],selected:'',onPoint(){},onPurchase:row=>opened.push(row.id)});
const paths = walk(rendered).filter(node=>node.type==='path');
const supplyPath = paths.find(node=>node.props.role==='button');
assert.ok(supplyPath, 'supplier connection is a keyboard target');
assert.equal(supplyPath.props.tabIndex, 0);
assert.match(supplyPath.props['aria-label'], /PO-41/);
let focused = false;
supplyPath.props.onClick({currentTarget:{focus(){focused=true}}});
let prevented = false;
supplyPath.props.onKeyDown({key:'Enter',preventDefault(){prevented=true}});
assert.deepEqual(opened, [41, 41]);
assert.equal(focused, true, 'pointer invocation leaves a focus return target');
assert.equal(prevented, true);
assert.ok(paths.some(node=>node.props.key===9), 'in-transit route remains');
console.log('M6 supplier line: endpoint, coordinates, filters, transfer and keyboard/click PASS');

// U5: «Структура» has one refresh button: it reloads the record data, and the map reloads with it (data is an effect dependency).
assert.doesNotMatch(source, /Оновити мережу/);
assert.match(source, /<div className="erp-workspace">\{view!=='network'&&<div className="erp-row">/);
assert.match(source, /content=<ERPNetwork data=\{data\} onRefresh=\{refresh\}/);
assert.match(source, /<Button onClick=\{\(\)=>onRefresh\?onRefresh\(\):setVersion\(v=>v\+1\)\}>Оновити<\/Button>/);
console.log('U5 one refresh on the structure screen: PASS');
