// Focused regression for supply -> actual ERPActionDialog currency state/payload.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
function load(name,marker,exports){const text=fs.readFileSync(path.join(__dirname,name),'utf8'),end=text.indexOf(marker);assert(end>0);const context={require,__dirname,console,setImmediate,setTimeout,clearTimeout,AbortController,Headers,URL,TextEncoder,Uint8Array};vm.createContext(context);vm.runInContext(text.slice(0,end)+'\n'+exports,context);return context;}
const flow=load('check_flow_projections.cjs','const results=[]','this.make=harness;this.supplyFixture=supply;');
const form=load('check_confirmation_recovery.cjs','function receipt(','this.make=harness;');
(async()=>{
 const source=flow.make();await source.choose(0,'3');source.reply(0,flow.supplyFixture());await source.flush();source.button('Підготувати закупівлю').props.onClick();
 const [action,preset]=source.actions[0];assert.equal(action,'purchase');assert.equal(preset.currency,'UAH');assert.equal(preset.supplier_id,'');assert.equal(preset.price,'');source.unmount();
 for(const currency of [undefined,'EUR','USD']){
  const h=form.make({action,preset:{...preset,code:'CURRENCY-SYNTHETIC',quantity:'3.000',price:'10.00',supplier_id:11,due_date:'2026-10-01',direct_reason:'Synthetic explicit source',...(currency?{currency}:{})}});
  const selector=h.all().find(node=>node.type===h.context.Select&&node.children.flat().some(child=>child?.type==='option'&&child.props.value==='UAH'));
  assert(selector,'Currency selector');assert.equal(selector.props.value,currency||'UAH');
  const payload=await h.prepared();assert.equal(payload.currency,currency||'UAH');assert.equal(payload.price,'10.00');assert.equal(payload.supplier_id,11);h.unmount();
 }
 console.log('PASS supply action -> actual purchase dialog: default UAH and explicit EUR/USD match visible selection and preview payload; supplier and price remain explicit.');
})().catch(error=>{console.error(error);process.exitCode=1;});
