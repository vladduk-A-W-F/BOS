// M2b: the compiled bento tiles of «Моніторинг» — roles, targets, the tile-less fallback and a reload without blanking.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const app = fs.readFileSync(path.join(__dirname, '../assets/app.js'), 'utf8');
const block = app.slice(app.indexOf('const MON_KIND ='), app.indexOf('// BoS 4 «Підключення»'));
assert.ok(block.includes('function MonBento(') && block.includes('function Monitoring('), 'bento lives in the monitoring block');
const React = {Fragment: 'fragment', createElement: (type, props, ...children) => ({type, props: props || {}, children: children.flat(Infinity)})};
const nodes = n => n && typeof n === 'object' ? [n, ...(n.children || []).flatMap(nodes)] : [];
const text = n => nodes(n).flatMap(x => x.children || []).filter(c => typeof c === 'string' || typeof c === 'number').join('');
const tick = () => new Promise(setImmediate);

function context(extra = {}) {
  let hook = 0, effect;
  const state = [], refs = [];
  const ctx = {React, Button: () => {}, BoSInspector: () => {}, C01TaskLegacy: () => {}, bosHttpScope: () => 'user:1',
    document: {activeElement: null}, requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
    erpDate: x => x ? String(x).slice(0, 10).split('-').reverse().join('.') : '—', erpDateTime: x => x,
    erpMoney: (v, c) => v + ' ' + c,
    useState(initial) { const i = hook++; if (!(i in state)) state[i] = typeof initial === 'function' ? initial() : initial; return [state[i], v => state[i] = typeof v === 'function' ? v(state[i]) : v]; },
    useRef(initial) { const i = hook++; if (!(i in refs)) refs[i] = {current: initial}; return refs[i]; },
    useEffect(fn) { effect = fn; }, ...extra};
  vm.createContext(ctx);
  vm.runInContext(block, ctx);
  ctx.reset = () => { hook = 0; };
  ctx.effect = () => effect;
  ctx.state = state;
  return ctx;
}

const day = (date, values) => ({date, orders: 0, deliveries: 0, jobs: 0, invoices: 0, ...values});
const ceo = {
  orders: {open: 4, late: 1, units_shipped: 480, units_total: 1639, top: [
    {ref: {kind: 'order', id: 7}, customer: 'ТОВ «Склад-Мережа Схід»', code: 'ZM-0150', shipped: 270, total: 1275, due: '2026-11-27', late: false},
    {ref: {kind: 'order', id: 2}, customer: 'ТОВ «Офіс Сіті»', code: 'ZM-0144', shipped: 90, total: 100, due: '2026-10-03', late: true}]},
  production: {planned: 1, running: 29, done: 12, late: 0, steps_done: 58, steps_total: 145},
  supply: {open: 2, late: 1, next: {ref: {kind: 'purchase', id: 3}, item: 'Лист сталевий', supplier: 'Металопрокат Центр', due: '2026-10-08'}},
  money: [{currency: 'UAH', invoiced: '2669550.00', paid: '1048525.00', open: '1621025.00', overdue: '168000.00'}],
  tasks: {open: 5, late: 0},
  sources: {total: 2, fresh: 1, stale: 1, error: 0, file: 0, unknown: 0},
  ahead: [day('2026-10-05', {jobs: 3}), day('2026-10-06', {jobs: 26}), day('2026-10-08', {deliveries: 1}), day('2026-10-19', {invoices: 1})],
};
const observer = {...ceo, money: [], ahead: ceo.ahead.map(d => ({...d, invoices: null}))};

// Tiles, by role. Money and the invoice row of «Наступні 14 днів» exist only when the server sent them.
const ctx = context();
const routes = [], opened = [];
const render = bento => ctx.MonBento({bento, attention: [], asOf: '2026-10-05', onOpen: ref => opened.push(ref), onNavigate: (...r) => routes.push(r)});
const tiles = tree => nodes(tree).filter(n => n.type === ctx.MonTile);
const titles = tree => tiles(tree).map(t => t.props.title);
const full = render(ceo);
assert.deepEqual(titles(full), ['Виконання замовлень', 'Гроші', 'Виробництво', 'Постачання', 'Доручення', 'Джерела даних', 'Наступні 14 днів']);
assert.equal(full.props.className, 'mon-bento');
const lean = render(observer);
assert.deepEqual(titles(lean), ['Виконання замовлень', 'Виробництво', 'Постачання', 'Доручення', 'Джерела даних', 'Наступні 14 днів'], 'no money tile without money');
assert.equal(lean.props.className, 'mon-bento mon-bento-nomoney');
const rowsOf = tree => nodes(tree).filter(n => n.type === 'th' && n.props.scope === 'row').map(n => text(n));
assert.deepEqual(rowsOf(full), ['Замовлення', 'Поставки', 'Роботи', 'Рахунки']);
assert.deepEqual(rowsOf(lean), ['Замовлення', 'Поставки', 'Роботи'], 'no invoice row for a role without money');
assert.ok(!JSON.stringify(lean).includes('1621025'), 'no amount reaches a role without money');

