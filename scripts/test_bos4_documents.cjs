const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(require('node:path').join(__dirname, '..', 'assets/app.js'), 'utf8');
const component = app.match(/function DocumentImage\([\s\S]*?\n}\n(?=function DocViewer)/)?.[0];
assert.ok(component, 'compiled DocumentImage component');
let state = 'loading';
const React = {createElement: (type, props, ...children) => ({type, props: props || {}, children})};
const context = {React, OP: '/api/operations/', useState: () => [state, next => {state = next}]};
vm.createContext(context);
vm.runInContext(component, context);
const doc = {id: 42, title: 'Фото перевірки'};
const flatten = node => [node, ...(node?.children || []).flatMap(flatten)];
let view = context.DocumentImage({doc});
let image = flatten(view).find(node => node.type === 'img');
assert.equal(image.props.src, '/api/operations/documents/42/view/');
assert.ok(flatten(view).some(node => node?.props?.role === 'status'));
image.props.onError();
view = context.DocumentImage({doc});
assert.equal(flatten(view).find(node => node.type === 'img').props.style.display, 'none');
assert.ok(flatten(view).some(node => node?.props?.role === 'alert' && node.children.join('').includes('пошкоджене')));
state = 'loading';
image.props.onLoad();
view = context.DocumentImage({doc});
assert.ok(!flatten(view).some(node => node?.props?.role === 'alert'));
console.log('M8 document image loading, private URL, damaged preview, and loaded state: PASS');

