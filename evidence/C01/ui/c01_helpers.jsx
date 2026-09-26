// C01_HELPERS_BEGIN
const C01_STATUS={active:'Відкрите',process:'У роботі',done:'Виконане',overdue:'Історичний статус: прострочене'};
const C01_TRANSITIONS={create:'Створено',update:'Змінено',archive:'Архівовано',restore:'Відновлено',reopen:'Повернуто до роботи',complete:'Виконано',result_correction:'Уточнено результат'};
const C01_FIELDS=['title','category','priority','assignee_id','deadline','order_id','status','result','archived'];
const c01Own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const c01UUID=s=>typeof s==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(s);
const c01Id=n=>Number.isSafeInteger(n)&&n>0;
function c01InputId(value,nullable=false){if(nullable&&(value===''||value===null))return null;const s=String(value);if(!/^[1-9]\d*$/.test(s)||!c01Id(Number(s)))throw Error('Оберіть наявний запис зі списку.');return Number(s);}
function c01Date(s){if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s)||Number(s.slice(0,4))<1)return false;const d=new Date(s+'T00:00:00Z');return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===s;}
function c01Text(value,label,min,max,trim=false){if(typeof value!=='string'||/[\u0000\uD800-\uDFFF]/u.test(value))throw Error(label+': потрібен коректний текст.');const text=trim?value.trim():value;if([...text].length<min||[...text].length>max)throw Error(label+': від '+min+' до '+max+' символів.');return text;}
function c01TaskPayload(value){
 if(!value||Array.isArray(value)||typeof value!=='object'||!['create_task','update_task'].includes(value.action))throw Error('Підтримуються create_task та update_task.');
 const create=value.action==='create_task',keys=create?['action','title','assignee_id','deadline','category','priority','order_id','request_code']:['action','task_id','reason',...C01_FIELDS];
 if(Object.keys(value).some(k=>!keys.includes(k)))throw Error('Доручення містить невідомі поля.');
 const p={...value};
 if(create&&!['title','assignee_id','deadline'].every(k=>c01Own(p,k)))throw Error('Для нового доручення потрібні назва, відповідальний і строк.');
 if(!create){if(!c01Id(p.task_id))throw Error('Потрібен фактичний ID доручення.');p.reason=c01Text(p.reason,'Причина',3,1000,true);if(!C01_FIELDS.some(k=>c01Own(p,k)))throw Error('Оберіть хоча б одну зміну.');}
 if(c01Own(p,'archived')){if(typeof p.archived!=='boolean'||C01_FIELDS.filter(k=>c01Own(p,k)).length!==1)throw Error('Архівування або відновлення погоджується окремо від інших змін.');}
 if(c01Own(p,'title'))p.title=c01Text(p.title,'Назва',3,200,true);
 if(c01Own(p,'category'))p.category=c01Text(p.category,'Категорія',0,50);
 if(c01Own(p,'assignee_id')&&!c01Id(p.assignee_id))throw Error('Потрібен ID обраного співробітника.');
 if(c01Own(p,'order_id')&&p.order_id!==null&&!c01Id(p.order_id))throw Error('Потрібен ID замовлення або null для відв’язування.');
 if(c01Own(p,'deadline')&&!c01Date(p.deadline))throw Error('Вкажіть календарну дату у форматі РРРР-ММ-ДД.');
 if(c01Own(p,'status')&&!['active','process','done'].includes(p.status))throw Error('Простроченість визначає сервер за строком; оберіть робочий статус.');
 if(c01Own(p,'priority')){if(p.priority===''||p.priority==='none')p.priority=null;if(![null,'high','medium','low'].includes(p.priority))throw Error('Оберіть пріоритет або «Без пріоритету».');}
 if(c01Own(p,'result'))p.result=c01Text(p.result,'Результат',0,2000);
 if(c01Own(p,'request_code'))p.request_code=c01Text(p.request_code,'Код заявки',1,200,true);
 return p;
}
function c01TaskJSON(raw){
 if(new TextEncoder().encode(raw).length>30000)throw Error('JSON доручення перевищує 30 000 байтів.');
 const value=JSON.parse(raw),tokens=raw.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]/g)||[],seen=new Set();
 for(let i=0;i<tokens.length-1;i++)if(tokens[i][0]==='"'&&tokens[i+1]===':'){const key=JSON.parse(tokens[i]);if(seen.has(key))throw Error('JSON містить повторний ключ: '+key);seen.add(key);}
 return c01TaskPayload(value);
}
function c01BuildPayload({task,values,changed=[],mode='create',requestCode,asOf}){
 if(mode==='archive'||mode==='restore')return c01TaskPayload({action:'update_task',task_id:task.id,reason:values.reason,archived:mode==='archive'});
 if(!task){const p={action:'create_task',title:values.title,assignee_id:c01InputId(values.assignee_id),deadline:values.deadline,category:values.category,priority:values.priority,order_id:c01InputId(values.order_id,true),...(requestCode?{request_code:requestCode}:{})};if(asOf&&p.deadline<asOf)throw Error('Строк нового доручення не може бути раніше дати зрізу '+asOf+'.');return c01TaskPayload(p);}
 const p={action:'update_task',task_id:task.id,reason:values.reason};for(const key of changed){if(!C01_FIELDS.includes(key)||key==='archived')continue;p[key]=['assignee_id','order_id'].includes(key)?c01InputId(values[key],key==='order_id'):values[key];}
 const resultingStatus=p.status??task.status;if(task.status==='done'&&['active','process'].includes(resultingStatus)&&c01Own(p,'result')&&p.result!==task.result)throw Error('Повернення до роботи зберігає попередній результат. Новий текст погодьте окремо після відкриття доручення.');
 if((p.status==='done'&&task.status!=='done')||(resultingStatus==='done'&&c01Own(p,'result'))){if(!c01Own(p,'result')||typeof p.result!=='string'||p.result.trim().length<3)throw Error('Для нового завершення явно запишіть результат: щонайменше 3 символи.');if(!c01Id(p.assignee_id??task.assignee_id))throw Error('Для завершення оберіть відповідального співробітника.');}
 return c01TaskPayload(p);
}
function c01Form(task,preset={},asOf='',defaultEmployee=''){
 const base={title:task?.title??'',assignee_id:task?.assignee_id??defaultEmployee,deadline:task?.deadline??'',category:task?.category??'Загальне',priority:task?.priority??'',order_id:task?.order_id??'',status:task?.status??'active',result:task?.result??'',reason:''};
 if(!task){base.priority='medium';base.deadline=asOf;}
 for(const k of [...C01_FIELDS,'reason'])if(c01Own(preset,k))base[k]=preset[k]??'';
 if(task&&preset.status==='done'&&task.status!=='done'&&!c01Own(preset,'result'))base.result='';
 return base;
}
function c01TaskSegment(task){return task.archived?'archive':task.status==='done'?'done':task.is_overdue===true?'overdue':task.status==='process'?'process':'active';}
function c01Assignee(task){return task.assignee_name??task.assignee??'';}
function c01EmployeeLabel(e){return [e.full_name,e.role,e.branch_name,'ID '+e.id].filter(Boolean).join(' · ');}
function c01ImpactValue(value,field){if(value===null)return 'Не задано';if(typeof value==='boolean')return value?'Так':'Ні';if(value&&typeof value==='object')return (value.name??value.code??'Не задано')+(value.id!=null?' · ID '+value.id:'');return field==='status'?(C01_STATUS[value]||String(value)):String(value);}
function c01PendingKey(){return bosStorageKey('task-proposals-pending');}
function c01PendingRead(){const raw=sessionStorage.getItem(c01PendingKey());if(!raw)return [];let rows;try{rows=JSON.parse(raw);}catch{throw Error('Не вдалося прочитати ідентифікатори погоджень. Їх не видалено.');}const user=window.BOS_RUNTIME?.user_id;if(!Array.isArray(rows)||rows.some(e=>!e||!c01UUID(e.proposal_id)||!['create_task','update_task'].includes(e.action)||e.user_id!==user||!c01Id(e.user_id)||(e.task_id!==null&&!c01Id(e.task_id))))throw Error('Збережені ідентифікатори мають невідомий формат. Дані не видалено.');return rows.map(({proposal_id,action,task_id,user_id})=>({proposal_id,action,task_id,user_id}));}
function c01PendingSave(entry){if(!c01Id(window.BOS_RUNTIME?.user_id)||entry.user_id!==window.BOS_RUNTIME.user_id||!c01UUID(entry.proposal_id))throw Error('Не підтверджено обліковий запис або ідентифікатор погодження.');const rows=c01PendingRead();if(!rows.some(r=>r.proposal_id===entry.proposal_id))rows.push({proposal_id:entry.proposal_id,action:entry.action,task_id:entry.task_id,user_id:entry.user_id});sessionStorage.setItem(c01PendingKey(),JSON.stringify(rows));window.dispatchEvent(new window.Event('bos:task-pending'));}
function c01PendingRemove(id){sessionStorage.setItem(c01PendingKey(),JSON.stringify(c01PendingRead().filter(r=>r.proposal_id!==id)));window.dispatchEvent(new window.Event('bos:task-pending'));}
function c01Terminal(status,body){return status===409&&['proposal_stale','proposal_expired'].includes(body?.code);}
// C01_HELPERS_END
function C01Impact({changes=[]}){return <ERPTable rows={changes} empty="Фактичних змін немає." columns={[["Доручення",r=>r.code||(r.id?'№'+r.id:'Нове доручення')],["Поле",'label'],["Було",r=><span className="c01-text">{c01ImpactValue(r.before,r.field)}</span>],["Стане / стало",r=><span className="c01-text">{c01ImpactValue(r.after,r.field)}</span>]]}/>;}
function C01PendingLauncher({onRecover}){const [rows,setRows]=useState([]),[error,setError]=useState('');useEffect(()=>{const read=()=>{try{setRows(c01PendingRead());setError('');}catch(e){setError(e.message);}};read();window.addEventListener('bos:task-pending',read);return()=>window.removeEventListener('bos:task-pending',read);},[]);if(error)return <p className="erp-error" role="alert">{error}</p>;return rows.length?<details className="c01-pending"><summary>Незавершена перевірка доручень · {rows.length}</summary><p className="op-muted">Лише ідентифікатори в поточній вкладці. Текст доручень і результатів тут не збережено.</p>{rows.map(r=><div className="erp-row" key={r.proposal_id}><span>{r.action==='create_task'?'Створення доручення':'Зміна доручення №'+r.task_id} · {r.proposal_id}</span><Button onClick={()=>onRecover(r)}>Перевірити результат</Button></div>)}</details>:null;}
