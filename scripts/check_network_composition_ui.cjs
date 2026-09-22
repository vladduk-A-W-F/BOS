// New composition contracts against actual merged JSX. Controlled hooks/HTTP,
// never a browser/DB proof or an invocation of the earlier exhausted suites.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
function load(name,exports){
 const source=fs.readFileSync(path.join(__dirname,name),'utf8'),end=source.indexOf('const results=[];');
 assert(end>0);const context={require,__dirname,console,setImmediate,setTimeout,clearTimeout,AbortController,Headers,URL,TextEncoder,Uint8Array};
 vm.createContext(context);vm.runInContext(source.slice(0,end)+'\n'+exports,context);return context;
}
const form=load('check_confirmation_recovery.cjs','this.make=harness;this.parent=integratedHarness;this.pending=entries;this.sent=sent;this.proposalID=id;');
const flow=load('check_flow_projections.cjs','this.make=harness;this.supply=supply;this.settlement=settlement;');
const labels=[
 'order currency and organisational branch stay distinct from fulfillment in actual payload',
 'network metadata clearing serializes null IDs and empty country/address without aliasing branch',
 'supply purchase carries line currency and only an explicitly chosen destination',
 'settlement debt retained and collectible use exact strings and payment uses collectible',
 'zero collectible disables payment and rejects a stale programmatic click',
 'retention source from another invoice fails closed',
 'new network action lost response retains same proposal and rejects wrong receipt identity',
 'new network action denies late success after access revision changes',
 'merged parent retains pending payment across invalidation and restores original opener on close',
 'legacy instant transfer and network dispatch remain distinct actual dialog actions',
];
if(process.argv.includes('--list')){console.log(JSON.stringify({schema:'bos.network-composition-ui-plan.v1',labels},null,2));process.exit(0);}
const from=process.argv.includes('--remaining')?3:0;
async function run(index,fn){if(index<from)return;await fn();console.log('PASS '+labels[index]);}
function replySuccess(h,n,fields){h.reply(n,200,{state:'succeeded',erp_event_id:31,impact:[],...fields});}
function heldFacts(collectible='6.00'){
 const f=flow.settlement();for(const row of [...f.totals,...f.invoices]){row.open='10.00';row.retained=collectible==='0.00'?'10.00':'4.00';row.collectible=collectible;}
 f.invoices[0].retentions=[{retention_id:17,invoice_id:9,code:'HOLD-SCOPED',amount:f.invoices[0].retained,currency:'UAH',status:'held',reason:'Agreed condition',release_reason:'',created_at:'2026-09-20',released_at:null}];return f;
}
(async()=>{
 await run(0,async()=>{for(const currency of [undefined,'EUR','USD']){
  const h=form.make({action:'order',preset:{code:'COMPOSE',customer_id:11,owner_id:12,branch_id:21,fulfillment_location_id:31,destination_country:'UA',due_date:'2026-12-31',lines:[{item_id:8,quantity:'1.000',price:'5.00'}],...(currency?{currency}:{})}});
  const selector=h.all().find(n=>n.type===h.context.Select&&n.children.flat().some(c=>c?.type==='option'&&c.props.value==='UAH'));assert.equal(selector.props.value,currency||'UAH');
  const p=await h.prepared();assert.equal(p.currency,currency||'UAH');assert.equal(p.branch_id,21);assert.equal(p.fulfillment_location_id,31);assert.notEqual(p.branch_id,p.fulfillment_location_id);h.unmount();
 }});
 await run(1,async()=>{for(const [action,preset,expected] of [
  ['order_network',{order_id:7,fulfillment_location_id:'',destination_country:'',reason:'Clear explicit metadata'},{order_id:7,fulfillment_location_id:null,destination_country:''}],
  ['purchase_network',{purchase_id:9,destination_id:'',origin_country:'',reason:'Clear explicit metadata'},{purchase_id:9,destination_id:null,origin_country:''}],
  ['location_update',{location_id:31,branch_id:'',lat:'',lng:'',address:'',reason:'Clear explicit metadata'},{location_id:31,branch_id:null,lat:null,lng:null,address:''}],
 ]){const h=form.make({action,preset});const p=await h.prepared();for(const [key,value] of Object.entries(expected))assert.equal(p[key],value,key);if(action!=='location_update')assert(!Object.hasOwn(p,'branch_id'));h.unmount();}});
 await run(2,async()=>{for(const currency of ['UAH','EUR','USD'])for(const target of [null,5]){
  const h=flow.make();await h.choose(0,'3');if(target)await h.choose(1,String(target));const f=flow.supply(target);f.line.currency=currency;f.fulfillment_location={id:44,code:'SEPARATE-FULFILLMENT'};
  h.reply(target?1:0,f);await h.flush();h.button('Підготувати закупівлю').props.onClick();const [action,preset]=h.actions[0];assert.equal(preset.currency,currency);assert.equal(preset.supplier_id,'');assert.equal(preset.price,'');assert.equal(preset.destination_id,target??undefined);assert(!Object.hasOwn(preset,'branch_id'));
  const dialog=form.make({action,preset:{...preset,code:'EXPLICIT-PO',supplier_id:11,price:'7.50',due_date:'2026-12-31',direct_reason:'Controlled explicit purchase'}});const payload=await dialog.prepared();assert.equal(payload.currency,currency);assert.equal(payload.destination_id,target??undefined);assert.equal(payload.price,'7.50');dialog.unmount();h.unmount();
 }});
 await run(3,async()=>{const h=flow.make('settlement');h.reply(0,heldFacts());await h.flush();assert.match(h.text(),/Борг за рахунком:\s+10\.00/);assert.match(h.text(),/Утримано:\s+4\.00/);assert.match(h.text(),/Доступно до оплати:\s+6\.00/);assert.match(h.text(),/Утримання № 17.*HOLD-SCOPED/);
  h.button('Зареєструвати оплату ·').props.onClick();const [action,preset]=h.actions[0];assert.equal(preset.amount,'6.00');const dialog=form.make({action,preset:{...preset,reference:'RAW-PAY'}});assert.equal((await dialog.prepared()).amount,'6.00');dialog.unmount();h.unmount();});
 await run(4,async()=>{const h=flow.make('settlement');h.reply(0,heldFacts('0.00'));await h.flush();const button=h.button('Зареєструвати оплату ·');assert.equal(button.props.disabled,true);button.props.onClick();assert.equal(h.actions.length,0);h.unmount();});
 await run(5,async()=>{const h=flow.make('settlement'),f=heldFacts();f.invoices[0].retentions[0].invoice_id=999;h.reply(0,f);await h.flush();assert.doesNotMatch(h.text(),/HOLD-SCOPED|INV-EXACT/);assert.equal(h.actions.length,0);h.unmount();});
 await run(6,async()=>{const h=form.make({action:'order_network',preset:{order_id:7,fulfillment_location_id:31,destination_country:'UA',reason:'Explicit network source'}});await h.prepared();h.click('Погодити й виконати');await h.flush();h.requests[1].reject(Error('Lost response'));await h.flush();assert.equal(form.pending(h)[0].action,'order_network');assert.equal(form.pending(h)[0].proposal_id,form.proposalID);
  h.click('Повторити це саме погодження');await h.flush();replySuccess(h,2,{order_id:999});await h.flush();assert.equal(h.done,0);assert.equal(form.pending(h).length,1);
  h.click('Повторити це саме погодження');await h.flush();replySuccess(h,3,{order_id:7});await h.flush();assert.equal(h.done,1);assert.equal(form.pending(h).length,0);assert.equal(form.sent(h).length,3);assert(form.sent(h).every(p=>p.proposal_id===form.proposalID));h.unmount();});
 await run(7,async()=>{const h=form.make({action:'hold_payment',preset:{invoice_id:7,amount:'4.00',code:'HOLD',reason:'Condition'}});await h.prepared();h.click('Погодити й виконати');await h.flush();h.reply(1,200,{state:'succeeded',erp_event_id:31,retention_id:17,invoice_id:7,impact:[]},{headers:{'X-BoS-Access':'r2'}});await h.flush();assert.equal(h.done,0);assert.equal(form.pending(h).length,0);assert.match(h.text(),/Погодження недоступне/);h.unmount();});
 await run(8,async()=>{
  const pending=form.parent();await pending.prepared();pending.click('Погодити й виконати');await pending.flush();pending.emit('bos:data-changed');await pending.flush();assert(pending.hasDialog());assert(!pending.requests[7].aborted);pending.requests[7].reject(Error('Lost response'));await pending.flush();pending.click('Повторити це саме погодження');await pending.flush();assert(form.sent(pending).every(p=>p.proposal_id===form.proposalID));pending.unmount();
  const focus=form.parent();await focus.pair();let returned=0;const opener={isConnected:true,disabled:false,focus(){returned++;}};focus.context.document.activeElement=opener;focus.click('Нове замовлення у цій точці');await focus.flush();focus.context.document.activeElement={focus(){throw Error('Wrong opener');}};await focus.pair(3);focus.all().find(n=>n.type==='dialog').props.onClose();await focus.flush();assert.equal(returned,1);assert(!focus.hasDialog());focus.unmount();
 });
 await run(9,async()=>{const h=flow.make();await h.choose(0,'3');await h.choose(1,'5');h.reply(1,flow.supply(5));await h.flush();h.button('Миттєво перемістити ·').props.onClick();const [action,preset]=h.actions[0];assert.equal(action,'transfer');
  const legacy=form.make({action,preset:{...preset,quantity:'1.000',code:'IMMEDIATE',reason:'Immediate physical change'}});assert.match(legacy.text(),/Миттєво перемістити матеріал/);assert.equal((await legacy.prepared()).action,'erp_transfer');legacy.unmount();
  const network=form.make({action:'transfer_dispatch',preset:{lot_id:4,location_id:5,quantity:'1.000',code:'IN-TRANSIT',reason:'Physical dispatch'}});assert.match(network.text(),/Відправити між точками/);assert.equal((await network.prepared()).action,'erp_transfer_dispatch');network.unmount();h.unmount();
 });
 console.log(JSON.stringify({schema:'bos.network-composition-ui.v1',passed:labels.length-from,labels:labels.slice(from),scope:'actual merged JSX; controlled hooks, storage, transport and opener; no browser/DB/physical network acceptance'},null,2));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