const viewer = app.match(/function DocViewer\([\s\S]*?\n}\n(?=\/\/ C01_HELPERS_BEGIN)/)?.[0];
assert.ok(viewer, 'compiled DocViewer component');
const Button = () => {}, Select = () => {};
const hooks = []; let hook = 0, refs = 0, mounted = false;
const calls = [];
const detail = id => ({id, title:'Джерело '+id, code:'DOC', revision:id === 1?'A':'B', status:'needs_review', current:true, text:'Перевірений текст', checksum:'sha'+id, image:false, contract_id:null, sections:[], versions:[{id:1,revision:'A'},{id:2,revision:'B'}]});
const ctx = {
  React, OP:'/api/operations/', OP_STATUS:{needs_review:'Потребує перевірки'}, T:{textMuted:'#555',primary:'#080'},
  Button, Select, DocumentImage:()=>{}, DocumentLinks:()=>{}, ERPActionDialog:()=>{},
  bosCan:key=>key==='write', bosCanAction:()=>false, bosHttpScope:()=> 'session-1',
  useState(initial){const i=hook++;if(!(i in hooks))hooks[i]=initial;return [hooks[i], value=>{hooks[i]=typeof value==='function'?value(hooks[i]):value}];},
  useRef(initial){const i=hook++;if(!(i in hooks))hooks[i]={current:refs++===0?{showModal(){},close(){}}:initial};return hooks[i];},
  useEffect(effect){if(!mounted){mounted=true;effect();}},
  opFetch:async (path, body)=>{calls.push({path,body});if(path.endsWith('/review/'))return {status:'approved'};return detail(Number(path.match(/documents\/(\d+)\//)[1]));},
  fetch:async ()=>({ok:true,json:async()=>[{id:77,number:'X',name:'Договір X'}]}),
};
vm.createContext(ctx);
vm.runInContext(viewer,ctx);
const tree = node => Array.isArray(node)?node.flatMap(tree):node&&typeof node==='object'?[node,...(node.children||[]).flatMap(tree)]:[];
const render = () => {hook=0;return ctx.DocViewer({id:1,onClose(){}})};
const button = (view,label) => tree(view).find(node=>node.type===Button&&node.children.flat(Infinity).join('')===label);
// Photo attachment uses the existing command dialog; a delayed snapshot must never bind another version.
(async()=>{
  const tick=()=>new Promise(setImmediate);
  function photoHarness({readOnly=false,status='ocr_required',image=true,current=true}={}){
    let hook=0,mounted=false,cleanup,scope='session-1',allowed=true;const hooks=[],requests=[];
    const photo=id=>({...detail(id),status,image,current,text:''});
    const context={...ctx,bosHttpScope:()=>scope,bosCanAction:()=>allowed,
      useState(initial){const i=hook++;if(!(i in hooks))hooks[i]=initial;return [hooks[i],v=>hooks[i]=typeof v==='function'?v(hooks[i]):v];},
      useRef(initial){const i=hook++;if(!(i in hooks))hooks[i]={current:initial===null?{showModal(){},close(){}}:initial};return hooks[i];},
      useEffect(fn){if(!mounted){mounted=true;cleanup=fn();}},
      opFetch:async path=>photo(Number(path.match(/documents\/(\d+)\//)[1])),
      erpFetch:path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}))};
    vm.createContext(context);vm.runInContext(viewer,context);
    return {requests,context,render(){hook=0;return context.DocViewer({id:1,readOnly,onClose(){}});},unmount(){cleanup();},scope(){scope='session-2';},deny(){allowed=false;}};
  }
  const ui=photoHarness();ui.render();await tick();
  assert.ok(!button(ui.render(),'Підтвердити ручну перевірку'),'OCR photo remains unapproved');
  assert.ok(tree(ui.render()).some(n=>n.type==='p'&&n.children.join('').includes('не підтверджує якість чи допуск')));
  const attach=button(ui.render(),'Прив’язати до партії').props.onClick;
  attach();await tick();attach();assert.equal(ui.requests.length,1,'pending snapshot admits one attachment intent');
  ui.requests[0].resolve({documents:[{id:1},{id:2}],lots:[{id:17}]});await tick();
  const dialog=tree(ui.render()).find(n=>n.type===ui.context.ERPActionDialog);
  assert.equal(dialog.props.action,'attach');assert.equal(dialog.props.preset.document_id,1);
  assert.equal(dialog.props.data.lots[0].id,17,'existing lot selection and preview/confirm dialog is reused');
  for(const boundary of ['version','scope','role','close','unmount']){
    const h=photoHarness();h.render();await tick();const saved=button(h.render(),'Прив’язати до партії').props.onClick;
    saved();await tick();
    if(boundary==='version')await button(h.render(),'Версія B').props.onClick();
    else if(boundary==='scope')h.scope();else if(boundary==='role')h.deny();else if(boundary==='close')button(h.render(),'Закрити').props.onClick();else h.unmount();
    h.requests[0].resolve({documents:[{id:1},{id:2}]});await tick();
    assert.ok(!tree(h.render()).some(n=>n.type===h.context.ERPActionDialog),'late snapshot rejected after '+boundary);
    saved();await tick();assert.equal(h.requests.length,1,'retained attachment handler rejected after '+boundary);
  }
  for(const flags of [{readOnly:true},{current:false}]){
    const h=photoHarness(flags);h.render();await tick();assert.ok(!button(h.render(),'Прив’язати до партії'),'ineligible photo has no attachment action');
  }
  for(const flags of [{image:false,status:'ocr_required'},{image:false,status:'needs_review'},{image:false,status:'approved'}]){
    const h=photoHarness(flags);h.render();await tick();
    const open=button(h.render(),'Прив’язати до партії');
    assert.ok(open,'current visible PDF/Excel can be filed before content approval');
    open.props.onClick();await tick();
    h.requests[0].resolve({documents:[{id:1,status:flags.status}],lots:[{id:17}]});await tick();
    const attached=tree(h.render()).find(n=>n.type===h.context.ERPActionDialog);
    assert.equal(attached.props.action,'attach');assert.equal(attached.props.preset.document_id,1);
    assert.ok(!button(h.render(),'Підтвердити ручну перевірку'),'filing does not approve an empty-text document');
  }
  const missing=photoHarness();missing.render();await tick();button(missing.render(),'Прив’язати до партії').props.onClick();await tick();missing.requests[0].resolve({documents:[{id:2}]});await tick();
  assert.ok(!tree(missing.render()).some(n=>n.type===missing.context.ERPActionDialog),'hidden or absent document cannot use snapshot');
  const fieldCode=app.slice(app.indexOf('function ERPActionDialog(')).match(/function field\([\s\S]*?\n  }\n/)?.[0];
  assert.ok(fieldCode,'compiled ERP dialog field');
  const fieldContext={React,Input:()=>{},action:'attach',preset:{document_id:1},values:{document_id:1},options:()=>[{value:1,label:'Фото A'},{value:2,label:'Фото B'}]};
  vm.createContext(fieldContext);vm.runInContext(fieldCode,fieldContext);
  const sourceField=tree(fieldContext.field(['document_id','Документ','documents'])).find(n=>n.type===fieldContext.Input);
  assert.equal(sourceField.props.readOnly,true);assert.equal(sourceField.props.value,'Фото A');
  assert.equal(sourceField.props.onChange,undefined,'exact preset photo cannot be replaced in the attach dialog');
  console.log('M8 current OCR photo exact lot dialog, quality boundary and stale snapshot guards: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
(async()=>{
  render();await new Promise(setImmediate);
  let current=render();
  assert.ok(button(current,'Обрати договір'), 'A contract chooser');
  await button(current,'Обрати договір').props.onClick();
  current=render();
  tree(current).find(node=>node.type===Select).props.onChange({target:{value:'77'}});
  current=render();
  await button(current,'Версія B').props.onClick();
  current=render();
  assert.ok(button(current,'Обрати договір'), 'B must require a fresh contract choice');
  await button(current,'Підтвердити ручну перевірку').props.onClick();
  const reviewCall=calls.find(call=>call.path==='documents/2/review/');
  assert.ok(reviewCall, 'B review request');
  assert.equal(reviewCall.body.checksum,'sha2');
  assert.equal(Object.hasOwn(reviewCall.body,'contract_id'),false,'A contract must not leak to B');
  console.log('M8 document A→B contract reset and exact review payload: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});

(async()=>{
  const path=require('node:path');
  const source=fs.readFileSync(path.join(__dirname,'check_confirmation_recovery.cjs'),'utf8').split('function receipt(')[0]
    .replace('const context={React,window,document,sessionStorage:store,console,',"const context={useERPProjection:()=>({state:{status:'idle'},refresh:async()=>null}),React,window,document,sessionStorage:store,console,");
  const sandbox={require,__dirname,console,setImmediate,setTimeout,clearTimeout,AbortController,Headers,URL,TextEncoder,Uint8Array};
  vm.createContext(sandbox);vm.runInContext(source+'\nthis.make=harness;',sandbox);
  function attachment(status,documents={passport:11},documentId=42){
    const dialog=sandbox.make({action:'attach',preset:{document_id:documentId,lot_id:5,kind:'passport'}});
    dialog.props.data.documents=[{id:documentId,status,title:'Синтетичний документ'}];
    dialog.props.data.lots=[{id:5,code:'LOT-5',quality:'approved',documents}];
    dialog.render();return dialog;
  }
  for(const status of ['ocr_required','needs_review','rejected']){
    const dialog=attachment(status),kind='Додаток №42';
    const input=dialog.all().find(node=>node.type===dialog.context.Input&&node.props.value===kind);
    assert.ok(input?.props.readOnly&&!input.props.onChange,'unapproved kind is fixed, not the unsafe preset');
    const payload=await dialog.prepared();
    assert.equal(JSON.stringify(payload),JSON.stringify({action:'erp_attach',lot_id:5,kind,document_id:42}));
    assert.equal(dialog.props.data.lots[0].documents.passport,11,'existing passport retained');
    assert.equal(dialog.props.data.lots[0].quality,'approved','attachment does not approve/revoke quality');
    dialog.click('Погодити й виконати');await dialog.flush();
    assert.equal(JSON.stringify(JSON.parse(dialog.requests[1].options.body)),JSON.stringify({proposal_id:'11111111-1111-4111-8111-111111111111',confirmed:true}));
    dialog.unmount();
  }
  const occupied=attachment('ocr_required',{'Додаток №42':11});
  await occupied.preview();assert.equal(occupied.requests.length,0,'occupied kind must not create a preview');
  assert.match(occupied.text(),/Неперевірений документ не замінює його/);occupied.unmount();
  const second=attachment('ocr_required',{passport:11,'Додаток №42':42},43);
  assert.equal((await second.prepared()).kind,'Додаток №43','another photo or scan has a separate attachment');second.unmount();
  const approved=attachment('approved');
  assert.equal((await approved.prepared()).kind,'passport','approved-document flow remains unchanged');approved.unmount();
  const missing=attachment('ocr_required');missing.props.data.documents=[];missing.render();await missing.preview();
  assert.equal(missing.requests.length,0,'missing visible document is refused');missing.unmount();
  console.log('M8 actual attachment dialog: unapproved separate kind, occupied-kind refusal, multiple files, approved flow, explicit confirm: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});

const uploadCode = app.match(/function documentUploadCode\([\s\S]*?\n}\n(?=function DocumentRegistry)/)?.[0];
const registry = app.match(/function DocumentRegistry\([\s\S]*?\n}\n(?=function ActionJournal)/)?.[0];
assert.ok(uploadCode && registry, 'compiled document upload code and registry');
const uploads = [];
const fields = {code:{value:''},revision:{value:'A'},title:{value:'Акт приймання'}};
const uploadForm = {elements:fields,reset(){for(const field of Object.values(fields))field.value=''}};
class UploadFormData {
  constructor(form){this.values = new Map(Object.entries(form.elements).map(([key,field])=>[key,field.value]));}
  get(key){return this.values.get(key);}
  set(key,value){this.values.set(key,value);}
}
let uploadHook = 0;
const uploadHooks = [];
const uploadContext = {
  React, FormData:UploadFormData, Card:()=>{}, Button:()=>{}, Input:()=>{}, DocViewer:()=>{},
  OP_STATUS:{}, T:{red:'#f00'}, bosCan:()=>true, useEffect:()=>{},
  useState(initial){const i=uploadHook++;if(!(i in uploadHooks))uploadHooks[i]=initial;return [uploadHooks[i],value=>{uploadHooks[i]=typeof value==='function'?value(uploadHooks[i]):value}];},
  useRef(initial){const i=uploadHook++;if(!(i in uploadHooks))uploadHooks[i]={current:initial===null?uploadForm:initial};return uploadHooks[i];},
  opFetch:async(path,body)=>{if(path==='documents/upload/'){uploads.push(body);throw Error('Server conflict');}return {items:[]};},
};
vm.createContext(uploadContext);
vm.runInContext(uploadCode+registry,uploadContext);
const uploadView=()=>{uploadHook=0;return uploadContext.DocumentRegistry()};
const uploadSubmit=()=>tree(uploadView()).find(node=>node.type==='form'&&node.props.className==='op-upload').props.onSubmit({preventDefault(){}});
(async()=>{
  const fixed=uploadContext.documentUploadCode('Акт приймання',new Date(2026,9,5,14,30,12,123),'abc123');
  assert.equal(fixed,'20261005-143012123-abc123-Акт-приймання');
  assert.ok(uploadContext.documentUploadCode('Дуже довга назва '.repeat(20)).length<=80);
  await uploadSubmit();
  assert.equal(uploads.length,1,'one request; no hidden retry after conflict');
  assert.equal(uploads[0].get('code'),fields.code.value,'generated code stays visible after error');
  const generated=fields.code.value;
  await uploadSubmit();
  assert.equal(uploads[1].get('code'),generated,'retry reuses the same generated code');
  fields.code.value='DOC-MANUAL';fields.revision.value='B';
  await uploadSubmit();
  assert.equal(uploads[2].get('code'),'DOC-MANUAL','new revision preserves manual document code');
  assert.equal(uploads[2].get('revision'),'B');
  console.log('Document upload generated code, stable retry, manual revision code: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
