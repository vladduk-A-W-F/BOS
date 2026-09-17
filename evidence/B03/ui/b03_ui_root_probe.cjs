// Execute extracted UI functions. No browser/HTTP/DB acceptance is claimed.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const root='/workspace/scratch/c7b51e996a9f/tmp/b03_ui_candidate';
const source=fs.readFileSync(root+'/frontend/boss_app_source.html','utf8');
const Babel=require(root+'/assets/babel.js');
const inspector=source.slice(source.indexOf('function BoSInspector('),source.indexOf('function BoSHome('));
const helpers=source.match(/\/\/ B03_HELPERS_BEGIN\n([\s\S]*?)\/\/ B03_HELPERS_END/)[1];
const memory=new Map();
const context={console,sessionStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)},window:{BOS_RUNTIME:{access_revision:'before'},Event:class{constructor(type){this.type=type;}},dispatchEvent:()=>{}},bosStorageKey:k=>'bos:demo:7:ceo:'+k,
 useRef:()=>({current:{showModal:()=>{}}}),useState:v=>[v,()=>{}],useEffect:()=>{},
 React:{createElement:(type,props,...children)=>({type:typeof type==='function'?type.name:type,props,children}),Fragment:'fragment'},
 bosCan:()=>true,bosCanAction:()=>true,bosRole:()=>'ceo',Button:function Button(){},DocViewer:function DocViewer(){},B03RecordBody:function B03RecordBody(){}};
vm.createContext(context);vm.runInContext(helpers+'\n'+Babel.transform(inspector,{presets:['react']}).code,context);
const checks=[];
function run(name,fn){try{fn();checks.push({case:name,passed:true});}catch(e){checks.push({case:name,passed:false,error:e.message});}}
run('source movement opens its actual inspector body and Ukrainian title',()=>{
 const tree=context.BoSInspector({selection:{kind:'source_movements',id:31},data:{source_movements:[{id:31,kind:'receipt',quantity:'4.000'}]},onClose:()=>{},onSelect:()=>{}});
 assert.equal(tree.children[1]?.type,'B03RecordBody','Source card body must be the actual movement inspector');
 assert(!JSON.stringify(tree.children[0]).includes('undefined'),'Source card title must have a defined label');
});
run('same user and role keeps unknown receipt IDs after access revision changes',()=>{
 const entry={action:'return_supplier',operation_id:'a0000000-0000-4000-8000-000000000001',proposal_id:'b0000000-0000-4000-8000-000000000001'};
 context.b03PendingSave(entry);assert.equal(context.b03PendingRead().length,1);
 context.window.BOS_RUNTIME.access_revision='after';assert.equal(context.b03PendingRead().length,1,'Current permissions must be rechecked by API, but IDs must not become undiscoverable');
});
const report={scope:'Actual extracted JavaScript execution in Node with minimal React element/hook stubs; no DOM, browser, HTTP, DB or gate10',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),checks};
const destination=process.argv[2];if(destination)fs.writeFileSync(destination,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));process.exitCode=checks.some(c=>!c.passed)?1:0;
