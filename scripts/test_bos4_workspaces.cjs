const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/boss_app_source.html'), 'utf8');
function part(start, end) {
  const from = source.indexOf(start), to = source.indexOf(end, from);
  assert(from >= 0 && to > from, `missing source block: ${start}`);
  return source.slice(from, to);
}
const code = [
  part('function bosCanView(', 'function useLocalState('),
  part('const NAV=[', '// Existing preference IDs remain compatible;'),
].join('\n');
for (const role of ['ceo', 'manager', 'observer']) {
  const context = {
    bosRole: () => role,
    bosCan: key => key === 'finance' ? role === 'ceo' : key === 'view_documents',
  };
  vm.createContext(context);
  vm.runInContext(code, context);
  const nav = vm.runInContext('bosNavigation()', context);
  assert.deepEqual(Array.from(nav, n => n.id), ['monitor', 'structure', 'erp', 'finance', 'hr', 'documents', 'connectors', 'settings']);
  assert.deepEqual(Array.from(nav.find(n => n.id === 'erp').subs, n => n.label), ['Продажі', 'Постачання', 'Склад', 'Виробництво', 'Якість', 'Номенклатура']);
  const finance = Array.from(nav.find(n => n.id === 'finance').subs, n => n.id);
  assert.deepEqual(finance, role === 'observer' ? ['contractors', 'contracts'] : role === 'manager' ? ['invoices', 'contractors', 'contracts'] : ['invoices', 'contractors', 'contracts', 'salaries']);
  const route = (section, sub) => JSON.parse(JSON.stringify(vm.runInContext(`bosRoute({section:${JSON.stringify(section)},sub:${JSON.stringify(sub)}})`, context)));
  assert.deepEqual(route('erp', 'network'), {section: 'structure', sub: null});
  assert.deepEqual(route('erp', 'deals'), {section: 'erp', sub: 'sales', extra: 'deals'});
  assert.deepEqual(route('finance', 'procurement'), {section: 'erp', sub: 'purchase', extra: 'procurement'});
  assert.deepEqual(route('finance', 'costs'), {section: 'finance', sub: 'invoices', extra: null});
  assert.deepEqual(route('finance', 'bank'), {section: 'finance', sub: 'invoices', extra: 'bank'});
}
const workspace = part('function ERPWorkspace(', 'const BOS_METRICS=');
const settings = part('function Settings(', '// InfoPage');
const finance = part('function FinanceWorkspace(', 'function App()');
assert.match(settings, /bosRole\(\)==='ceo'&&<ERPWorkspace view="import" onNavigate=\{onNavigate\}/);
assert.match(workspace, /view==='import'&&bosRole\(\)==='ceo'&&<Button onClick=\{\(\)=>setInitialImport\(true\)\}>Початковий імпорт<\/Button>/);
assert.doesNotMatch(workspace, /Єдині замовлення, матеріали та відповідальні|Контекст для AI|Собівартість і маржа відвантажень/);
assert.match(workspace, /if\(view==='costs'&&bosCan\('finance'\)\)content=<>\<Card\><h3>Рахунки й оплати<\/h3>/);
assert.match(finance, /<ERPWorkspace view="costs"/);
const erpNumCode = source.match(/^const erpNum=.*;$/m)?.[0];
assert.ok(erpNumCode);
assert.deepEqual(Array.from(vm.runInNewContext(`${erpNumCode};[erpNum('0.000'),erpNum('120.000'),erpNum('0.125')]`)), ['0', '120', '0,125']);
// Money and quantities are formatted from the exact decimal string: no float rounding, hryvnia as «грн».
const amountCode = source.slice(source.indexOf('function erpAmount('), source.indexOf('const erpDateTime='));
assert.ok(amountCode.includes('const erpMoney='));
assert.deepEqual(Array.from(vm.runInNewContext(`${amountCode};[erpAmount('10900.00'),erpAmount('9007199254740993.125'),erpAmount('0.000'),erpMoney('777700.00','UAH'),erpMoney('-1234.5','UAH'),erpMoney('5.10','EUR'),erpMoney(null,'UAH')]`)),
  ['10\u00a0900', '9\u00a0007\u00a0199\u00a0254\u00a0740\u00a0993,125', '0', '777\u00a0700\u00a0грн', '-1\u00a0234,50\u00a0грн', '5,10\u00a0EUR', 'Недоступно']);
