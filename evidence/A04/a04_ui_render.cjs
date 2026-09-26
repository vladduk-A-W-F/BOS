// Narrow component render harness; no browser/effect/HTTP gate is claimed.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root='/workspace/sites/bos-original-refined';
const React=require(root+'/assets/react.js'),babel=require(root+'/assets/babel.js');
const src=fs.readFileSync('/workspace/scratch/c7b51e996a9f/tmp/a04_frontend_candidate.html','utf8');
let jsx=src.match(/<script type="text\/babel">([\s\S]*?)<\/script>/)[1].replace('{% verbatim %}','').replace('{% endverbatim %}','').replace(/ReactDOM\.createRoot[^\n]+/,'');
const allowed=new Set(['React','ReactDOM','window','document','navigator','location','localStorage','fetch','URL','Headers','FormData','File','Blob','FileReader','MediaRecorder','Audio','alert','confirm','prompt','console','setTimeout','clearTimeout','setInterval','clearInterval','requestAnimationFrame','cancelAnimationFrame','CustomEvent','DOMPurify','marked','atob','btoa','performance','URLSearchParams','Intl']);
const missing=new Set();
const code=babel.transform(jsx,{presets:['react'],filename:'a04-ui.jsx',plugins:[()=>({visitor:{ReferencedIdentifier(p){if(!p.scope.hasBinding(p.node.name)&&!allowed.has(p.node.name))missing.add(p.node.name);}}})]}).code;
assert.deepStrictEqual([...missing],[],'lexical identifiers');
let currentSeeds=[],hook=0;
React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current={
 useState(initial){const i=hook++;return [i in currentSeeds?currentSeeds[i]:typeof initial==='function'?initial():initial,()=>{}];},
 useEffect(){},useRef(value){return {current:value};}
};
const store=new Map();
const sandbox={React,console,URL,Headers,FormData,URLSearchParams,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},document:{body:{style:{}},getElementById:()=>null},window:{fetch:()=>{throw Error('Unexpected fetch during pure render')},innerWidth:1200,BOS_RUNTIME:null},location:{href:'http://testserver/',origin:'http://testserver'}};
vm.createContext(sandbox);vm.runInContext(code+`;globalThis.ui={BoSHome,ERPWorkspace,BoSInspector,Procurement,QuoteInspector,ActionJournal,NavBar,Topbar,BoSReadOnlyRecords,ERPActionDialog,App,INIT_SETTINGS,bosStorageKey,bosNavigation,bosCanView,bosCanAction};`,sandbox);
const ui=sandbox.ui,fixtures=JSON.parse(fs.readFileSync('/workspace/scratch/c7b51e996a9f/tmp/a04_ui_source.json','utf8'));
function render(Component,props,seeds=[]){currentSeeds=seeds;hook=0;return walk(Component(props));}
function walk(element){
 if(element==null||typeof element==='boolean')return '';
 if(Array.isArray(element))return element.map(walk).join(' ');
 if(typeof element!=='object')return String(element);
 if(typeof element.type==='function'){currentSeeds=[];hook=0;return walk(element.type(element.props));}
 return walk(element.props?.children);
}
let count=0;
const noop=()=>{};
const failures=[];
function check(label,fn){try{const text=fn();assert(!text?.includes('NaN'),label+' rendered NaN');assert(!text?.includes('undefined'),label+' rendered undefined');count++;return text;}catch(e){failures.push({label,error:e.stack});return '';}}
for(const role of ['ceo','manager','observer']){
 const f=fixtures[role],data=f.snapshot;
 sandbox.window.BOS_RUNTIME={role,user_id:role==='ceo'?1:role==='manager'?2:3,employee_id:role==='ceo'?1:role==='manager'?2:3,mode:'demo',as_of:'2026-09-09',capabilities:{finance:role==='ceo',hr_private:role==='ceo',write:role!=='observer',view_documents:true,download_documents:true,export_workspace:role!=='observer',external_llm:false}};
 const home=check(role+' home',()=>render(ui.BoSHome,{onNavigate:noop,refetchTasks:noop},[data]));
 if(role!=='ceo')assert(!home.includes('Вартість запасу')&&!home.includes('Портфель замовлень'),role+' home financial projection');
 for(const view of ['overview','catalog','sales','stock','production','purchase','quality','costs'])check(role+' ERP '+view,()=>render(ui.ERPWorkspace,{view,onNavigate:noop,refetchTasks:noop},[data]));
 for(const kind of ['orders','items','lots','jobs','purchases','invoices','changes','events','locations','partners'])for(const row of data[kind]||[])check(role+' inspector '+kind+' '+(row.id??row.invoice_id),()=>render(ui.BoSInspector,{selection:{kind,id:row.id??row.invoice_id},data,onClose:noop,onSelect:noop,onAction:noop,onNavigate:noop}));
 for(const key of ['tasks','jobs','lots','orders'])check(role+' list '+key,()=>render(ui.BoSInspector,{selection:{kind:'list',key,title:key},data,onClose:noop,onSelect:noop,onAction:noop,onNavigate:noop}));
 check(role+' procurement',()=>render(ui.Procurement,{refetchTasks:noop},[f.requests.items,'R01','5',f.compare]));
 for(const quote of f.compare.rows)check(role+' quote '+quote.code,()=>render(ui.QuoteInspector,{quote,data:f.compare,onClose:noop,onDocument:noop,onTask:noop}));
 check(role+' audit',()=>render(ui.ActionJournal,{},[f.audit.items]));
 check(role+' navbar',()=>render(ui.NavBar,{nav:{section:'dash',sub:null},setNav:noop,settings:ui.INIT_SETTINGS,aiPanelOpen:false,setAiPanelOpen:noop,tasks:f.tasks,aiConfigured:false}));
 for(const nav of [{section:'finance',sub:null},{section:'finance',sub:'bank'},{section:'finance',sub:'salaries'},{section:'hr',sub:'employees'},{section:'erp',sub:'costs'}]){
  const appSeeds=['app',{id:'manufacturing'},nav,role,false,f.tasks,false,null,[],f.employees.map(e=>({...e,name:e.full_name,dept:e.department})),false,null,ui.INIT_SETTINGS,f.counterparties,f.contracts,[],[],null,'month',null,null,'',false,[]];
  const text=check(role+' App '+JSON.stringify(nav),()=>render(ui.App,{},appSeeds));
  if(nav.section==='finance'&&nav.sub===null)assert(text.includes('Промислові закупівлі'),role+' finance default resolves procurement');
  if(nav.section==='finance'&&nav.sub==='bank'&&role==='manager')assert(text.includes('Журнал операцій')&&!text.includes('+ Нова транзакція'),'manager direct bank is metadata only');
  if(nav.section==='finance'&&nav.sub==='bank'&&role==='observer')assert(text.includes('Розділ недоступний'),'observer direct bank denied');
 }
 for(const action of ['item','order','purchase','receive','job','operator','quality','finish','ship','invoice','payment'])if(ui.bosCanAction(action))check(role+' action '+action,()=>render(ui.ERPActionDialog,{action,data,onClose:noop,onDone:noop}));
 const keys=[];for(const uid of [10,11])for(const r of ['ceo','manager','observer']){sandbox.window.BOS_RUNTIME={...sandbox.window.BOS_RUNTIME,user_id:uid,role:r};keys.push(ui.bosStorageKey('notes'));}assert.equal(new Set(keys).size,6);
}
fs.writeFileSync('/workspace/scratch/c7b51e996a9f/tmp/a04_ui_render_result.json',JSON.stringify({method:'Pure component render with actual synthetic HTTP response fixtures; not browser/effects/route acceptance',passed:count,failures},null,2));
if(failures.length){console.error(JSON.stringify(failures,null,2));process.exit(1);}
console.log('Babel + lexical PASS; component renders PASS '+count+'; user/role storage namespace checks PASS. Browser not run.');
