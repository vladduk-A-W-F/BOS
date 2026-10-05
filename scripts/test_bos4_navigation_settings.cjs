const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8');
function part(start,end){const a=app.indexOf(start),b=app.indexOf(end,a);assert(a>=0&&b>a,start);return app.slice(a,b);}
const React={Fragment:'fragment',createElement:(type,props,...children)=>({type,props:{...props,children}})};
function nodes(value){return Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children||[])]:[];}
function words(value){return Array.isArray(value)?value.map(words).join(''):value&&typeof value==='object'?words(value.props?.children||[]):value==null?'':String(value);}
function harness(extra={}){
 const state=[];let slot=0;
 const ctx={React,T:{},ICONS:{},BosMark(){},useEffect(){},useState(initial){const i=slot++;if(!(i in state))state[i]=initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(initial){const i=slot++;if(!(i in state))state[i]={current:initial};return state[i];},...extra};
 vm.createContext(ctx);return {ctx,render:fn=>{slot=0;return fn();}};
}
const navCode=part('const NAV =','// Existing preference IDs remain compatible;');
const navComponent=part('function NavBar(','// ═══════════════════════════════════════════════════════════════════════════\n//  EXECUTIVE DASHBOARD');
for(const role of ['ceo','manager','observer']){
 let nav={section:'monitor',sub:null},tree,effectSlot=0;const effects=[],pendingEffects=[],timers=new Map(),frames=new Map(),dom=new Map();let nextId=0;
 const doc={activeElement:null,addEventListener(){},removeEventListener(){},querySelector:selector=>selector==='main[data-bos-main]'?dom.get('main'):null,getElementById:id=>dom.get(id)};
 const cluster=()=>nodes(tree).find(n=>n.props?.className==='bos-nav-cluster');
 const element=id=>{if(!dom.has(id))dom.set(id,{id,isConnected:true,disabled:false,getClientRects:()=>[{}],contains:other=>other?.id===id||(id==='cluster'&&other?.id?.startsWith('trigger-')),focus(){doc.activeElement=this;cluster()?.props.onBlur({relatedTarget:null});}});return dom.get(id);};
 element('main');
 const win={setTimeout:run=>{timers.set(++nextId,run);return nextId;},clearTimeout:id=>timers.delete(id),requestAnimationFrame:run=>{frames.set(++nextId,run);return nextId;},cancelAnimationFrame:id=>frames.delete(id),matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}}),addEventListener(){},removeEventListener(){}};
 const h=harness({document:doc,window:win,getComputedStyle:()=>({visibility:'visible'}),bosRole:()=>role,bosCan:()=>role==='ceo',bosHttpScope:()=>role,bosCanView:()=>true,useEffect(run,deps){const i=effectSlot++;if(!effects[i]||deps.some((v,j)=>v!==effects[i][j])){effects[i]=deps;pendingEffects.push(run);}}});
 vm.runInContext(part('function bosNavigation(','function useLocalState(')+navCode+navComponent,h.ctx);
 const render=()=>{effectSlot=0;tree=h.render(()=>h.ctx.NavBar({nav,setNav:next=>nav=next,settings:{profile:{}},tasks:[]}));for(const node of nodes(tree)){if(typeof node.props?.ref==='function')node.props.ref(element('trigger-'+node.props['aria-controls']?.replace('bos-nav-disclosure-','')));else if(node.props?.ref)node.props.ref.current=element(node.type==='select'?'mobile':'cluster');if(node.props?.id)element(node.props.id);}for(const run of pendingEffects.splice(0))run();return tree;};
 const button=label=>nodes(tree).find(n=>n.type==='button'&&words(n)===label);
 const flush=()=>{for(const run of [...timers.values()]){timers.clear();run();}for(const run of [...frames.values()]){frames.clear();run();}render();};
 render();render();button('Команда').props.onClick();render();flush();
 assert.equal(nav.sub,'tasks');assert.equal(doc.activeElement.id,'trigger-hr','team transition keeps focus on its trigger');assert.equal(button('Команда').props['aria-expanded'],true,'submenu survives timer, blur and RAF');
 button('Співробітники').props.onClick();render();flush();assert.equal(doc.activeElement.id,'main','ordinary submenu leaf focuses content');assert.equal(button('Команда').props['aria-expanded'],false);
 button('Команда').props.onClick();render();flush();assert.equal(button('Команда').props['aria-expanded'],true,'return from employees retains disclosure after focus flush');
 button('Команда').props.onClick();render();nodes(tree).find(n=>n.type==='select').props.onChange({target:{value:'monitor:'}});render();flush();nodes(tree).find(n=>n.type==='select').props.onChange({target:{value:'hr:'}});render();flush();assert.equal(nav.sub,'tasks');assert.equal(doc.activeElement.id,'main','mobile team transition retains ordinary content focus');
}
console.log('U2 focus finding: compiled timer → blur → RAF, team disclosure and ordinary/mobile focus: PASS');
if(!process.argv.includes('--focus-only')){
for(const role of ['ceo','manager','observer']){
 let nav={section:'monitor',sub:null};let writes=0;
 const h=harness({bosRole:()=>role,bosCan:()=>role==='ceo',bosHttpScope:()=>role,bosCanView:(section,sub)=>!(role!=='ceo'&&section==='finance'&&sub==='salaries'),window:{setTimeout:()=>1,clearTimeout(){},cancelAnimationFrame(){},matchMedia:()=>({matches:false})}});
 vm.runInContext(part('function bosNavigation(','function useLocalState(')+navCode+navComponent,h.ctx);
 const render=()=>h.render(()=>h.ctx.NavBar({nav,setNav:next=>{nav=next;writes++;},settings:{profile:{}},tasks:[]}));
 const team=tree=>nodes(tree).find(n=>n.type==='button'&&words(n)==='Команда');
 let tree=render();const stale=team(tree);stale.props.onClick();
 assert.equal(nav.section,'hr');assert.equal(nav.sub,'tasks','first team click routes immediately');
 tree=render();assert.equal(team(tree).props['aria-expanded'],true,'submenu stays open');
 const employees=nodes(tree).find(n=>n.type==='button'&&words(n)==='Співробітники');
 assert.ok(employees,'employee submenu preserved for every role');employees.props.onClick();
 assert.equal(nav.sub,'employees');tree=render();team(tree).props.onClick();
 assert.equal(nav.sub,'tasks','team resets employee selection to tasks');
 tree=render();team(tree).props.onClick();tree=render();assert.equal(team(tree).props['aria-expanded'],false,'current team click collapses submenu');
 const before=writes;stale.props.onClick();assert.equal(writes,before,'old render cannot navigate');
 const mobile=nodes(tree).find(n=>n.type==='select');mobile.props.onChange({target:{value:'hr:'}});assert.equal(nav.sub,'tasks','mobile team routes to tasks');
 const salaries=vm.runInContext("bosNavigation().find(n=>n.id==='finance').subs.some(n=>n.id==='salaries')",h.ctx);
 assert.equal(salaries,role==='ceo','private role boundary preserved');
}
const initial={name:'Тест',description:'Опис',industry:'Торгівля',process_owner:'Олена',timezone:'Europe/Kyiv',ai_timeout:30,ai_max_steps:5,ai_hourly_limit:20};
const saved=[];let effect;
const org=harness({Card(){},Input(){},Button(){},useEffect:run=>{effect=run;},opFetch:async(route,body)=>{if(route==='status/')return {organization:{...initial}};saved.push({route,body});return body;}});
vm.runInContext(part('function OrganizationSettings(','function AIChat('),org.ctx);
(async()=>{
 org.render(()=>org.ctx.OrganizationSettings());effect();await new Promise(resolve=>setImmediate(resolve));
 let tree=org.render(()=>org.ctx.OrganizationSettings());
 const disclosure=nodes(tree).find(n=>n.type==='details');assert.ok(disclosure);assert.equal(disclosure.props.open,undefined,'native disclosure closed by default');
 assert.equal(words(nodes(disclosure).find(n=>n.type==='summary')),'Додатково');
 const numeric=nodes(disclosure).filter(n=>n.type===org.ctx.Input);assert.deepEqual(numeric.map(n=>n.props.value),[30,5,20]);
 assert.equal(nodes(tree).filter(n=>n.type===org.ctx.Input).length,8,'all original fields retained');
 numeric[0].props.onChange({target:{value:'45'}});tree=org.render(()=>org.ctx.OrganizationSettings());
 await nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(saved.length,1);assert.equal(saved[0].route,'settings/');assert.deepEqual(JSON.parse(JSON.stringify(saved[0].body)),{...initial,ai_timeout:45},'same form saves all fields');
 const settings=harness({SegmentedControl(){},Card(){},Input(){},Button(){},Select(){},cardS:()=>({}),bosRole:()=> 'observer',bosCan:()=>false});
 vm.runInContext(part('const ICONS =','// NavBar —'),settings.ctx);
 vm.runInContext(part('function Settings({','// InfoPage'),settings.ctx);
 tree=settings.render(()=>settings.ctx.Settings({settings:{profile:{},notifications:{},dataSources:{}},employees:[]}));
 const options=nodes(tree).find(n=>n.type===settings.ctx.SegmentedControl).props.options;
 assert.equal(options.length,8);for(const option of options){assert.equal(nodes(option.label).filter(n=>n.type==='svg').length,1,'settings label reuses SVG');assert.ok(words(option.label).length);}
 console.log('U2 compiled navigation, roles, stale handlers, mobile route, native disclosure, save payload and SVG settings: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
}
