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
console.log('M7 navigation, legacy routes and role visibility: PASS');
