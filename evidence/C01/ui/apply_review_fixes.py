from pathlib import Path
p=Path(__file__).resolve().parent
f=p/'c01_helpers.jsx';s=f.read_text();s=s.replace("if(c01Own(p,'result')){p.result=c01Text(p.result,'Результат',0,2000);if(p.result!==''&&p.result.trim().length<3)throw Error('Змістовний результат має містити щонайменше 3 символи.');}","if(c01Own(p,'result'))p.result=c01Text(p.result,'Результат',0,2000);")
s=s.replace('function c01ImpactValue(value){','function c01ImpactValue(value,field){').replace("return C01_STATUS[value]||String(value);}","return field==='status'?(C01_STATUS[value]||String(value)):String(value);}")
s=s.replace('c01ImpactValue(r.before)','c01ImpactValue(r.before,r.field)').replace('c01ImpactValue(r.after)','c01ImpactValue(r.after,r.field)');f.write_text(s)
f=p/'c01_dialog.jsx';s=f.read_text();s=s.replace("[orderOpen,setOrderOpen]=useState(false);","[orderOpen,setOrderOpen]=useState(false),[scopeDenied,setScopeDenied]=useState(false);")
s=s.replace(" async function load(){", " function denyScope(){setTask(null);setHistory([]);setHistoryCursor(null);setHistoryLoaded(false);setOrders([]);setOrderOpen(false);setReady(false);setScopeDenied(true);}\n async function load(){")
s=s.replace("const responses=await Promise.all([targetId?request('/api/tasks/'+targetId+'/'):Promise.resolve(null)","const recordId=receipt?.task_id||targetId;const responses=await Promise.all([recordId?request('/api/tasks/'+recordId+'/'):Promise.resolve(null)")
s=s.replace("for(const r of responses.filter(Boolean))if(!r.ok)throw Error(r.body.error||'Не вдалося прочитати доручення або доступні джерела.');", "for(const r of responses.filter(Boolean))if(!r.ok){if([403,404].includes(r.status))denyScope();throw Error(r.body.error||'Не вдалося прочитати доручення або доступні джерела.');}")
s=s.replace("if((targetId&&row?.id!==targetId)","if((recordId&&row?.id!==recordId)")
s=s.replace("setAsOf(snapshot.as_of);setReady(true);", "setAsOf(snapshot.as_of);setReady(true);setScopeDenied(false);")
s=s.replace("setReady(false);setTask(null);}}finally", "setReady(false);}}finally")
s=s.replace("setReceipt(result);setTask(null);", "setReceipt(result);setTask(null);setScopeDenied(false);")
old=next(l for l in s.splitlines() if l.startswith(' async function refreshRecord()'))
new=""" async function refreshRecord(){const id=receipt?.task_id||task?.id||targetId;if(lock.current||!id)return;lock.current=true;setBusy('record');setReadError('');try{const [r,related]=await Promise.all([request('/api/tasks/'+id+'/'),request('/api/erp/snapshot/')]);if(!alive.current)return;for(const response of [r,related])if(!response.ok){if([403,404].includes(response.status))denyScope();throw Error(response.body.error||'Поточне доручення або джерела недоступні.');}if(r.body.id!==id||!Array.isArray(related.body.orders))throw Error('Не отримано актуального доручення з джерелами.');setTask(r.body);setOrders(related.body.orders);setOrderOpen(false);setScopeDenied(false);setReady(true);}catch(e){if(alive.current)setReadError(e.name==='AbortError'?'Оновлення не завершилося. Квитанція збережена.':e.message);}finally{lock.current=false;if(alive.current)setBusy('');}}"""
s=s.replace(old,new)
s=s.replace("if(!r.ok||r.body.task_id!==id||!Array.isArray(r.body.items))throw Error(r.body.error||'Історія доручення недоступна.');", "if(!r.ok){if([403,404].includes(r.status))denyScope();throw Error(r.body.error||'Історія доручення недоступна.');}if(r.body.task_id!==id||!Array.isArray(r.body.items))throw Error('Некоректна відповідь історії доручення.');setScopeDenied(false);")
s=s.replace('<h3>Поточне доручення №{task.id}</h3>', '<h3>Доручення №{task.id} · останній прочитаний стан</h3>')
s=s.replace('<C01Impact changes={receipt.impact}/>', "{scopeDenied?<p className=\"erp-error\">Результат виконання збережено, але текст змін зараз недоступний. Перевірте поточний доступ до доручення.</p>:<C01Impact changes={receipt.impact}/>}")
s=s.replace(':proposal?<section>', ':proposal&&!scopeDenied?<section>')
f.write_text(s)
# Existing test contexts include newly added scope helper/setters; no product tests removed.
for name in ['check_c01_ui.cjs','check_review_fixes.cjs']:
 f=p/name;s=f.read_text();s=s.replace("'Terminal','NoChange','Busy']", "'Terminal','NoChange','Busy','Orders','OrderOpen','Ready','ScopeDenied']")
 s=s.replace("['close','accept','commit'", "['close','denyScope','accept','commit'")
 s=s.replace("['close','accept'].includes(name)", "['close','denyScope','accept'].includes(name)")
 f.write_text(s)