// U7: no raw «{amount} {currency}» left in purchase facts; document kinds in Ukrainian; zero-only columns hidden.
assert.doesNotMatch(source, /\{s\.[a-z_]+\} \{s\.currency\}/);
assert.doesNotMatch(source, /додаткові витрати \{r\.extras\}/);
assert.doesNotMatch(source, /\["Вартість",r=>erpNum\(/);
assert.match(source, /r\.missing_documents\.map\(k=>ERP_DOC_KINDS\[k\]\|\|k\)/);
assert.equal(vm.runInNewContext(`${source.match(/^const ERP_DOC_KINDS=.*;$/m)[0]};ERP_DOC_KINDS.passport`), 'паспорт виробу');
for (const rows of ['data.lines', 'data.purchases']) {
  assert.ok(source.includes(`...(erpAllZero(${rows},'cancelled_quantity')?[]:[`), rows);
  assert.ok(source.includes(`...(erpAllZero(${rows},'returned_quantity')?[]:[`), rows);
}
// U7: purchase value is computed from exact decimal strings and rounded half-to-even like erp.balances.money
// (vectors cross-checked against the server function), never through binary floats.
const lineTotalCode = source.slice(source.indexOf('function erpLineTotal('), source.indexOf('const erpMoney='));
assert.deepEqual(Array.from(vm.runInNewContext(`${lineTotalCode};[
  erpLineTotal('1.015','1.00','0.00'), erpLineTotal('1.025','1.00','0'), erpLineTotal('1.005','1','0'),
  erpLineTotal('300.000','520.00','0.00'), erpLineTotal('0.333','0.15','0.01'),
  erpLineTotal('9007199254740993.125','1.00','0'), erpLineTotal('-1.015','1','0'), erpLineTotal('x','1')]`)),
  ['1.02', '1.02', '1.00', '156000.00', '0.06', '9007199254740993.12', '-1.02', null]);
assert.match(source, /\["Вартість",r=>erpMoney\(erpLineTotal\(r\.quantity,r\.price,r\.extras\),r\.currency\)\]/);
assert.doesNotMatch(source, /toFixed\(2\),r\.currency/);
// U8: file pickers speak Ukrainian; the browser's «Choose File / No file chosen» is never shown.
assert.match(source, /if \(props\.type === 'file'\) return <BosFile \{\.\.\.props\}\/>;/);
assert.match(source, /<span className="bos-file-button" aria-hidden="true">Обрати файл<\/span>/);
assert.match(source, /\.bos-file-name:empty::before\{content:"Файл не обрано"/);
// Only the hidden assistant upload (opened by its own button) keeps a bare native file input.
assert.equal((source.match(/<input [^>]*type="file"/g) || []).length, 1);
// U9: on a phone the monitoring tables become «label: value» cards. Rendered from the compiled app:
// headers stay real (scope + roles, only visually hidden), every cell names its column, and the phone
// rules are scoped to .mon-table so other .erp-table screens (Connections) are untouched.
{
  const app = fs.readFileSync(path.join(__dirname, '../assets/app.js'), 'utf8');
  const monTable = app.slice(app.indexOf('function MonTable('), app.indexOf('function Monitoring('));
  assert.ok(monTable, 'compiled MonTable');
  const React = {createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)})};
  const all = n => n&&typeof n==='object'?[n,...(n.children||[]).flatMap(all)]:[];
  const tree = vm.runInNewContext(`${monTable};MonTable({table:{title:'Замовлення в роботі',total:1,columns:['Замовлення','Строк'],rows:[{ref:{kind:'order',id:1},late:true,cells:['ZM-1','2026-10-03']}]},onRow:()=>{}})`, {React, monValue:v=>v});
  const nodes = all(tree);
  assert.ok(nodes.some(n=>n.type==='div'&&n.props.className==='erp-table mon-table'));
  const ths = nodes.filter(n=>n.type==='th');
  assert.deepEqual(ths.map(n=>[n.props.scope,n.props.role,n.children[0]]), [['col','columnheader','Замовлення'],['col','columnheader','Строк']]);
  const tds = nodes.filter(n=>n.type==='td');
  assert.deepEqual(tds.map(n=>[n.props.role,n.props['data-label']]), [['cell','Замовлення'],['cell','Строк']]);
  assert.ok(nodes.filter(n=>n.type==='tr').every(n=>n.props.role==='row'));
  const phone = source.match(/@media\(max-width:600px\)\{\.mon-table\{overflow:visible\}[^\n]*/)?.[0];
  assert.ok(phone, 'phone rules exist');
  assert.doesNotMatch(phone, /\.mon-card \.erp-table|\.erp-table (thead|td|tr)/, 'phone rules never target other .erp-table screens');
  assert.doesNotMatch(phone, /thead\{display:none\}/, 'headers are only visually hidden');
  assert.match(phone, /\.mon-table thead\{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect\(0 0 0 0\)/);
  const connections = app.match(/function Connections\(\)\s*\{[\s\S]*?\n\}\s*(?=\/\/ BoS 4 first screen)/)?.[0];
  assert.ok(connections && !connections.includes('mon-table'), 'Connections tables keep the ordinary layout');
}
console.log('M7 navigation, legacy routes and role visibility: PASS');
