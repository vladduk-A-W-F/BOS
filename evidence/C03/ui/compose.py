from pathlib import Path
import hashlib
r=Path(__file__).resolve().parent
base=(r/'base/boss_app_source.html').read_text()
assert hashlib.sha256(base.encode()).hexdigest()=='fd283ac01fd50fd2478a5902e492fbed5f16da943ac3731a01b4903a96dec801'
s=base
start=s.index('function Bank(');end=s.index('// Типы контрагентов',start)
s=s[:start]+(r/'c03_bank.jsx').read_text()+'\n'+s[end:]
s=s.replace('function Bank(',''.join((r/f).read_text()+'\n' for f in ['c03_helpers.jsx','c03_forms.jsx','c03_dialogs.jsx','c03_records.jsx'])+'function Bank(',1)
s=s.replace('</style>',(r/'c03_styles.css').read_text()+'\n</style>',1)
old="[erpAction,setErpAction]=useState(null);"
assert s.count(old)==1
s=s.replace(old,"[erpAction,setErpAction]=useState(null),[statementAction,setStatementAction]=useState(null);")
old="if(value.action.startsWith('erp_')){const type="
assert s.count(old)==1
s=s.replace(old,"if(C03_ACTIONS[value.action]){if(bosRole()!=='ceo')throw Error('Виписки доступні лише CEO.');const preset=c03ActionJSON(raw);setStatementAction({action:preset.action,preset});}else if(value.action.startsWith('erp_')){const type=")
old="{erpAction&&<BoSActionDialog action={erpAction.type}"
assert s.count(old)==1
s=s.replace(old,"{statementAction&&<C03ActionDialog {...statementAction} onClose={()=>setStatementAction(null)} onDone={()=>{refetchTasks?.();setMessages(m=>[...m,{role:'assistant',text:'Дію з випискою підтверджено. Квитанція та поточні джерела відкриті в діалозі.'}]);}}/>}"+old)
(r/'frontend/boss_app_source.html').write_text(s)
print(hashlib.sha256(s.encode()).hexdigest())
