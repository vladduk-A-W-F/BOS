/* Additive Node/source proof. No application, HTTP, database, DOM or browser. */
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
const sourcePath=process.argv[2],expectedSha=process.argv[3],output=process.argv[4];
if(!sourcePath||!expectedSha||!output)throw Error('Usage: node check_assistant_entry.cjs SOURCE EXPECTED_SHA OUTPUT');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const source=fs.readFileSync(sourcePath,'utf8');
assert.equal(sha(source),expectedSha,'Source must be the root-frozen candidate');
const root=path.dirname(path.dirname(sourcePath));
const Babel=require(path.join(root,'assets/babel.js'));
const extract=(start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a,`Missing exact source boundary ${start}`);return source.slice(a,b);};
const importerLines=source.split('\n').filter(line=>/^\s*async function importAction\(\)/.test(line));assert.equal(importerLines.length,1);
const importer=importerLines[0];
const helpers=source.match(/\/\/ B03_HELPERS_BEGIN\n([\s\S]*?)\/\/ B03_HELPERS_END/)[1];
const roles=extract('function bosRole(){','function bosCanView(');
const oldDefinitions=extract('const ERP_ACTIONS={','function ERPTable(');
const q=extract('function purchaseRemaining(','const IMPORT_ENTITIES=');
const dialogs=extract('function CorrectionActionDialog(','function B03RecordBody(');
const dialogJS=Babel.transform(dialogs,{presets:['react'],sourceType:'script',filename:'actual-extracted-dialogs.jsx'}).code;
const oldFiles=['/workspace/scratch/c7b51e996a9f/tmp/B03_ASSISTANT_ENTRY_RED.json','/workspace/scratch/c7b51e996a9f/tmp/B03_ASSISTANT_ENTRY_GREEN.json'];
const oldEvidence=oldFiles.map(file=>({file,sha256:sha(fs.readFileSync(file))}));
const OP='a0000000-0000-4000-8000-000000000001',REC='b0000000-0000-4000-8000-000000000002';
const common={operation_id:OP,code:'КР-NODE-1',business_date:'2026-09-12',reason:'Погоджено джерельний результат'};
const base={
 cancel_remaining:{purchase_id:19,quantity:'1.000'},
 return_supplier:{receipt_id:23,quantity:'1.000'},
 return_from_shipment:{shipment_id:31,quantity:'1.000',location_id:4},
 credit_invoice:{invoice_id:5,basis:'commercial',source_document_id:4,allocations:[{invoice_line_index:0,amount:'1.00'}]},
 reverse_credit:{credit_id:20},
 confirm_supplier_claim:{claim_id:21,amount:'1.31',currency:'EUR',source_document_id:4},
};
const examples=Object.entries(base).map(([action,fields])=>({name:action,action,value:{action:'erp_'+action,...common,...fields}}));
examples.push({name:'sales_cancel',action:'cancel_remaining',value:{action:'erp_cancel_remaining',...common,line_id:27,quantity:'0.001'}});
examples.push({name:'return_credit',action:'credit_invoice',value:{action:'erp_credit_invoice',...common,invoice_id:5,basis:'return',allocations:[{invoice_line_index:0,return_id:43,quantity:'0.001'}]}});
const clone=x=>JSON.parse(JSON.stringify(x)),checks=[],trace={snapshot_reads:0,network_calls:0,effects_invoked:0,random_uuid_calls:0};
let captured={},refs=[],cells=[];
const data={as_of:'2026-09-12',items:[],lots:[],locations:[],orders:[],lines:[],jobs:[],purchases:[],invoices:[],invoice_adjustments:[],supplier_claims:[],goods_returns:[],source_movements:[],documents:[],events:[],reservations:[],partners:[],employees:[]};
const c={JSON,raw:'',window:{BOS_RUNTIME:{role:'ceo',capabilities:{write:true}},crypto:{randomUUID:()=>{trace.random_uuid_calls++;throw Error('UUID generation is outside this initial-render proof');}}},
 setError:value=>captured.error=value,setErpAction:value=>captured.entries.push(value),setPayload:value=>captured.payload=value,setTask:value=>captured.task=value,
 erpFetch:async route=>{assert.equal(route,'snapshot/');trace.snapshot_reads++;captured.reads++;return data;},
 fetch:()=>{trace.network_calls++;throw Error('Network prohibited in Node/source regression');},
 useRef:initial=>{const ref={current:initial};refs.push(ref);return ref;},
 useState:initial=>{const cell={value:typeof initial==='function'?initial():initial};cells.push(cell);return [cell.value,value=>{cell.value=typeof value==='function'?value(cell.value):value;}];},
 useEffect:()=>{},
 React:{Fragment:'fragment',createElement:(type,props,...children)=>({type,props:props||{},children})},
 erpDate:value=>String(value||''),
};
for(const name of new Set([...dialogs.matchAll(/<\/?([A-Z][A-Za-z0-9_]*)\b/g)].map(m=>m[1]))){if(!['CorrectionActionDialog'].includes(name))c[name]=function UIElementPlaceholder(){};}
c.ERPActionDialog=function ERPActionDialog(){};
vm.createContext(c);vm.runInContext(roles+'\n'+q+'\n'+helpers+'\n'+oldDefinitions+'\n'+importer+'\n'+dialogJS+'\nthis.legacyKeys=Object.keys(ERP_ACTIONS);this.newKeys=Object.keys(B03_ACTIONS);',c);
const run=async(name,fn)=>{try{const observed=await fn();checks.push({name,passed:true,...(observed?{observed}:{} )});}catch(e){checks.push({name,passed:false,error:e.message});}};
async function call(value,{role='ceo',write=true,raw}={}){
 captured={entries:[],error:null,reads:0};c.window.BOS_RUNTIME={role,capabilities:{write}};c.raw=raw===undefined?JSON.stringify(value):raw;await c.importAction();return captured;
}
async function accepted(example,options){const r=await call(example.value,options);assert.equal(r.error,'');assert.equal(r.entries.length,1);assert.equal(r.reads,1);assert.equal(r.entries[0].type,example.action);assert.equal(r.entries[0].preset.operation_id,OP);return r.entries[0].preset;}
async function denied(value,options){const r=await call(value,options);assert.equal(r.entries.length,0);assert.equal(r.reads,0);assert.equal(typeof r.error,'string');assert(r.error.length>0);return {error:r.error};}
function visit(tree,predicate){const found=[];function walk(x){if(!x||typeof x!=='object')return;if(Array.isArray(x)){x.forEach(walk);return;}if(predicate(x))found.push(x);walk(x.children);}walk(tree);return found;}
function render(action,preset,recovery=null){refs=[];cells=[];c.window.BOS_RUNTIME={role:'ceo',capabilities:{write:true}};const tree=c.CorrectionActionDialog({action,preset,recovery,data,onClose:()=>{},onDone:()=>{}});assert.equal(refs.length,6);return {tree,intent:refs[5],refs,cells};}
(async()=>{
 await run('frozen source identity and existing red/green remain distinct preserved evidence',()=>{assert.equal(sha(source),expectedSha);assert.equal(JSON.parse(fs.readFileSync(oldFiles[0])).checks.length,6);assert(JSON.parse(fs.readFileSync(oldFiles[0])).checks.every(x=>!x.passed));assert(JSON.parse(fs.readFileSync(oldFiles[1])).checks.every(x=>x.passed));});
 for(const ex of examples)await run('actual importAction accepts '+ex.name,async()=>{const p=await accepted(ex);if(ex.name==='sales_cancel'){assert.equal(p.cancel_source,'sales');assert(!('purchase_id'in p));}if(ex.name==='cancel_remaining')assert.equal(p.cancel_source,'purchase');if(ex.name==='return_credit'){assert.equal(p.allocations[0].invoice_line_index,0);assert.equal(p.allocations[0].quantity,'0.001');}return {type:ex.action,operation_id:p.operation_id};});
 for(const ex of examples)await run('reject extra top key '+ex.name,()=>denied({...clone(ex.value),paid:'999.99'}));
 for(const name of ['credit_invoice','return_credit'])await run('reject extra nested allocation key '+name,()=>{const p=clone(examples.find(x=>x.name===name).value);p.allocations[0].unapproved_cost='1.00';return denied(p);});
 for(const ex of examples)for(const key of Object.keys(ex.value).filter(k=>k.endsWith('_id')&&k!=='operation_id'))await run('reject bool ID '+ex.name+'.'+key,()=>denied({...clone(ex.value),[key]:true}));
 for(const [name,key] of [['credit_invoice','invoice_line_index'],['return_credit','invoice_line_index'],['return_credit','return_id']])await run('reject bool nested ID '+name+'.'+key,()=>{const p=clone(examples.find(x=>x.name===name).value);p.allocations[0][key]=true;return denied(p);});
 for(const ex of examples.filter(x=>'quantity'in x.value))await run('reject JSON number Q '+ex.name,()=>denied({...clone(ex.value),quantity:1}));
 await run('reject JSON number Q return-credit allocation',()=>{const p=clone(examples.find(x=>x.name==='return_credit').value);p.allocations[0].quantity=0.001;return denied(p);});
 await run('reject JSON number M commercial allocation',()=>{const p=clone(examples.find(x=>x.name==='credit_invoice').value);p.allocations[0].amount=1;return denied(p);});
 await run('reject JSON number M supplier claim',()=>denied({...clone(examples.find(x=>x.name==='confirm_supplier_claim').value),amount:1.31}));
 for(const ex of examples){await run('reject missing UUID '+ex.name,()=>{const p=clone(ex.value);delete p.operation_id;return denied(p);});await run('reject malformed UUID '+ex.name,()=>denied({...clone(ex.value),operation_id:'not-a-uuid'}));await run('reject UUID wrong version '+ex.name,()=>denied({...clone(ex.value),operation_id:'a0000000-0000-1000-8000-000000000001'}));}
 for(const ex of examples)await run('observer denied '+ex.name,()=>denied(ex.value,{role:'observer',write:false}));
 for(const ex of examples)await run('explicit write denied '+ex.name,()=>denied(ex.value,{role:'ceo',write:false}));
 for(const ex of examples.filter(x=>['credit_invoice','reverse_credit','confirm_supplier_claim'].includes(x.action)))await run('manager financial role denied '+ex.name,()=>denied(ex.value,{role:'manager',write:true}));
 for(const ex of examples.filter(x=>!['credit_invoice','reverse_credit','confirm_supplier_claim'].includes(x.action)))await run('manager operational action retained '+ex.name,()=>accepted(ex,{role:'manager',write:true}));
 await run('reject cancellation both target types',()=>denied({...clone(examples[0].value),line_id:27}));
 await run('reject cancellation missing target type',()=>{const p=clone(examples[0].value);delete p.purchase_id;return denied(p);});
 await run('reject unknown action',()=>denied({action:'erp_unknown_b03'}));
 for(const raw of ['null','[]','{"action":false}','{broken'])await run('reject invalid JSON shape '+raw,()=>denied(null,{raw}));
 for(const ex of examples)await run('actual dialog initial operation_id and change preserve imported intent '+ex.name,()=>{const rendered=render(ex.action,clone(ex.value));assert.equal(rendered.intent.current,OP);const inputs=visit(rendered.tree,node=>node.type==='textarea'&&node.props.value===common.reason);assert.equal(inputs.length,1);inputs[0].props.onChange({target:{value:'Уточнено ту саму підставу без створення іншого наміру'}});assert.equal(rendered.intent.current,OP);assert.equal(rendered.cells[1].value.reason,'Уточнено ту саму підставу без створення іншого наміру');return {initial:OP,after_change:rendered.intent.current};});
 await run('actual dialog recovery operation_id has precedence over preset',()=>{const x=render('return_supplier',clone(examples[1].value),{action:'return_supplier',operation_id:REC,proposal_id:OP});assert.equal(x.intent.current,REC);return {intent:x.intent.current};});
 await run('actual new blank dialog has no invented operation ID before preview',()=>{const x=render('return_supplier',{});assert.equal(x.intent.current,null);assert.equal(trace.random_uuid_calls,0);});
 for(const action of c.newKeys)await run('actual BoSActionDialog routes new '+action+' to CorrectionActionDialog',()=>{const props={action,preset:{operation_id:OP},data};const out=c.BoSActionDialog(props);assert.strictEqual(out.type,c.CorrectionActionDialog);assert.strictEqual(out.props.preset,props.preset);assert.equal(out.props.action,action);});
 for(const action of c.legacyKeys)await run('actual BoSActionDialog preserves old '+action+' route',()=>{const props={action,preset:{marker:'unchanged'},data};const out=c.BoSActionDialog(props);assert.strictEqual(out.type,c.ERPActionDialog);assert.strictEqual(out.props.preset,props.preset);});
 await run('no frontend/source or existing six-case evidence bytes changed',()=>{assert.equal(sha(fs.readFileSync(sourcePath)),expectedSha);for(const row of oldEvidence)assert.equal(sha(fs.readFileSync(row.file)),row.sha256);assert.equal(trace.network_calls,0);assert.equal(trace.effects_invoked,0);});
 const report={scope:'Actual extracted OperationsAssistant.importAction, B03 validators/role functions, full CorrectionActionDialog and BoSActionDialog JSX compiled in memory with bundled Babel. Minimal React hooks/element objects; lifecycle effects deliberately NOT invoked. Snapshot read is a local data stub. No network, backend, database, DOM, browser or gate10 acceptance.',source_file:sourcePath,source_sha256:expectedSha,runner_sha256:sha(fs.readFileSync(__filename)),extracted_sha256:{importAction:sha(importer),helpers:sha(helpers),roles:sha(roles),dialogs:sha(dialogs)},old_evidence_preserved:oldEvidence,trace,checks,passed:checks.filter(x=>x.passed).length,failed:checks.filter(x=>!x.passed).length};
 fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({source_sha256:expectedSha,passed:report.passed,failed:report.failed,failures:checks.filter(x=>!x.passed),output},null,2));process.exitCode=report.failed?1:0;
})().catch(e=>{console.error(e);process.exitCode=2;});
