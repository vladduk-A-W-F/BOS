const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(require('node:path').join(__dirname, '..', 'assets/app.js'), 'utf8');
const component = app.match(/function Connections\([^)]*\)\s*\{[\s\S]*?\n}\s*(?=\/\/ BoS 4 first screen)/)?.[0];
assert.ok(component, 'compiled Connections component');
const formatters = app.match(/const erpDate = [\s\S]*?(?=const erpDateTime =)/)?.[0];
assert.ok(formatters, 'compiled date and exact money formatters');

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
  vm.createContext(context);vm.runInContext(formatters,context);vm.runInContext(component,context);
  return {requests,state,render(){hook=0;return context.Connections(extra.props||{});},mount(){this.render();cleanup=effect();},unmount(){cleanup();},setScope(value){scope=value;}};
}

(async()=>{
  // Persistence uses an explicitly rechecked and confirmed choice, and trusts only matching acknowledgement.
  for(const acknowledges of [true,false]){
    const ui=harness(true);ui.mount();ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    const button=label=>nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes(label));
    const fileNode=nodes(ui.render()).find(n=>n.props.inputRef);fileNode.props.inputRef.current={files:[{name:'persist.csv'}]};
    const chosen={code:'Номер',customer:'Клієнт'},result={sha256:'c'.repeat(64),columns:['Номер','Клієнт'],rows:[],row_count:1,
      fields:[{field:'code',label:'Номер',required:true},{field:'customer',label:'Клієнт',required:true}],suggested_mapping:chosen,
      mapped:{mapping:chosen,rows:[{code:'ZM-1',customer:'Synthetic'}],accepted:1,total:1,rejected:[]}};
    button('Переглянути').props.onClick();await tick();ui.requests[2].resolve(response(result));await tick();
    assert.ok(!nodes(ui.render()).some(n=>n.type==='input'&&n.props.type==='checkbox'),'automatic guess has no persistence confirmation');
    button('Перевірити відповідність').props.onClick();await tick();ui.requests[3].resolve(response(result));await tick();
    assert.ok(!nodes(ui.render()).some(n=>n.type==='input'&&n.props.type==='checkbox'),'checked preview needs only the explicit create button');
    assert.equal(ui.requests.length,4,'checking does not create or save automatically');
    nodes(ui.render()).find(n=>n.props.placeholder==='Замовлення з магазину').props.onChange({target:{value:'Explicit choice'}});
    const create=button('Підключити з цією відповідністю').props.onClick;
    ui.setScope('user:2');create();await tick();assert.equal(ui.requests.length,4,'retained create handler cannot POST after account change');
    ui.setScope('user:1');create();await tick();
    assert.deepEqual(JSON.parse(ui.requests[4].options.body.items.find(([k])=>k==='mapping')[1]),chosen);
    ui.requests[4].resolve(response(acknowledges?{id:8,mapping:chosen}:{id:8}));await tick();await tick();
    ui.requests[5].reject(Error('List refresh failed'));await tick();
    assert.ok(nodes(ui.render()).some(n=>n.props.role==='status'&&n.children.some(c=>typeof c==='string'&&c.includes(acknowledges?'відповідність збережено':'сервер не підтвердив'))));
    assert.ok(nodes(ui.render()).some(n=>n.props.role==='alert'&&n.children.includes('List refresh failed')),'refresh failure stays separate from successful POST');
    assert.equal(ui.requests.filter(r=>r.url==='/api/connectors/create/').length,1,'no automatic retry after success/unsupported persistence');
    create();await tick();assert.equal(ui.requests.length,6,'completed create consumes its preview intent; retained handler cannot create a duplicate');
  }
  for(const boundary of ['account','unmount','role']){
    let write=true;const ui=harness(true,{props:{targetId:7},bosCan:key=>key==='write'&&write});ui.mount();
    ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    ui.requests[2].resolve(response({...list.connectors[0],columns:['Номер'],rows:[],fields:[{field:'code',label:'Номер',required:true}],mapping:{code:'Номер'}}));await tick();
    const save=nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes('Зберегти')).props.onClick;
    if(boundary==='account')ui.setScope('user:2');else if(boundary==='unmount')ui.unmount();else write=false;
    save();await tick();assert.equal(ui.requests.length,3,'retained save handler cannot POST after '+boundary);
    if(boundary==='account')assert.ok(!nodes(ui.render()).some(n=>n.props['aria-label']==='Джерело: Продажі'),'previous account source editor is hidden');
  }
  for(const boundary of ['edit','close']){
    const ui=harness(true,{props:{targetId:7}});ui.mount();ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    ui.requests[2].resolve(response({...list.connectors[0],columns:['Номер'],rows:[['old value']],fields:[{field:'code',label:'Номер',required:true}],mapping:{code:'Номер'}}));await tick();
    const save=nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes('Зберегти')).props.onClick;
    if(boundary==='edit')nodes(ui.render()).find(n=>n.props['aria-label']==='Джерело: Номер').props.onChange({target:{value:''}});
    else nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes('Закрити')).props.onClick();
    save();await tick();assert.equal(ui.requests.length,3,'retained save confirmation cannot POST after '+boundary);
  }
  {
    const ui=harness(true,{props:{targetId:7}});ui.mount();ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    const saved={...list.connectors[0],columns:['Номер'],fields:[{field:'code',label:'Номер',required:true}],mapping:{code:'Номер'},mapped_summary:{accepted:1,total:1,rejected:0}};
    ui.requests[2].resolve(response({...saved,rows:[['ZM-1']]}));await tick();
    const save=nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes('Зберегти')).props.onClick;
    save();await tick();ui.requests[3].resolve(response(saved));await tick();await tick();
    ui.requests[4].resolve(response({...saved,rows:[['ZM-1']]}));await tick();await tick();ui.requests[5].resolve(response(list));await tick();
    assert.ok(!nodes(ui.render()).some(n=>n.type==='input'&&n.props.type==='checkbox'),'save needs one explicit button, no extra checkbox');
    save();await tick();assert.equal(ui.requests.length,6,'completed save consumes its confirmation; retained handler cannot write again');
  }
  {
    const ui=harness(true,{props:{targetId:7}});ui.mount();ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    assert.equal(ui.requests[2].url,'/api/connectors/7/rows/','navigation opens exact connector');
    const saved={...list.connectors[0],columns:['Номер','Клієнт'],rows:[['ZM-1','Synthetic']],mapping:{code:'Номер',customer:'Клієнт'},
      fields:[{field:'code',label:'Номер',required:true},{field:'customer',label:'Клієнт',required:true}],mapped_summary:{accepted:1,total:1,rejected:0}};
    ui.requests[2].resolve(response(saved));await tick();
    const button=label=>nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes(label));
    const select=()=>nodes(ui.render()).find(n=>n.props['aria-label']==='Джерело: Номер');
    assert.equal(button('Зберегти').props.disabled,false,'explicit save button is the confirmation');
    select().props.onChange({target:{value:'Клієнт'}});
    assert.equal(ui.requests.length,3,'editing an existing mapping never autosaves');
    button('Зберегти').props.onClick();await tick();
    assert.equal(ui.requests[3].url,'/api/connectors/7/mapping/');
    assert.deepEqual(JSON.parse(ui.requests[3].options.body.items[0][1]),{code:'Клієнт',customer:'Клієнт'});
    button('Зберегти').props.onClick();select().props.onChange({target:{value:'Номер'}});await tick();
    assert.equal(ui.requests.length,4,'pending mutation cannot be duplicated or edited');
    ui.requests[3].resolve(response({error:'Колонка вже використана'},false));await tick();
    assert.equal(select().props.value,'Клієнт','422 keeps the selected choice');
    assert.ok(!nodes(ui.render()).some(n=>n.props.role==='status'&&n.children.includes('Відповідність джерела збережено.')));
    select().props.onChange({target:{value:'Номер'}});button('Зберегти').props.onClick();await tick();
    ui.requests[4].resolve(response({...saved,columns:['Клієнт','Номер'],rows:undefined}));await tick();await tick();
    assert.equal(ui.requests[5].url,'/api/connectors/7/rows/');
    assert.ok(!nodes(ui.render()).some(n=>n.type==='td'&&n.children.includes('ZM-1')),'new headers never label old raw rows after save');
    ui.requests[5].reject(Error('Rows refresh after save failed'));await tick();await tick();ui.requests[6].reject(Error('Refresh after save failed'));await tick();
    assert.ok(nodes(ui.render()).some(n=>n.props.role==='status'&&n.children.includes('Відповідність джерела збережено.')));
    assert.ok(nodes(ui.render()).some(n=>n.props.role==='alert'&&n.children.includes('Refresh after save failed')));
    assert.equal(ui.requests.filter(r=>r.url.endsWith('/mapping/')).length,2,'one failed choice and one successful choice, no retry');
    button('Зберегти').props.onClick();await tick();ui.setScope('user:2');ui.requests[7].resolve(response(saved));await tick();
    assert.equal(ui.requests.length,8,'old-account save response cannot reload or report success');
    ui.unmount();
    const observer=harness(false,{props:{targetId:7}});observer.mount();observer.requests[0].resolve(response(list));await tick();
    assert.equal(observer.requests.length,1,'observer opens metadata without rows GET');
    assert.ok(!nodes(observer.render()).some(n=>n.props.onClick&&n.children.includes('Зберегти')));
  }
  {
    const ui=harness(true);ui.mount();ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();ui.requests[1].resolve(response(list));await tick();
    const button=label=>nodes(ui.render()).find(n=>n.props.onClick&&n.children.includes(label));
    const section=()=>nodes(ui.render()).find(n=>n.props['aria-label']==='Попередній перегляд відповідності колонок');
    nodes(ui.render()).find(n=>n.props.inputRef).props.inputRef.current={files:[{name:'synthetic-ux.csv'}]};
    button('Переглянути').props.onClick();await tick();
    const fields=[{field:'amount',label:'Сума'},{field:'currency',label:'Валюта'},{field:'due_date',label:'Строк'}];
    const rows=[{amount:'999999999999.99',currency:'USD',due_date:'2026-10-05'},
      {amount:'0.00',currency:'UAH',due_date:null},{amount:'-1234.50',currency:'EUR',due_date:''},
      {amount:null,currency:'UAH',due_date:'2026-10-06'},{amount:'',currency:'USD',due_date:'2026-10-07'}];
    const mapping={amount:'Сума',currency:'Валюта',due_date:'Строк'};
    ui.requests[2].resolve(response({columns:['Сума','Валюта','Строк'],rows:[],row_count:105,fields,suggested_mapping:mapping,
      mapped:{mapping,rows,accepted:5,total:105,rejected:Array.from({length:50},(_,i)=>({row:i+7,reason:'помилка '+i}))}}));await tick();
    assert.ok(button('Перевірити відповідність'),'plain Ukrainian action');
    assert.ok(nodes(section()).some(n=>n.children.includes('Як BoS прочитає перші 5 рядків')));
    assert.ok(nodes(section()).some(n=>n.children.some(c=>typeof c==='string'&&c.startsWith('Після перевірки натисніть'))));
    const cells=nodes(section()).filter(n=>n.type==='td').map(n=>n.children[0]);
    assert.deepEqual(cells,['999\u00a0999\u00a0999\u00a0999,99\u00a0USD','USD','05.10.2026',
      '0\u00a0грн','UAH','—','-1\u00a0234,50\u00a0EUR','EUR','—','—','UAH','06.10.2026','—','USD','07.10.2026']);
    const rejected=nodes(section()).filter(n=>n.type==='li');
    assert.equal(rejected.length,5,'only first five reasons');
    assert.ok(rejected.every(n=>n.props.style.margin==='8px 0'),'reasons have spacing');
    assert.ok(nodes(section()).some(n=>n.type==='p'&&n.children.includes('ще ')&&n.children.includes(95)),'remaining count uses total minus accepted, not capped reason list');
    nodes(ui.render()).find(n=>n.props.value==='orders'&&n.props.onChange).props.onChange({target:{value:'calls'}});
    button('Переглянути').props.onClick();await tick();
    ui.requests[3].resolve(response({columns:['Час'],rows:[],row_count:2,fields:[{field:'started_at',label:'Час дзвінка',required:true}],
      suggested_mapping:{started_at:'Час'},mapped:{mapping:{started_at:'Час'},rows:[{started_at:'2026-10-05T12:34:56'},{started_at:null}],accepted:2,total:2,rejected:[]}}));await tick();
    assert.deepEqual(nodes(section()).filter(n=>n.type==='td').map(n=>n.children[0]),['05.10.2026 12:34:56','—'],'datetime retains seconds; empty stays empty');
  }
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
    button('Перевірити відповідність').props.onClick();await tick();
    assert.deepEqual(JSON.parse(ui.requests[3].options.body.items.find(([k])=>k==='mapping')[1]),{ticket:'Номер',total_cost:''});
    assert.equal(ui.requests[3].options.body.items.find(([k])=>k==='file')[1],file,'same source is read again');
    ui.requests[3].resolve(response({...result,mapped:{error:'Оберіть обов’язкову колонку'}}));await tick();
    assert.ok(nodes(mappingSection()).some(n=>n.props.role==='alert'&&n.children.includes('Оберіть обов’язкову колонку')),'HTTP 200 mapping error is visible');
    button('Перевірити відповідність').props.onClick();await tick();
    mappingField('Номер звернення').props.onChange({target:{value:'Вартість'}});
    ui.requests[4].resolve(response(result));await tick();
    assert.equal(nodes(mappingSection()).filter(n=>n.type==='tr').length,0,'late result after selection change is ignored');
    assert.equal(mappingField('Номер звернення').props.value,'Вартість');
    button('Перевірити відповідність').props.onClick();await tick();
    ui.requests[5].resolve(response({...result,mapped:{mapping:{ticket:'Вартість'},rows:[],accepted:0,total:8,rejected:[{row:2,reason:'порожнє поле'}]}}));await tick();
    assert.ok(nodes(mappingSection()).some(n=>n.children.includes('Немає прийнятих рядків')));
    const staleCheckedCreate=button('Підключити з цією відповідністю').props.onClick;
    mappingField('Номер звернення').props.onChange({target:{value:'Вартість'}});
    staleCheckedCreate();await tick();assert.equal(ui.requests.length,6,'edit invalidates retained checked create without sending a POST');
    field('Назва').props.onChange({target:{value:'Без збереження мапінгу'}});
    assert.ok(button('Підключити без відповідності'),'edited mapping explicitly labels raw creation');
    assert.equal(button('Підключити'),undefined,'edited mapping never offers an ambiguous create label');
    const createAgain=button('Підключити без відповідності').props.onClick;
    const syncWhileCreating=button('Оновити').props.onClick;
    createAgain();await tick();
    assert.equal(ui.requests[6].url,'/api/connectors/create/');
    assert.ok(!ui.requests[6].options.body.items.some(([key])=>key==='mapping'),'raw connector creation never sends preview mapping');
    mappingField('Номер звернення').props.onChange({target:{value:'Номер'}});
    assert.equal(button('Підключити без відповідності').props.disabled,true,'mapping change keeps pending mutation busy');
    button('Підключити без відповідності').props.onClick();await tick();
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
    assert.ok(create, 'old backend without fields keeps the ordinary create label');
    assert.ok(!nodes(sheets.render()).some(node=>node.children.includes('Підключити без відповідності')));
    create.props.onClick();await tick();
    assert.equal(sheets.requests[2].url, '/api/connectors/create/');
    assert.ok(!sheets.requests[2].options.body.items.some(([key])=>key==='mapping'),'old backend raw flow sends no mapping');
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

