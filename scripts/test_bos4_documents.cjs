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
