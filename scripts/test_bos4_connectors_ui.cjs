const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(require('node:path').join(__dirname, '..', 'assets/app.js'), 'utf8');
const component = app.match(/function Connections\(\)\s*\{[\s\S]*?\n}\s*(?=\/\/ BoS 4 first screen)/)?.[0];
assert.ok(component, 'compiled Connections component');

const React = {createElement:(type,props,...children)=>({type,props:props||{},children})};
const nodes = value => Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...(value.children||[]).flatMap(nodes)]:[];
const tick = () => new Promise(setImmediate);
const response = (data,ok=true) => ({ok,json:async()=>data});
const list = {connectors:[{id:7,name:'Продажі',kind:'google_sheets',dataset_label:'Замовлення',status:'ready',status_label:'Готово',last_sync_at:null,row_count:4}],catalog:[]};

function harness(write){
  let scope='user:1',hook=0,effect,cleanup;
  const state=[],refs=[],requests=[];
  const context={React,FormData:class{},Button:()=>{},Input:()=>{},BosFile:()=>{},Select:()=>{},
    bosCan:key=>key==='write'&&write,bosHttpScope:()=>scope,monValue:value=>String(value),
    useState(initial){const i=hook++;if(!(i in state))state[i]=initial;return [state[i],value=>{state[i]=typeof value==='function'?value(state[i]):value}];},
    useRef(initial){const i=hook++;if(!(i in refs))refs[i]={current:initial};return refs[i];},
    useEffect(fn){effect=fn;},
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),
  };
  vm.createContext(context);vm.runInContext(component,context);
  return {requests,state,render(){hook=0;return context.Connections();},mount(){this.render();cleanup=effect();},unmount(){cleanup();},setScope(value){scope=value;}};
}

(async()=>{
  const writer=harness(true);writer.mount();
  assert.equal(writer.requests.length,1);
  assert.equal(writer.requests[0].url,'/api/connectors/sync-stale/');
  assert.equal(writer.requests[0].options.method,'POST');
  writer.requests[0].resolve(response({synced:[],failed:[{id:7,name:'Продажі',error:'Джерело недоступне'}]}));
  await tick();
  assert.equal(writer.requests[1].url,'/api/connectors/');
  writer.requests[1].resolve(response(list));await tick();
  assert.ok(nodes(writer.render()).some(node=>node.type==='td'&&node.children.includes('Помилка оновлення: Джерело недоступне')),'failed connector error remains visible beside loaded list');
  writer.render();assert.equal(writer.requests.length,2,'one sync per mount, even after rerender');
  const writableRow=nodes(writer.render()).find(node=>node.type==='tr'&&node.props.className?.includes('bos-click-row'));
  assert.equal(typeof writableRow.props.onClick,'function','writer may open connector rows');

  const observer=harness(false);observer.mount();
  assert.equal(observer.requests.length,1);
  assert.equal(observer.requests[0].url,'/api/connectors/','observer only reads the list');
  observer.requests[0].resolve(response(list));await tick();
  const observerRow=nodes(observer.render()).find(node=>node.type==='tr'&&nodes(node).some(cell=>cell.type==='td'&&cell.children.includes('Продажі')));
  assert.ok(observerRow,'observer sees connector metadata');
  assert.equal(observerRow.props.onClick,undefined,'observer cannot open forbidden rows endpoint');
  assert.ok(!observerRow.props.className.includes('bos-click-row'),'observer row has no click affordance');
  assert.equal(observer.requests.length,1,'rendering observer list issues no rows request');

  const rejected=harness(true);rejected.mount();
  rejected.requests[0].reject(Error('Sync unavailable'));await tick();
  assert.equal(rejected.requests[1].url,'/api/connectors/','sync failure still loads list');
  rejected.requests[1].resolve(response(list));await tick();
  assert.ok(nodes(rejected.render()).some(node=>node.props.role==='alert'&&node.children.includes('Sync unavailable')));
  assert.ok(nodes(rejected.render()).some(node=>node.type==='td'&&node.children.includes('Продажі')));

  const stale=harness(true);stale.mount();stale.unmount();
  stale.requests[0].resolve(response({synced:[],failed:[]}));await tick();
  assert.equal(stale.requests.length,1,'unmounted response cannot start list fetch');
  const switched=harness(true);switched.mount();
  switched.requests[0].resolve(response({synced:[],failed:[]}));await tick();
  switched.setScope('user:2');switched.requests[1].resolve(response(list));await tick();
  assert.equal(switched.state[0],null,'old-account list response is ignored');
  console.log('M3 connector sync once, observer GET, failed rows/list, stale completion: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
