// Controlled actual parent JSX: capture the opener before async busy disables it.
// This checks lifecycle behavior; the native DOM/browser check remains separate.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const runner=fs.readFileSync(path.join(__dirname,'check_confirmation_recovery.cjs'),'utf8');
const setup=runner.slice(0,runner.indexOf('const results=[];'));
const context={require,__dirname,console,Headers,AbortController,TextEncoder,URL,setImmediate};
vm.createContext(context);vm.runInContext(setup+'\nthis.make=integratedHarness;',context);
(async()=>{
 let passed=0;
 for(const mode of ['connected','detached','disabled','changed-scope']){
  const h=context.make();await h.pair();let focused=0;
  const opener={isConnected:true,disabled:false,focus(){focused++;}};
  h.context.document.activeElement=opener;
  h.click('Нове замовлення у цій точці');await h.flush();
  assert(h.all().find(n=>h.text(n)==='Нове замовлення у цій точці').props.disabled);
  h.context.document.activeElement={isConnected:true,focus(){throw Error('Must not restore the later body focus');}};
  await h.pair(3);assert(h.hasDialog());
  const dialog=h.all().find(n=>n.type==='dialog');assert(dialog);
  if(mode==='detached')opener.isConnected=false;
  if(mode==='disabled')opener.disabled=true;
  if(mode==='changed-scope')h.window.BOS_RUNTIME.access_revision='r2';
  dialog.props.onClose();await h.flush();
  assert.equal(focused,mode==='connected'?1:0,mode);
  assert(!h.hasDialog());assert.equal(h.requests.length,6);
  h.unmount();passed++;console.log('PASS original opener '+mode);
 }
 console.log(JSON.stringify({schema:'bos.workpoint-focus-controlled.v1',passed,scope:'actual JSX parent with controlled focus target, no browser'}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