// MCP: the CEO sees whether AI-client access is on and which keys exist; the server sends no block to other roles.
(async()=>{
  const words=tree=>nodes(tree).flatMap(n=>(n.children||[]).flat(Infinity)).filter(c=>typeof c==='string').join(' ');
  const open=async mcp=>{
    const ui=harness(true,{location:{origin:'http://127.0.0.1:8030'}});ui.mount();
    ui.requests[0].resolve(response({synced:[],failed:[]}));await tick();
    ui.requests[1].resolve(response(mcp===undefined?list:{...list,mcp}));await tick();
    return nodes(ui.render()).find(n=>n.props['aria-label']==='ІІ-помічники (MCP)');
  };
  const on=await open({enabled:true,path:'/mcp/',keys:[{id:'ab12cd34',label:'Claude на ноутбуці',user:'owner',created_at:'2026-10-09T02:00:00+00:00'}]});
  assert.ok(on,'CEO sees the MCP card');
  for(const part of ['Увімкнено','http://127.0.0.1:8030/mcp/','Claude на ноутбуці','owner'])assert.ok(words(on).includes(part),part);
  assert.ok(!JSON.stringify(on).includes('sha256'),'no key material on screen');
  const off=await open({enabled:false,path:'/mcp/',keys:[]});
  assert.ok(words(off).includes('Вимкнено')&&words(off).includes('mcp_access create'),'disabled card says how a key is issued on the server');
  assert.equal(await open(undefined),undefined,'no card without the server block');
  console.log('MCP card in «Підключення»: CEO state, key labels, no key material: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
