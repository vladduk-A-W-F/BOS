/* UI-COLUMN-CONTENT-01: bounded renderer checks, not a browser or product suite. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=path.resolve(__dirname,'../..'),html=fs.readFileSync(path.join(root,'frontend/boss_app_source.html'),'utf8');
const babel=require(path.join(root,'assets/babel.js'));
const fragment=html.slice(html.indexOf('// CORE_MODULE_VIEWS_BEGIN'),html.indexOf('// CORE_MODULE_VIEWS_END'));
const actionPolicy=html.slice(html.indexOf('function bosCanAction('),html.indexOf('function bosCanView('));
const actions=html.slice(html.indexOf('const ERP_ACTIONS='),html.indexOf('\nfunction ERPTable'));
const React={createElement:(type,props,...children)=>({type,props:props||{},children})};
const c={console,React,Intl,Number,BigInt,Math,Map,Set,Promise,AbortController,JSON,URLSearchParams,
 useState(value){const current=typeof value==='function'?value():value;return [current,()=>{}];},useRef:value=>({current:value}),useEffect:()=>{},
 bosRole:()=> 'ceo',bosCan:()=>true,window:{BOS_RUNTIME:{employee_id:1}},
 Button:'Button',Select:'Select',Input:'Input',Card:'Card',ERPTable:'ERPTable',NetworkMap:'NetworkMap',
 ERP_LABELS:{},erpDate:value=>value||'date fallback',
 networkQuery:()=>'',
};
vm.createContext(c);vm.runInContext(babel.transform(actionPolicy+'\n'+actions+'\n'+fragment,{presets:['react']}).code,c);
function text(node){return node==null?'':typeof node==='object'?(node.children||[]).flat(Infinity).map(text).join(''):String(node);}
function nodes(node){return node==null||typeof node!=='object'?[]:[node,...(node.children||[]).flat(Infinity).flatMap(nodes)];}
function count(value,needle){return value.split(needle).length-1;}
let checks=0;function check(label,fn){fn();checks++;console.log('PASS '+label);}

check('missing cells use typed Ukrainian fallbacks while numeric zero remains a value',()=>{
 assert.equal(c.moduleCell({key:'value',type:'text'},{value:null},'UAH'),'Не вказано');
 assert.equal(c.moduleCell({key:'value',type:'text'},{value:'   '},'UAH'),'Не вказано');
 assert.equal(c.moduleCell({key:'due_date',type:'date'},{due_date:undefined},'UAH'),'Не встановлено');
 assert.equal(c.moduleCell({key:'created_at',type:'datetime'},{created_at:'\t'},'UAH'),'Не встановлено');
 assert.equal(c.moduleCell({key:'quantity',type:'quantity'},{quantity:0},'UAH'),'0');
 assert.equal(text(c.moduleCell({key:'amount',type:'money'},{amount:'0.00',currency:'UAH'},'UAH')),'0,00\u00a0грн');
 assert.equal(c.moduleCell({key:'status',type:'status'},{status:'future_state'},'UAH'),'future_state');
});

check('flow cards retain same-text semantic facts with their labels',()=>{
 const sourceCatalog=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/module_catalog','ceo.json'),'utf8'));
 const model={...sourceCatalog.models.find(candidate=>candidate.id==='orders'),default_view:'flow',views:['flow']};
 assert.equal(model.source.rows,'rows.orders');
 const network={as_of:'2026-09-26',capabilities:{write:true,finance:true,export:false},locations:[],rows:{orders:[
  {id:1,code:'SO-001',status:'open',item_name:'SO-001',customer_name:'SO-001',location_name:'Київ'},
  {id:2,code:'SO-002',status:'open',item_name:'Деталь A',customer_name:'Деталь A',location_name:'Львів'},
  {id:3,code:'SO-003',status:'open',item_name:'Деталь B',customer_name:'Клієнт B',location_name:'Одеса'},
  {id:4,code:'SO-004',status:'open',item_name:'SO-004 ',customer_name:'SO-004',location_name:'Дніпро'},
 ]}};
 const catalog={permissions:{write:true,finance:true,export:false},views:[{id:'flow',name:'Потік'}],models:[model],actions:[]};
 const tree=c.CoreModuleSurface({catalog,network,table:'orders',view:'flow',search:'',branch:'',point:'',currency:'UAH',onTable:()=>{},onView:()=>{},onSearch:()=>{},onPoint:()=>{},onSelect:()=>{},onAction:()=>{}});
 const cards=nodes(tree).filter(node=>node.props.className==='module-record');
 assert.equal(cards.length,4);
 assert.equal(count(text(cards[0]),'SO-001'),3);
 assert(text(cards[0]).includes('Номенклатура: '));
 assert(text(cards[0]).includes('Клієнт: '));
 assert.equal(count(text(cards[1]),'Деталь A'),2);
 assert(text(cards[2]).includes('Деталь B'));
 assert(text(cards[2]).includes('Клієнт B'));
 assert.equal(count(text(cards[3]),'SO-004'),3,'distinct source fields remain visible even when their text is similar');
});

check('facts omit only the semantic heading field',()=>{
 const model={label_field:'code',columns:[{key:'code',label:'Замовлення',type:'text'},{key:'item_name',label:'Номенклатура',type:'text'},{key:'customer_name',label:'Клієнт',type:'text'}]};
 const tree=c.ModuleRecordFacts({model,row:{code:'SO-001',item_name:'SO-001',customer_name:'SO-001'},currency:'UAH'});
 assert(!text(tree).includes('Замовлення'));
 assert(text(tree).includes('Номенклатура'));
 assert(text(tree).includes('Клієнт'));
});

check('server and all role fixtures use the current column labels',()=>{
 const registry=fs.readFileSync(path.join(root,'erp/module_registry.py'),'utf8');
 for(const label of ['На складі','Доступно для операцій','Ще прийняти','Рядки до виконання'])assert(registry.includes(label));
 for(const role of ['ceo','manager','observer']){
  const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/module_catalog',role+'.json'),'utf8'));
  const labels=catalog.models.flatMap(model=>model.columns.map(column=>column.label));
  for(const label of ['На складі','Доступно для операцій','Ще прийняти','Рядки до виконання'])assert(labels.includes(label),role+' '+label);
 }
});

console.log(JSON.stringify({result:'PASS',checks,scope:'bounded module-column renderer and descriptor checks; no browser, build, or product suite'},null,2));