// Nothing to show reads as words, not as «0%» or an empty ring.
const empty = render({...observer, orders: {open: 0, late: 0, units_shipped: 0, units_total: 0, top: []},
  production: {planned: 0, running: 0, done: 0, late: 0, steps_done: 0, steps_total: 0}, ahead: observer.ahead.map(d => ({...d, orders: 0, deliveries: 0, jobs: 0}))});
assert.match(text(tiles(empty)[0]), /Немає замовлень у роботі/);
assert.ok(!nodes(tiles(empty)[0]).some(n => n.type === ctx.MonMeter), 'no meter without orders');
assert.match(text(tiles(empty)[1]), /Робіт немає/);
assert.ok(!nodes(tiles(empty)[1]).some(n => n.type === ctx.MonRing));
assert.match(text(tiles(empty)[5]), /На ці дні строків немає/);

// Every tile opens its place; rows open their exact record.
for (const tile of tiles(full)) {
  const header = nodes(ctx.MonTile(tile.props)).find(n => n.type === 'button');
  if (header) header.props.onClick();
}
assert.deepEqual(routes, [['erp', 'sales'], ['finance', 'invoices'], ['erp', 'production'], ['erp', 'purchase'], ['hr', 'tasks'], ['connectors', null]]);
const orders = tiles(full)[0];
nodes(orders).filter(n => n.type === 'button').forEach(b => b.props.onClick());
nodes(tiles(full)[3]).filter(n => n.type === 'button').forEach(b => b.props.onClick());
assert.deepEqual(opened, [{kind: 'order', id: 7}, {kind: 'order', id: 2}, {kind: 'purchase', id: 3}]);
assert.ok(nodes(orders).some(n => n.props.className === 'mon-row-late'), 'a late order is marked in words and colour');
assert.match(text(orders), /прострочено/);

// Exact figures: the last value shown is the server's own; meters and the ring stay within 0–100 %.
const count = (value, render) => context().MonCount(render ? {value, render} : {value});   // a fresh component each time
assert.equal(count(1639), (1639).toLocaleString('uk-UA'));
assert.equal(count(1621025, (v, done) => done ? 'exact' : 'moving'), 'exact', 'without motion the exact value shows at once');
const moving = context({window: {matchMedia: () => ({matches: false})}});
assert.equal(moving.MonCount({value: 1639}), '0', 'with motion allowed the count starts from zero');
moving.effect()();                                                  // one animation frame is requested, nothing else
for (const [part, whole, expected] of [[480, 1639, 29], [5, 0, 0], [7, 5, 100], [-1, 5, 0], ['58', '145', 40]]) assert.equal(ctx.monPercent(part, whole), expected);
const meter = ctx.MonMeter({part: 90, whole: 100, late: true, label: 'x'});
assert.equal(meter.props.role, 'meter'); assert.equal(meter.props['aria-valuenow'], 90); assert.equal(meter.props.className, 'mon-meter mon-meter-late');
assert.equal(ctx.MonRing({part: 58, whole: 145, label: 'Операції'}).props['aria-label'], 'Операції: 40%');
assert.deepEqual([0, 1, 2, 3, 4, 9, 10, 19, 20, 99].map(ctx.monHeat), ['', 'mon-h1', 'mon-h2', 'mon-h2', 'mon-h3', 'mon-h3', 'mon-h4', 'mon-h4', 'mon-h5', 'mon-h5']);
const strip = tiles(full)[6];
assert.ok(nodes(strip).some(n => n.type === 'td' && /mon-today/.test(n.props.className || '')), 'today is marked');
assert.ok(nodes(strip).some(n => n.type === 'td' && n.props.className === 'mon-h5' && n.children.includes(26)));

// «Джерела даних»: each source by name, worst first, opening its own data further down the page.
const jumps = [];
const counts = list => list.reduce((c, s) => ({...c, [s.freshness]: (c[s.freshness] || 0) + 1}), {total: list.length});
const source = (id, name, freshness, extra = {}) => ({id, name, freshness, freshness_label: 'x', ...extra});
const withSources = list => ctx.MonBento({bento: {...ceo, sources: counts(list)}, attention: [], asOf: '2026-10-05',
  onOpen: () => {}, onNavigate: () => {}, sources: list, onSource: id => jumps.push(id)});
