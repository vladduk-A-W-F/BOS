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

function harness(write,extra={}){
  let scope='user:1',hook=0,effect,cleanup;
  const state=[],refs=[],requests=[];
  const context={React,FormData:class{constructor(){this.items=[];}append(k,v){this.items.push([k,v]);}},Button:()=>{},Input:()=>{},BosFile:()=>{},Select:()=>{},
    bosCan:key=>key==='write'&&write,bosHttpScope:()=>scope,monValue:value=>String(value),bosFileName:()=>{},
    useState(initial){const i=hook++;if(!(i in state))state[i]=initial;return [state[i],value=>{state[i]=typeof value==='function'?value(state[i]):value}];},
    useRef(initial){const i=hook++;if(!(i in refs))refs[i]={current:initial};return refs[i];},
    useEffect(fn){effect=fn;},
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),
    ...extra,
  };
  vm.createContext(context);vm.runInContext(component,context);
  return {requests,state,render(){hook=0;return context.Connections();},mount(){this.render();cleanup=effect();},unmount(){cleanup();},setScope(value){scope=value;}};
}

(async()=>{
  // Mapping is preview-only: exercise actual compiled event handlers and out-of-order replies.
  {
    const ui=harness(true);ui.mount();
    ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();
    ui.requests[1].resolve(response(list));await tick();
    const button=(label)=>nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes(label));
    const field=(label)=>nodes(nodes(ui.render()).find(n=>n.type==='label'&&n.children.includes(label))).find(n=>n.props.onChange);
    const mappingField=(label)=>nodes(ui.render()).find(n=>n.props['aria-label']===label);
    const mappingSection=()=>nodes(ui.render()).find(n=>n.props['aria-label']==='Попередній перегляд відповідності колонок');
    const fileNode=nodes(ui.render()).find(n=>n.props.inputRef);
    const file={name:'synthetic.csv'};fileNode.props.inputRef.current={files:[file]};
    const result={sha256:'b'.repeat(64),columns:['Номер','Вартість'],row_count:8,rows:[['A','1']],
      fields:[{field:'ticket',label:'Номер звернення',required:true},{field:'total_cost',label:'Вартість звернення',required:false}],
      suggested_mapping:{ticket:'Номер',total_cost:'Вартість'},
      mapped:{mapping:{ticket:'Номер',total_cost:'Вартість'},rows:Array.from({length:7},(_,i)=>({ticket:'normalized-'+i,total_cost:'1.00'})),accepted:7,total:8,rejected:[{row:9,reason:'не число'}]}};
    button('Переглянути').props.onClick();await tick();
    assert.equal(ui.requests[2].url,'/api/connectors/preview/');
    assert.deepEqual(ui.requests[2].options.body.items,[['kind','csv'],['file',file],['dataset','orders']]);
    assert.ok(nodes(ui.render()).some(n=>n.props.role==='status'&&n.children.includes('Завантаження…')));
    ui.requests[2].resolve(response(result));await tick();
    assert.equal(mappingField('Номер звернення').props.value,'Номер','suggested mapping fills dynamic API field');
    assert.equal(mappingField('Номер звернення').props.required,true);
    assert.equal(mappingField('Вартість звернення').props.required,false);
    assert.equal(nodes(mappingSection()).filter(n=>n.type==='tr').length,6,'header + first five normalized rows');
    assert.ok(nodes(mappingSection()).some(n=>n.type==='li'&&n.children.includes('не число')));
    assert.ok(nodes(mappingSection()).some(n=>n.type==='p'&&n.children.includes(8)&&n.children.includes(7)&&n.children.includes(1)),'total/accepted/rejected counts');
    mappingField('Вартість звернення').props.onChange({target:{value:''}});
    assert.equal(nodes(mappingSection()).filter(n=>n.type==='tr').length,0,'selection invalidates old mapped result');
    button('Переглянути з мапінгом').props.onClick();await tick();
    assert.deepEqual(JSON.parse(ui.requests[3].options.body.items.find(([k])=>k==='mapping')[1]),{ticket:'Номер',total_cost:''});
    assert.equal(ui.requests[3].options.body.items.find(([k])=>k==='file')[1],file,'same source is read again');
    ui.requests[3].resolve(response({...result,mapped:{error:'Оберіть обов’язкову колонку'}}));await tick();
    assert.ok(nodes(mappingSection()).some(n=>n.props.role==='alert'&&n.children.includes('Оберіть обов’язкову колонку')),'HTTP 200 mapping error is visible');
    button('Переглянути з мапінгом').props.onClick();await tick();
    mappingField('Номер звернення').props.onChange({target:{value:'Вартість'}});
    ui.requests[4].resolve(response(result));await tick();
    assert.equal(nodes(mappingSection()).filter(n=>n.type==='tr').length,0,'late result after selection change is ignored');
    assert.equal(mappingField('Номер звернення').props.value,'Вартість');
    button('Переглянути з мапінгом').props.onClick();await tick();
    ui.requests[5].resolve(response({...result,mapped:{mapping:{ticket:'Вартість'},rows:[],accepted:0,total:8,rejected:[{row:2,reason:'порожнє поле'}]}}));await tick();
    assert.ok(nodes(mappingSection()).some(n=>n.children.includes('Немає прийнятих рядків')));
    field('Назва').props.onChange({target:{value:'Без збереження мапінгу'}});
    const createAgain=button('Підключити').props.onClick;
    const syncWhileCreating=button('Оновити').props.onClick;
    createAgain();await tick();
    assert.equal(ui.requests[6].url,'/api/connectors/create/');
    assert.ok(!ui.requests[6].options.body.items.some(([key])=>key==='mapping'),'raw connector creation never sends preview mapping');
    mappingField('Номер звернення').props.onChange({target:{value:'Номер'}});
    assert.equal(button('Підключити').props.disabled,true,'mapping change keeps pending mutation busy');
    button('Підключити').props.onClick();await tick();
    assert.equal(ui.requests.length,7,'mapping edit cannot issue a second create');
    fileNode.props.onChange();
    createAgain();syncWhileCreating();button('Переглянути').props.onClick();await tick();
    assert.equal(ui.requests.length,7,'source invalidation and old handlers cannot release the active mutation lock');
    ui.requests[6].resolve(response({id:8}));await tick();await tick();
    ui.requests[7].resolve(response(list));await tick();
    fileNode.props.inputRef.current={files:[file]};
    button('Переглянути').props.onClick();await tick();
    field('Дані').props.onChange({target:{value:'stock'}});
    ui.requests[8].resolve(response(result));await tick();
    assert.equal(mappingSection(),undefined,'dataset change invalidates inflight raw and mapped preview');
    button('Переглянути').props.onClick();await tick();
    fileNode.props.onChange();
    ui.requests[9].resolve(response(result));await tick();
    assert.equal(mappingSection(),undefined,'file selection invalidates inflight preview');
    field('Сервіс').props.onChange({target:{value:'google_sheets'}});
    field('Посилання на таблицю').props.onChange({target:{value:'https://docs.google.com/spreadsheets/d/synthetic/pub?output=csv'}});
    button('Переглянути').props.onClick();await tick();
    assert.equal(ui.requests[10].options.body.items.find(([k])=>k==='dataset')[1],'stock');
    field('Посилання на таблицю').props.onChange({target:{value:'https://docs.google.com/spreadsheets/d/changed/pub?output=csv'}});
    ui.requests[10].resolve(response(result));await tick();
    assert.equal(mappingSection(),undefined,'URL change invalidates inflight preview');
    button('Переглянути').props.onClick();await tick();ui.setScope('user:2');
    ui.requests[11].resolve(response(result));await tick();
    assert.equal(mappingSection(),undefined,'old-account mapping response is ignored');
    ui.unmount();
    const gone=harness(true);gone.mount();
    gone.requests[0].resolve(response({synced:[],failed:[]}));await tick();gone.requests[1].resolve(response(list));await tick();
    nodes(gone.render()).find(n=>n.props.inputRef).props.inputRef.current={files:[file]};
    nodes(gone.render()).find(n=>n.props.onClick&&n.children.includes('Переглянути')).props.onClick();await tick();gone.unmount();
    gone.requests[2].resolve(response(result));await tick();
    assert.ok(!nodes(gone.render()).some(n=>n.props['aria-label']==='Попередній перегляд відповідності колонок'),'unmounted mapping response is ignored');
  }
  // U8 regression: creating a Google Sheets connector has no file input (fileRef is null). The real
  // bosFileName from the compiled app must not throw there, and the list must be reloaded after create.
  {
    const bosFileName = app.match(/function bosFileName\(input\)\s*\{[\s\S]*?\n\}/)?.[0];
    assert.ok(bosFileName, 'compiled bosFileName');
    const extra = {FormData:class{constructor(){this.items=[];}append(k,v){this.items.push([k,v]);}}};
    vm.runInNewContext(bosFileName + ';globalThis.bosFileName=bosFileName;', extra);
    const sheets = harness(true, extra);sheets.mount();
    sheets.requests[0].resolve(response({synced:[],failed:[]}));await tick();
    sheets.requests[1].resolve(response(list));await tick();
    const form = sheets.state.findIndex(v=>v&&typeof v==='object'&&v.kind==='csv'&&'dataset' in v);
    sheets.state[form] = {kind:'google_sheets',name:'Продажі з таблиці',dataset:'orders',url:'https://docs.google.com/spreadsheets/d/synthetic/pub?output=csv'};
    sheets.state[form+1] = {sha256:'a'.repeat(64),columns:[],rows:[],total:0};
    const create = nodes(sheets.render()).find(node=>node.props?.onClick&&node.children.includes('Підключити'));
    assert.ok(create, 'create button after preview');
    create.props.onClick();await tick();
    assert.equal(sheets.requests[2].url, '/api/connectors/create/');
    sheets.requests[2].resolve(response({id:8}));await tick();await tick();
    assert.equal(sheets.requests[3]?.url, '/api/connectors/', 'list reloads after a Google Sheets create');
    sheets.requests[3].resolve(response(list));await tick();
    assert.ok(!nodes(sheets.render()).some(node=>node.props?.role==='alert'), 'no error after a successful create');
  }
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
