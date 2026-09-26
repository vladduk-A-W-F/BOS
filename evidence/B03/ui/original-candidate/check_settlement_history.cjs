const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
const root=__dirname,sha=s=>crypto.createHash('sha256').update(s).digest('hex');
function execute(dir){const js=fs.readFileSync(path.join(dir,'assets/app.js'),'utf8'),source=fs.readFileSync(path.join(dir,'frontend/boss_app_source.html'),'utf8');const part=js.slice(js.indexOf('function B03Settlement('),js.indexOf('function CorrectionActionDialog('));
 const c={bosRole:()=> 'ceo',B03Facts:function B03Facts(){},React:{Fragment:'fragment',createElement:(type,props,...children)=>({type:typeof type==='function'?type.name:type,props:props||{},children})}};vm.createContext(c);vm.runInContext(part+'\nthis.render=B03Settlement;',c);
 const invoice={invoice_id:7,currency:'EUR',amount:'123.40',paid:'110.00',effective_credit:'0.00',net_amount:'123.40',receivable:'13.40',customer_credit:'0.00'};
 const settlement={effective_credit:'24.68',net_amount:'98.72',receivable:'0.00',customer_credit:'1.28'};
 const tree=c.render({invoice,settlement,currency:'EUR'}),tables=[],sections=[];
 function visit(node){if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return;}if(node.type==='B03Facts')tables.push(node.props.rows);if(node.type==='section')sections.push(node.props['aria-label']);visit(node.children);}visit(tree);
 const noMixedTimes=tables.every(rows=>{const values=rows.map(r=>r[1]);return !(values.includes('110.00')&&values.includes('98.72'));});
 const snapshotOwnFour=tables.some(rows=>rows.length===4&&rows.map(r=>r[1]).join('|')==='24.68|98.72|0.00|1.28');
 const currentOwnSix=tables.some(rows=>rows.map(r=>r[1]).join('|')==='123.40|110.00|0.00|123.40|13.40|0.00');
 return {source_sha256:sha(source),compiled_sha256:sha(js),checks:[{case:'Historical receipt table never borrows current paid110.00 while presenting historical net98.72',passed:noMixedTimes},{case:'Original receipt four fields and current six fields are separately labelled',passed:snapshotOwnFour&&currentOwnSix&&sections.includes('Результат цього погодження')&&sections.includes('Поточний стан рахунку')}],observed_tables:tables};}
const red=execute(path.join(root,'review_freeze_2')),green=execute(root);assert(red.checks.every(c=>!c.passed),'Original freeze must expose this exact regression');assert(green.checks.every(c=>c.passed),'Corrected candidate must separate both moments');
const result={scope:'Actual extracted compiled B03Settlement JavaScript with minimal React element objects; no DOM/browser/HTTP/DB acceptance',red,green};fs.writeFileSync(path.join(root,'SETTLEMENT_HISTORY_RED_GREEN.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