const sourcesTile = tree => tiles(tree).find(t => t.props.title === 'Джерела даних');
const sourceButtons = tile => nodes(tile).filter(n => n.type === 'button' && n.props.className === 'mon-source');
const two = [source(1, 'Замовлення з іншої системи', 'fresh', {total: 2, accepted: 1}), source(2, 'Оплати з банку', 'error')];
let tile = sourcesTile(withSources(two));
assert.deepEqual(sourceButtons(tile).map(b => b.props['data-state']), ['error', 'fresh'], 'a broken source comes first');
assert.match(text(sourceButtons(tile)[0]), /Оплати з банку.*помилка читання/);
assert.match(text(sourceButtons(tile)[1]), /Замовлення з іншої системи.*актуальне · прочитано 1 з 2/);
assert.ok(!nodes(tile).some(n => n.props.className === 'mon-states'), 'a short list needs no separate summary');
sourceButtons(tile).forEach(b => b.props.onClick());
assert.deepEqual(jumps, [2, 1]);
const five = [...two, source(3, 'Склад', 'stale'), source(4, 'Каса', 'file', {total: 3, accepted: 3}), source(5, 'Дзвінки', 'unknown')];
tile = sourcesTile(withSources(five));
assert.ok(nodes(tile).some(n => n.props.className === 'mon-states'), 'many sources keep the summary');
assert.deepEqual(sourceButtons(tile).map(b => b.props['data-state']), ['error', 'stale', 'unknown', 'file'], 'four, worst first');
const everything = nodes(tile).find(n => n.props.className === 'mon-more');
assert.match(text(everything), /Усі джерела \(5\)/);
everything.props.onClick();
assert.equal(jumps.at(-1), null, 'the whole list opens the sources section');
tile = sourcesTile(render(ceo));
assert.ok(nodes(tile).some(n => n.props.className === 'mon-states') && !sourceButtons(tile).length, 'an older server: summary only');
assert.equal(ctx.monSourceNote(source(6, 'Склад', 'stale')), 'застаріле', 'the observer gets the state in words, no row counts');
assert.equal(ctx.monSourceNote(source(7, 'Склад', 'fresh', {problem: 'Колонки не зіставлено з полями BoS'})), 'актуальне · потрібна відповідність колонок');

// Monitoring: tiles when the server sends them, the previous number row otherwise; a reload keeps facts on screen.
(async () => {
  const requests = [], listeners = {}, moved = [];
  const element = id => ({scrollIntoView: options => moved.push([id, options]), focus: options => moved.push([id, 'focus', options])});
  const mon = context({window: {addEventListener: (k, fn) => listeners[k] = fn, removeEventListener: k => delete listeners[k]},
    document: {activeElement: null, getElementById: id => ['mon-sources', 'mon-source-9'].includes(id) ? element(id) : null},
    erpFetch: p => new Promise((resolve, reject) => requests.push({p, resolve, reject}))});
  const draw = () => { mon.reset(); return mon.Monitoring({onNavigate: () => {}}); };
  draw(); mon.effect()();
  assert.equal(requests[0].p, 'monitoring/');
  const listed = [source(9, 'Замовлення з іншої системи', 'file', {dataset_label: 'Замовлення', total: 2, accepted: 1, rejected: 1})];
  requests[0].resolve({as_of: '2026-10-05', numbers: [{key: 'orders', value: 4, label: 'Замовлень у роботі'}], attention: [], tables: [], queries: [], bento: ceo, sources: listed});
  await tick();
  let tree = draw();
  assert.ok(nodes(tree).some(n => n.type === mon.MonBento), 'tiles replace the number row');
  const tilesNode = nodes(tree).find(n => n.type === mon.MonBento);
  assert.deepEqual(tilesNode.props.sources, listed, 'the tile lists the same sources as the section below');
  assert.ok(nodes(tree).some(n => n.props.id === 'mon-sources' && n.props.tabIndex === -1));
  assert.ok(nodes(tree).some(n => n.props.id === 'mon-source-9' && n.props.tabIndex === -1), 'each source card can take focus');
  tilesNode.props.onSource(9); tilesNode.props.onSource(null); tilesNode.props.onSource(404);
  assert.deepEqual(JSON.parse(JSON.stringify(moved)), [['mon-source-9', {block: 'start', behavior: 'auto'}], ['mon-source-9', 'focus', {preventScroll: true}],
    ['mon-sources', {block: 'start', behavior: 'auto'}], ['mon-sources', 'focus', {preventScroll: true}]],
    'scroll without motion when reduced motion is asked (or unknown), then keyboard focus; a missing card is ignored');
  assert.ok(!nodes(tree).some(n => n.props.className === 'mon-numbers'));
  listeners['bos:data-changed']();
  tree = draw();
  assert.equal(tree.props.className, 'mon mon-busy', 'reload dims, never blanks');
  assert.equal(tree.props['aria-busy'], 'true');
  assert.ok(nodes(tree).some(n => n.type === mon.MonBento), 'previous facts stay visible while reloading');
  requests[1].resolve({as_of: '2026-10-05', numbers: [{key: 'orders', value: 4, label: 'Замовлень у роботі'}], attention: [], tables: [], queries: []});
  await tick();
  tree = draw();
  assert.equal(tree.props.className, 'mon');
  assert.ok(nodes(tree).some(n => n.props.className === 'mon-numbers'), 'without bento the number row remains');
  assert.ok(!nodes(tree).some(n => n.type === mon.MonBento));
  const css = fs.readFileSync(path.join(__dirname, '../frontend/boss_app_source.html'), 'utf8');
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{\*,\*::before,\*::after\{animation:none!important;transition:none!important/, 'reduced motion switches the tile animation off');
  assert.match(css, /\.mon-tile\{[^}]*animation:mon-rise[^}]*backwards/, 'tiles rise in once, then hover can lift them');
  console.log('M2b bento tiles: roles, targets, exact figures, sources by name, fallback and reload without blanking: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
