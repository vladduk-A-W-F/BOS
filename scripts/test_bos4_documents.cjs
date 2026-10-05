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
  Button, Select, DocumentImage:()=>{}, ERPActionDialog:()=>{},
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
