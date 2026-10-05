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
    let scope='user:1',hook=0,effect,cleanup;const state=[],refs=[],requests=[],routes=[],listeners={},frames=[];
    const opener={isConnected:true,focus(){this.focused=true;}};
    const context={React,Button:()=>{},BoSInspector:()=>{},C01TaskLegacy:()=>{},c01Scope:()=>scope,bosHttpScope:()=>scope,document:{activeElement:opener},requestAnimationFrame:fn=>frames.push(fn),erpDate:x=>x.split('T')[0].split('-').reverse().join('.'),erpDateTime:x=>x,
      erpMoney:(v,c)=>v+' '+c,
      useState(initial){const i=hook++;if(!(i in state))state[i]=initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
      useRef(initial){const i=hook++;if(!(i in refs))refs[i]={current:initial};return refs[i];},useEffect(fn){effect=fn;},
      window:{addEventListener:(key,fn)=>listeners[key]=fn,removeEventListener:key=>delete listeners[key]},
      erpFetch:path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}))};
    vm.createContext(context);vm.runInContext(block,context);
    return {context,state,requests,routes,listeners,opener,flushFrames(){frames.splice(0).forEach(fn=>fn());},render(){hook=0;return context.Monitoring({onNavigate:(...route)=>routes.push(route)});},mount(){this.render();cleanup=effect();},unmount(){cleanup();},setScope:v=>scope=v};
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
  const taskTable={key:'tasks',title:'Доручення',columns:['Доручення'],rows:[{ref:{kind:'task',id:42},cells:['Термінове доручення']},{ref:{kind:'task',id:43},cells:['Наступне доручення']}],total:2};
  for(const role of ['ceo','manager','observer']){
    const tasks=harness();tasks.setScope('user:1:'+role);tasks.mount();tasks.requests[0].resolve({...base,tables:[taskTable],attention:[{ref:{kind:'task',id:42}}]});await tick();
    const row=nodes(tasks.render()).find(n=>n.type===tasks.context.MonTable).props.onRow;
    row({kind:'task',id:0});row({kind:'task',id:44});row({kind:'task',id:'42'});
    assert.ok(!nodes(tasks.render()).some(n=>n.type===tasks.context.C01TaskLegacy),'invalid and hidden IDs cannot open');
    row({kind:'task',id:42});
    let dialog=nodes(tasks.render()).find(n=>n.type===tasks.context.C01TaskLegacy);
    assert.equal(dialog.props.taskId,42,'row opens the exact task ID');
    assert.equal(dialog.props.mode,'view');assert.equal(dialog.props.onHandoff,undefined,'monitoring does not offer handoff');
    assert.equal(tasks.requests.length,1,'opening a task does not fetch ERP snapshot');
    assert.deepEqual(tasks.routes,[],'task does not navigate to the HR list');
    const oldClose=dialog.props.onClose;oldClose();tasks.render();
    row({kind:'task',id:43});oldClose();tasks.flushFrames();
    dialog=nodes(tasks.render()).find(n=>n.type===tasks.context.C01TaskLegacy);
    assert.equal(dialog.props.taskId,43,'retained close cannot dismiss a newer task');
    assert.notEqual(tasks.opener.focused,true,'old frame cannot focus behind the newer dialog');
    dialog.props.onClose();tasks.flushFrames();assert.equal(tasks.opener.focused,true,'current close restores focus to connected row');
    row({kind:'task',id:42});tasks.listeners['bos:data-changed']();oldClose();tasks.flushFrames();
    assert.ok(!nodes(tasks.render()).some(n=>n.type===tasks.context.C01TaskLegacy),'reload closes task before its response');
    tasks.requests[1].resolve({...base,tables:[]});await tick();
    assert.ok(!nodes(tasks.render()).some(n=>n.type===tasks.context.C01TaskLegacy),'old task stays closed after reload');
    row({kind:'task',id:42});assert.ok(!nodes(tasks.render()).some(n=>n.type===tasks.context.C01TaskLegacy),'retained row cannot reopen a removed task');
    tasks.unmount();oldClose();tasks.flushFrames();assert.ok(!nodes(tasks.render()).some(n=>n.type===tasks.context.C01TaskLegacy),'retained close after unmount is inert');
  }
  const query=harness();query.mount();query.requests[0].resolve({...base,queries:[{key:'overdue',title:'Прострочені доручення'}]});await tick();
  nodes(query.render()).find(n=>n.props.onClick&&n.children.includes('Прострочені доручення')).props.onClick();
  query.requests[1].resolve({...taskTable,key:'overdue'});await tick();
  nodes(query.render()).find(n=>n.type===query.context.MonTable).props.onRow({kind:'task',id:42});
  assert.equal(nodes(query.render()).find(n=>n.type===query.context.C01TaskLegacy).props.taskId,42,'query row opens exact task');
  const attentionUi=harness();attentionUi.mount();attentionUi.requests[0].resolve({...base,attention:[{ref:{kind:'task',id:42}}]});await tick();
  nodes(attentionUi.render()).find(n=>n.type===attentionUi.context.MonAttention).props.onOpen({kind:'task',id:42});
  assert.equal(nodes(attentionUi.render()).find(n=>n.type===attentionUi.context.C01TaskLegacy).props.taskId,42,'attention opens exact task');
  const taskSource=fs.readFileSync(path.join(__dirname,'../frontend/boss_app_source.html'),'utf8');
  assert.match(taskSource,/recordId\?request\('\/api\/tasks\/'\+recordId\+'\/'\)/,'task viewer reads the exact server record');
  assert.match(taskSource,/canEdit=writable&&initialMode!=='view'/,'view mode suppresses write controls');
  assert.match(taskSource,/if\(\[403,404\]\.includes\(r\.status\)\)denyScope\(\)/,'denied or missing task clears viewer data');
  const viewerCode=app.slice(app.indexOf('function C01TaskLegacy('),app.indexOf('function ProcurementEntry('));
  function viewer(role,taskStatus=200){
    let hook=0,effect;const state=[],refs=[],calls=[];
    const React={createElement:(type,props,...children)=>{if(type==='dialog'&&props.ref)props.ref.current={showModal(){},close(){}};return {type,props:props||{},children:children.flat(Infinity)};}};
    const context={React,Button:()=>{},C01HandoffFacts:()=>{},C01TaskSource:()=>{},C01Impact:()=>{},C01_FIELDS:[],C01_STATUS:{active:'Активне'},C01_TRANSITIONS:{},ERP_LABELS:{},
      c01Own:(o,k)=>Object.hasOwn(o,k),c01Form:()=>({assignee_id:''}),c01Date:()=>true,c01Assignee:()=>'',c01GatherSources:()=>[],bosCan:key=>key==='write'&&role!=='observer',
      useState(initial){const i=hook++;if(!(i in state))state[i]=initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
      useRef(initial){const i=hook++;if(!(i in refs))refs[i]={current:initial};return refs[i];},useEffect:fn=>effect=fn,AbortController,setTimeout,clearTimeout,
      fetch:async(url,options)=>{calls.push({url,method:options.method||'GET'});const status=url==='/api/tasks/42/'?taskStatus:200;
        const body=url==='/api/tasks/42/'?status===200?{id:42,title:'Термінове доручення',status:'active',result:''}:{error:'Недоступно'}
          :url==='/api/employees/'?[]:{orders:[],as_of:'2026-10-05'};
        return {ok:status===200,status,json:async()=>body};}};
    vm.createContext(context);vm.runInContext(viewerCode,context);
    return {calls,render(){hook=0;return context.C01TaskLegacy({taskId:42,mode:'view',onClose:()=>{}});},mount(){this.render();effect();}};
  }
  for(const role of ['ceo','manager','observer']){
    const view=viewer(role);view.mount();await tick();const tree=nodes(view.render());
    assert.deepEqual(view.calls.map(c=>[c.url,c.method]),[['/api/tasks/42/','GET'],['/api/employees/','GET'],['/api/erp/snapshot/','GET']]);
    assert.ok(tree.some(n=>n.type==='strong'&&n.children.includes('Термінове доручення')),'exact server task is rendered');
    assert.ok(!tree.some(n=>n.type==='form'||n.children.includes('Передати доручення')),'view has no edit or handoff controls');
  }
  for(const status of [403,404]){
    const denied=viewer('ceo',status);denied.mount();await tick();const tree=nodes(denied.render());
    assert.ok(!tree.some(n=>n.type==='strong'&&n.children.includes('Термінове доручення')),'denied task data is absent');
    assert.ok(tree.some(n=>n.props.role==='alert'&&n.children.includes('Недоступно')),'denied task explains read failure');
    assert.ok(denied.calls.every(c=>c.method==='GET'),'denied view never writes');
  }
  const rendered=ui.context.MonTable({table:sourceTable,onRow:tableNode.props.onRow});
  assert.ok(nodes(rendered).some(n=>n.type==='td'&&n.children.includes('12.50 USD')),'source money uses currency-aware formatter');
  const headings=tree=>nodes(tree).filter(n=>n.type==='th').map(n=>n.children[0]);
  assert.deepEqual(headings(rendered),['Клієнт','Сума'],'formatted source amount carries currency without a duplicate column');
  assert.deepEqual(nodes(rendered).filter(n=>n.type==='td').map(n=>n.props['data-label']),['Клієнт','Сума'],'visible headers and mobile cell labels remain aligned');
  vm.runInContext(app.match(/const erpDate = [\s\S]*?(?=const erpDateTime =)/)[0],ui.context);
  const currencyTable=(amount,kind='connector',columns=['Сума','Валюта'])=>ui.context.MonTable({table:{...sourceTable,columns,rows:[{ref:{kind,id:7},cells:columns.length===1?['USD']:[amount,'USD']}]},onRow:()=>{}});
  for(const amount of ['0.00','-1234.50','999999999999.99']){
    const view=currencyTable(amount);
    assert.deepEqual(headings(view),['Сума']);
    assert.equal(nodes(view).find(n=>n.type==='td').children[0],vm.runInContext('erpMoney('+JSON.stringify(amount)+',"USD")',ui.context),'source currency remains in the existing exact formatter');
  }
  for(const amount of [null,'']){
    const view=currencyTable(amount);
    assert.deepEqual(headings(view),['Сума','Валюта'],'empty source amount keeps the provided currency column');
    assert.ok(nodes(view).some(n=>n.type==='td'&&n.props['data-label']==='Валюта'&&n.children.includes('USD')));
  }
  assert.deepEqual(headings(currencyTable(null,'connector',['Валюта'])),['Валюта'],'currency-only source keeps its currency');
  const erpView=currencyTable('12.50','invoice');
  assert.deepEqual(headings(erpView),['Сума','Валюта'],'ERP columns remain unchanged');
  assert.deepEqual(nodes(erpView).filter(n=>n.type==='td').map(n=>n.children[0]),['12.50','USD'],'ERP cell values remain unchanged');
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
