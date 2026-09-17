// Actual extracted action importer, mocked read-only data fetch, no browser/API.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const filename=process.argv[2],output=process.argv[3],source=fs.readFileSync(filename,'utf8');
const method=source.split('\n').find(line=>line.includes('async function importAction(){'));
const helpers=source.match(/\/\/ B03_HELPERS_BEGIN\n([\s\S]*?)\/\/ B03_HELPERS_END/)[1];
const oldDefinitions=source.match(/const ERP_ACTIONS=\{[\s\S]*?\n\};/)[0];
const entries=[],errors=[],context={JSON,console,raw:'',bosRole:()=>'ceo',bosCan:()=>true,bosCanAction:()=>true,setError:e=>errors.push(e),setErpAction:e=>entries.push(e),setPayload:()=>{},setTask:()=>{},erpFetch:async()=>({as_of:'2026-09-12'}),window:{crypto:{randomUUID:()=> 'f0000000-0000-4000-8000-000000000001'}}};
vm.createContext(context);vm.runInContext(helpers+'\n'+oldDefinitions+'\n'+method,context);
const op='a0000000-0000-4000-8000-000000000001',common={operation_id:op,code:'КР-1',business_date:'2026-09-12',reason:'Погоджено джерельний результат'},checks=[];
const cases={cancel_remaining:{purchase_id:19,quantity:'1.000'},return_supplier:{receipt_id:23,quantity:'1.000'},return_from_shipment:{shipment_id:31,quantity:'1.000',location_id:4},credit_invoice:{invoice_id:5,basis:'commercial',source_document_id:4,allocations:[{invoice_line_index:0,amount:'1.00'}]},reverse_credit:{credit_id:20},confirm_supplier_claim:{claim_id:21,amount:'1.31',currency:'EUR',source_document_id:4}};
(async()=>{
 for(const [action,fields] of Object.entries(cases)){
  entries.length=errors.length=0;context.raw=JSON.stringify({action:'erp_'+action,...common,...fields});await context.importAction();
  try{assert.equal(entries.length,1,errors.join('; '));assert.equal(entries[0].type,action);assert.equal(entries[0].preset.operation_id,op);checks.push({action,passed:true});}
  catch(e){checks.push({action,passed:false,error:e.message});}
 }
 const report={scope:'Actual extracted OperationsAssistant.importAction closure in Node; mock snapshot GET only, no writes/browser/HTTP/DB',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),checks};
 if(output)fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));process.exitCode=checks.some(c=>!c.passed)?1:0;
})();
