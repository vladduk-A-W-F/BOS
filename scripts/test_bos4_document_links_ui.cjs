const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'..','assets/app.js'),'utf8');
const component=app.match(/function DocumentLinks\([\s\S]*?\n}\s*(?=function DocumentImage)/)?.[0];
assert.ok(component,'compiled DocumentLinks component');
const docKinds=vm.runInNewContext(app.match(/^const ERP_DOC_KINDS = [\s\S]*?\};/m)?.[0]+';ERP_DOC_KINDS');
assert.equal(docKinds.certificate,'сертифікат якості');
const React={createElement:(type,props,...children)=>({type,props:props||{},children})};
const all=value=>Array.isArray(value)?value.flatMap(all):value&&typeof value==='object'?[value,...(value.children||[]).flatMap(all)]:[];
const text=value=>Array.isArray(value)?value.map(text).join(''):value&&typeof value==='object'?text(value.children):String(value??'');
const tick=()=>new Promise(setImmediate);
function harness(role,doc={id:42,current:true}){
 let cursor=0,scope='person:1',cleanup,pendingEffect;
 const hooks=[],calls=[],events=new Map();
 const Button=()=>{},Select=()=>{},Input=()=>{},ERPActionDialog=()=>{};
 const ctx={React,Button,Select,Input,ERPActionDialog,ERP_DOC_KINDS:docKinds,window:{addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name)},
  bosHttpScope:()=>scope,bosRole:()=>role,bosCanAction:()=>role!=='observer',
  erpFetch:path=>new Promise((resolve,reject)=>calls.push({path,resolve,reject})),
  useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=initial;return [hooks[i],value=>{hooks[i]=typeof value==='function'?value(hooks[i]):value}];},
  useRef(initial){const i=cursor++;if(!(i in hooks))hooks[i]={current:initial};return hooks[i];},
  useEffect(effect){cursor++;if(!cleanup)pendingEffect=effect;},
 };
 vm.createContext(ctx);vm.runInContext(component,ctx);
 const render=()=>{cursor=0;const view=ctx.DocumentLinks({doc,readOnly:false});if(pendingEffect){cleanup=pendingEffect();pendingEffect=null;}return view;};
 const button=label=>all(render()).find(node=>node.type===Button&&text(node)===label);
 return {calls,render,button,Select,ERPActionDialog,unmount(){cleanup?.();},setScope(value){scope=value;},sessionEnded(){events.get('bos:session-ended')?.();}};
}
(async()=>{
 const rows={links:[{id:1,order:{id:3,code:'ZM-3'},invoice:null,note:'Джерело'}]};
 const snapshot={orders:[{id:3,code:'ZM-3'}],invoices:[{invoice_id:7,order_id:3,code:'RF-7'},{invoice_id:7,order_id:4,code:'RF-7'},{invoice_id:8,order_id:5,code:'RF-8'}],documents:[{id:42,code:'DOC'}]};
 const snapshotBytes=JSON.stringify(snapshot);
 const observer=harness('observer');observer.render();
 assert.equal(observer.calls[0].path,'document-links/?document=42');observer.calls[0].resolve(rows);await tick();
 assert.ok(text(observer.render()).includes('Замовлення ZM-3'));
 assert.equal(observer.button('Прив’язати до замовлення або рахунку'),undefined,'observer has no write action');observer.unmount();

 // A document also shows the lots it is filed under (reverse of «attach to lot»), in plain Ukrainian.
 const filed=harness('observer');filed.render();
 filed.calls[0].resolve({lots:[{id:5,code:'KM-L-1',kind:'certificate'},{id:6,code:'KM-L-2',kind:'custom_kind'}],links:[]});await tick();
 const filedText=text(filed.render());
 assert.ok(filedText.includes('Партія KM-L-1 · сертифікат якості'),filedText);
 assert.ok(filedText.includes('Партія KM-L-2 · custom_kind'),'unknown kinds are shown as they are');
 assert.ok(!filedText.includes('Зв’язків поки немає'),'lots count as links');filed.unmount();

 const manager=harness('manager');manager.render();manager.calls[0].resolve(rows);await tick();
 manager.button('Прив’язати до замовлення або рахунку').props.onClick();
 assert.equal(manager.calls[1].path,'snapshot/');manager.calls[1].resolve(snapshot);await tick();
 let view=manager.render();
 assert.ok(!all(view).some(node=>node.type==='option'&&node.props.value==='invoice:7'),'manager cannot select an invoice');
 all(view).find(node=>node.type===manager.Select).props.onChange({target:{value:'order:3'}});
 manager.button('Перевірити прив’язку').props.onClick();
 const action=all(manager.render()).find(node=>node.type===manager.ERPActionDialog);
 assert.equal(action.props.action,'link_document');
 assert.equal(JSON.stringify(action.props.preset),JSON.stringify({document_id:42,order_id:3}));
 assert.equal(manager.calls.length,2,'selection does not preview or confirm automatically');
 const stale=manager.button('Перевірити прив’язку').props.onClick;
  manager.setScope('person:2');stale();
  assert.ok(!all(manager.render()).some(node=>node.type===manager.ERPActionDialog),'account change hides stale action');manager.unmount();

  const ended=harness('ceo');ended.render();ended.calls[0].resolve(rows);await tick();
  ended.sessionEnded();assert.ok(text(ended.render()).includes('Сесію змінено'),'session-end invalidates target state even when scope string is unchanged');ended.unmount();

 const old=harness('ceo');old.render();old.calls[0].resolve({links:[]});await tick();
 old.button('Прив’язати до замовлення або рахунку').props.onClick();old.unmount();
 old.calls[1].resolve(snapshot);await tick();
 assert.ok(!all(old.render()).some(node=>node.type===old.Select),'old version response cannot supply targets after unmount');
 const newer=harness('ceo',{id:43,current:true});newer.render();assert.equal(newer.calls[0].path,'document-links/?document=43');newer.calls[0].resolve({links:[]});await tick();
 newer.button('Прив’язати до замовлення або рахунку').props.onClick();newer.calls[1].resolve(snapshot);await tick();
 view=newer.render();
 const invoiceOptions=all(view).filter(node=>node.type==='option'&&String(node.props.value).startsWith('invoice:'));
 assert.deepEqual(invoiceOptions.map(node=>node.props.value),['invoice:7','invoice:8'],'one option per invoice ID in first-seen order');
 assert.equal(new Set(invoiceOptions.map(node=>node.props.key)).size,invoiceOptions.length,'React invoice keys are unique');
 assert.equal(JSON.stringify(snapshot),snapshotBytes,'snapshot rows are not mutated');
 all(view).find(node=>node.type===newer.Select).props.onChange({target:{value:'invoice:7'}});
 newer.button('Перевірити прив’язку').props.onClick();
 const invoicePreset=all(newer.render()).find(node=>node.type===newer.ERPActionDialog).props.preset;
 assert.equal(JSON.stringify(invoicePreset),JSON.stringify({document_id:43,invoice_id:7}));newer.unmount();

 const source=fs.readFileSync(path.join(__dirname,'check_confirmation_recovery.cjs'),'utf8').split('function receipt(')[0]
  .replace('const context={React,window,document,sessionStorage:store,console,',"const context={useERPProjection:()=>({state:{status:'idle'},refresh:async()=>null}),React,window,document,sessionStorage:store,console,");
 const context={require,__dirname,console,setImmediate,setTimeout,clearTimeout,AbortController,Headers,URL,TextEncoder,Uint8Array};
 vm.createContext(context);vm.runInContext(source+'\nthis.make=harness;',context);
 const dialog=context.make({action:'link_document',preset:{document_id:42,order_id:3,note:'Синтетичне джерело'}});
 const note=dialog.all().find(node=>node.type==='label'&&dialog.text(node).includes('Примітка'));
 assert.ok(note,'link note field');
 assert.equal(dialog.all(note).find(node=>node.type===dialog.context.Input).props.maxLength,200,'note limit matches server contract');
 const payload=await dialog.prepared();
 assert.equal(JSON.stringify(payload),JSON.stringify({action:'erp_link_document',document_id:42,order_id:3,note:'Синтетичне джерело'}));
 dialog.click('Погодити й виконати');await dialog.flush();
 const confirm=dialog.requests.find(request=>request.url==='/api/operations/confirm/');
 assert.ok(confirm,'explicit confirmation uses existing endpoint');
 assert.equal(JSON.stringify(JSON.parse(confirm.options.body)),JSON.stringify({proposal_id:'11111111-1111-4111-8111-111111111111',confirmed:true}));dialog.unmount();
 const invoiceDialog=context.make({action:'link_document',preset:invoicePreset});
 const invoicePayload=await invoiceDialog.prepared();
 assert.equal(JSON.stringify(invoicePayload),JSON.stringify({action:'erp_link_document',document_id:43,invoice_id:7}),'preview uses the selected invoice ID once');invoiceDialog.unmount();
 console.log('M8 document links: roles, version/account isolation, exact preview and explicit confirm: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
