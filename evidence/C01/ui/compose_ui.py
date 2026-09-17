from pathlib import Path
import hashlib
p=Path(__file__).resolve().parent;s=(p/'base/boss_app_source.html').read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='f00fe5165592b9e8a8a71fda7d16c2f70ba61620a94a864c7ef3eb4dc1635c60'
def replace(old,new):
 global s
 assert s.count(old)==1,(old[:80],s.count(old));s=s.replace(old,new,1)
def region(start,end,file):
 global s
 a=s.index(start);b=s.index(end,a);s=s[:a]+(p/file).read_text()+'\n'+s[b:]
region('function Tasks(', 'function Employees(', 'c01_tasks.jsx')
region('function Topbar(', '// AI-панель справа', 'c01_topbar.jsx')
region('function ControlledTask(', 'function ProcurementEntry(', 'c01_dialog.jsx')
replace('function ControlledTask(', (p/'c01_helpers.jsx').read_text()+'\nfunction ControlledTask(')
replace("}else{setPayload(value);setTask(true);}setError('');", "}else{setPayload(c01TaskJSON(raw));setTask(true);}setError('');")
replace(".then(data=>{const date=window.BOS_RUNTIME?.as_of||new Date().toISOString().slice(0,10);setTasks(data.map(t=>({...t,status:t.status!=='done'&&t.deadline&&t.deadline<date?'overdue':t.status})));setTasksLoading(false);})", ".then(data=>{if(!Array.isArray(data))throw new Error('Некоректний список доручень');setTasks(data);setTasksLoading(false);})")
# Active scoped projection supplies status and is_overdue separately.
replace("tasks.some(t=>t.status==='overdue')", "tasks.some(t=>!t.archived&&t.is_overdue===true)")
replace("tasks.filter(t=>t.status!=='done').length", "tasks.filter(t=>!t.archived&&t.status!=='done').length")
readonly=next(line for line in s.splitlines(True) if "if((sub==='tasks'||!sub)&&!bosCan('write'))return" in line)
replace(readonly,'')
replace('type===\'tasks\'?[["Доручення",\'title\'],["Відповідальний",\'assignee\'],["Термін",r=>erpDate(r.deadline)],["Стан",r=>({done:\'Виконано\',active:\'Відкрите\',process:\'У роботі\'})[r.status]]]', 'type===\'tasks\'?[["Доручення",\'title\'],["Відповідальний",r=>c01Assignee(r)],["Термін",r=>erpDate(r.deadline)],["Стан",r=>(C01_STATUS[r.status]||r.status)+(r.is_overdue?\' · прострочено\':\'\')]]')
replace("(data.home?.tasks||[]).filter(t=>selection.overdue?(t.overdue??(t.status!=='done'&&!!t.deadline&&t.deadline<data.as_of)):t.status!=='done')", "(data.home?.tasks||[]).filter(t=>!t.archived&&(selection.overdue?t.is_overdue===true:t.status!=='done'))")
replace("const homeTasks=(data.home?.tasks||[]).map(t=>({...t,overdue:t.overdue??(t.status!=='done'&&!!t.deadline&&t.deadline<data.as_of)}))", "const homeTasks=(data.home?.tasks||[]).filter(t=>!t.archived).map(t=>({...t,overdue:t.is_overdue===true}))")
replace("<span>{t.assignee} · до {erpDate(t.deadline)}</span>", "<span>{c01Assignee(t)} · до {erpDate(t.deadline)}</span>")
css='''\n/* C01 scoped task styles */\n.c01-dialog{width:min(980px,96vw)}.c01-text{white-space:pre-wrap;overflow-wrap:anywhere}.c01-textarea{width:100%;min-height:100px;background:var(--surface2,#202228);color:inherit;border:1px solid #637083;border-radius:8px;padding:10px;font:inherit}.c01-wide{grid-column:1/-1}.c01-current,.c01-history{border-top:1px solid #3b414c;margin-top:20px;padding-top:16px}.c01-current h4,.c01-history h4{margin:12px 0 8px}.c01-pending{padding:8px 24px;border-bottom:1px solid #3b414c;font-size:13px}.c01-pending .erp-row{padding:8px 0;overflow-wrap:anywhere}.c01-task-table{margin-top:16px}.c01-task-table td{vertical-align:top}.c01-task-table td:first-child{min-width:220px}.c01-task-table .erp-actions{max-width:240px}.c01-dialog .erp-form>label{min-width:0}.c01-dialog select{max-width:100%}@media(max-width:600px){.c01-dialog .erp-form{grid-template-columns:1fr}.c01-pending{padding:8px 12px}}\n'''
replace('</style>',css+'</style>')
(p/'frontend/boss_app_source.html').write_text(s)
print(hashlib.sha256(s.encode()).hexdigest())
