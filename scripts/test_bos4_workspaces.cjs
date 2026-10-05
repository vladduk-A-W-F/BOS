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
  const connections = app.match(/function Connections\([^)]*\)\s*\{[\s\S]*?\n\}\s*(?=\/\/ BoS 4 first screen)/)?.[0];
  assert.ok(connections && !connections.includes('mon-table'), 'Connections tables keep the ordinary layout');
}
console.log('M7 navigation, legacy routes and role visibility: PASS');

// M3: execute the compiled read-only source block and the connector handoff, including delayed replies.
(async()=>{
  const app=fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8');
  const block=app.slice(app.indexOf('const MON_KIND ='),app.indexOf('// BoS 4 «Підключення»'));
  assert.ok(block.includes('function Monitoring('));
  const React={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)})};
  const nodes=n=>n&&typeof n==='object'?[n,...(n.children||[]).flatMap(nodes)]:[];
  const tick=()=>new Promise(setImmediate);
  function harness(){
    let scope='user:1',hook=0,effect,cleanup;const state=[],refs=[],requests=[],routes=[];
    const context={React,Button:()=>{},BoSInspector:()=>{},bosHttpScope:()=>scope,erpDate:x=>x.split('T')[0].split('-').reverse().join('.'),erpDateTime:x=>x,
      erpMoney:(v,c)=>v+' '+c,
      useState(initial){const i=hook++;if(!(i in state))state[i]=initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
      useRef(initial){const i=hook++;if(!(i in refs))refs[i]={current:initial};return refs[i];},useEffect(fn){effect=fn;},
      window:{addEventListener(){},removeEventListener(){}},
      erpFetch:path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}))};
    vm.createContext(context);vm.runInContext(block,context);
    return {context,state,requests,routes,render(){hook=0;return context.Monitoring({onNavigate:(...route)=>routes.push(route)});},mount(){this.render();cleanup=effect();},unmount(){cleanup();},setScope:v=>scope=v};
  }
  const base={numbers:[{key:'orders',value:1,label:'ERP'}],tables:[],attention:[],queries:[]};
  const sourceTable={key:'source-7',title:'Synthetic orders',columns:['Клієнт','Сума','Валюта'],rows:[{ref:{kind:'connector',id:7},late:false,cells:['Synthetic','12.50','USD']}],total:1};
  const source={id:7,name:'Synthetic orders',dataset_label:'Замовлення',freshness:'stale',freshness_label:'Дані застаріли, оновіть джерело',last_sync_at:null,mapped:true,total:3,accepted:1,rejected:2,table:sourceTable};
  const ui=harness();ui.mount();assert.equal(ui.requests[0].path,'monitoring/');
  ui.requests[0].resolve({...base,sources:[source],source_attention:[{level:'warning',ref:{kind:'connector',id:7},title:'Source stale',detail:'Synthetic warning'}]});await tick();
  const tree=ui.render(),all=nodes(tree);
  assert.equal(ui.requests.length,1,'Monitoring GET never triggers connector fetch or synchronization');
  assert.ok(all.some(n=>n.children.includes('Окремі дані джерел. До показників ERP не додаються.')));
  assert.equal(all.filter(n=>n.type==='strong'&&n.children.includes('1')).length,1,'ERP total remains its own value');
  const tableNode=all.find(n=>n.type===ui.context.MonTable);
  assert.equal(tableNode.props.table,sourceTable);
  tableNode.props.onRow({kind:'connector',id:7});
  const attention=all.find(n=>n.type===ui.context.MonAttention);attention.props.onOpen({kind:'connector',id:7});
  all.find(n=>n.props.onClick&&n.children.includes('Відкрити джерело')).props.onClick();
  assert.deepEqual(ui.routes,[['connectors',7],['connectors',7],['connectors',7]]);
  assert.equal(ui.requests.length,1,'connector handoff happens before ERP snapshot lookup');
  const rendered=ui.context.MonTable({table:sourceTable,onRow:tableNode.props.onRow});
  assert.ok(nodes(rendered).some(n=>n.type==='td'&&n.children.includes('12.50 USD')),'source money uses currency-aware formatter');
  ui.setScope('user:2');assert.ok(!nodes(ui.render()).some(n=>n.props['aria-label']==='Підключені джерела у моніторингу'),'previous account source data is hidden');
  tableNode.props.onRow({kind:'connector',id:7});assert.equal(ui.routes.length,3,'retained source row cannot navigate after account change');
  const old=harness();old.mount();old.requests[0].resolve(base);await tick();
  assert.ok(!nodes(old.render()).some(n=>n.props['aria-label']==='Підключені джерела у моніторингу'),'old backend never pretends sources are available');
  const observer=harness();observer.mount();observer.requests[0].resolve({...base,sources:[{id:7,name:'Observer metadata',freshness_label:'Актуально',dataset_label:'Замовлення',last_sync_at:null}],source_attention:[]});await tick();
  assert.ok(!nodes(observer.render()).some(n=>n.type===observer.context.MonTable),'observer receives freshness without rows');
  const manager=harness();manager.mount();manager.requests[0].resolve({...base,sources:[{...source,table:{...sourceTable,columns:['Клієнт'],rows:[{ref:{kind:'connector',id:7},cells:['Synthetic']} ]}}],source_attention:[]});await tick();
  assert.deepEqual(nodes(manager.render()).find(n=>n.type===manager.context.MonTable).props.table.columns,['Клієнт'],'server role-scoped columns are preserved');
  const stale=harness();stale.mount();stale.setScope('user:2');stale.requests[0].resolve({...base,sources:[source]});await tick();assert.equal(stale.state[0],null,'old-account source response is ignored');
  const gone=harness();gone.mount();gone.unmount();gone.requests[0].resolve({...base,sources:[source]});await tick();assert.equal(gone.state[0],null,'unmounted source response is ignored');
  console.log('M3 Monitoring source blocks, role-shaped rows, separate ERP totals, exact connector handoff and stale reads: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
