"""C01 real HTTP task commands, only on a NEW verification database."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import os
from django.conf import settings
from django.db import connection
from django.test import Client,TestCase,override_settings
from scripts.check_support import login_test_client
from employees.models import Employee
from tasks.models import Task
from operations.models import Configuration,ActionProposal,AuditEvent
from erp.models import Event
from finance.models import Transaction,Salary

class CommandFixture:
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'),'verification_settings')
        if connection.vendor=='sqlite':self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.http=Client(enforce_csrf_checks=True,raise_request_exception=False);self.user=login_test_client(self.http,'ceo',capabilities=('view_document','export_workspace'))
        Configuration.objects.create(key='dataset',value={'as_of':'2026-09-12'});Configuration.objects.get_or_create(key='erp_write',defaults={'value':{'revision':0}})
        self.employee=Employee.objects.create(full_name='Синтетичний відповідальний '+('ї'*170),role='Виконавець')
        self.other=Employee.objects.create(full_name=self.employee.full_name,role='Інший виконавець')
    def post(self,path,payload,client=None):
        client=client or self.http
        return client.post(path,payload,content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    def state(self):return {m._meta.label:list(m.objects.order_by('pk').values()) for m in (Task,AuditEvent,Event,Transaction,Salary)}
    def preview(self,payload,client=None):
        before=self.state();response=self.post('/api/operations/preview/',payload,client);self.assertEqual(response.status_code,200,response.content);self.assertEqual(self.state(),before);return response.json()
    def confirm(self,proposal,client=None):return self.post('/api/operations/confirm/',{'proposal_id':proposal['id'],'confirmed':True},client)
    def command(self,payload,client=None):
        proposal=self.preview(payload,client);response=self.confirm(proposal,client);self.assertEqual(response.status_code,200,response.content);return proposal,response.json()
    def create(self,**fields):
        payload={'action':'create_task','title':'Перевірити фактичний результат','assignee_id':self.employee.pk,'deadline':'2026-09-15',**fields}
        proposal,receipt=self.command(payload);return Task.objects.get(pk=receipt['task_id']),proposal,receipt

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TaskCommandTests(CommandFixture,TestCase):
    def test_create_uses_explicit_fk_full_name_and_one_audit_with_no_other_effect(self):
        task,proposal,receipt=self.create(priority='none',category='')
        self.assertEqual(task.assignee,'');self.assertEqual(task.assignee_employee_id,self.employee.pk);self.assertEqual(task.result,'');self.assertIsNone(task.priority)
        self.assertEqual((AuditEvent.objects.count(),Event.objects.count(),Transaction.objects.count(),Salary.objects.count()),(1,0,0,0))
        row=self.http.get('/api/tasks/'+str(task.pk)+'/').json();self.assertEqual(row['assignee_name'],self.employee.full_name);self.assertEqual(row['assignee_id'],self.employee.pk)
        self.assertEqual(self.confirm(proposal).json(),receipt)
        before=self.state();raw=self.post('/api/tasks/',{'title':'Непогоджене створення'});self.assertEqual(raw.status_code,403);self.assertEqual(raw.json()['code'],'approval_required');self.assertEqual(self.state(),before)

    def test_done_requires_explicit_new_result_and_reopen_keeps_previous_history(self):
        task,_,_=self.create();p,done=self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'  Отримано підтвердження\nДжерело DOC-1  ','reason':'Перевірено відповідальним'})
        task.refresh_from_db();self.assertEqual(task.result,'  Отримано підтвердження\nДжерело DOC-1  ');self.assertEqual(task.status,'done');self.assertIsNone(task.priority)
        events=deepcopy(list(AuditEvent.objects.order_by('pk').values()));self.command({'action':'update_task','task_id':task.pk,'status':'active','reason':'Потрібне повторне уточнення'})
        task.refresh_from_db();self.assertEqual(task.result,'  Отримано підтвердження\nДжерело DOC-1  ')
        bad=self.post('/api/operations/preview/',{'action':'update_task','task_id':task.pk,'status':'done','reason':'Повторно завершити'});self.assertEqual(bad.status_code,422)
        self.assertEqual(list(AuditEvent.objects.filter(pk__in=[r['id'] for r in events]).order_by('pk').values()),events)

    def test_archive_restore_preserve_legacy_done_and_noop_creates_no_proposal(self):
        task=Task.objects.create(title='Історична завершена',assignee='Колишній виконавець',status='done',deadline=date(2026,9,1))
        proposal,receipt=self.command({'action':'update_task','task_id':task.pk,'archived':True,'reason':'Прибрати з робочого списку'})
        task.refresh_from_db();self.assertIsNotNone(task.archived_at);self.assertEqual(task.status,'done');self.assertIsNone(task.result)
        self.assertEqual(self.http.get('/api/tasks/').json(),[]);self.assertEqual(self.http.get('/api/tasks/',{'archived':'true'}).json()[0]['id'],task.pk)
        before=self.state();count=ActionProposal.objects.count();noop=self.preview({'action':'update_task','task_id':task.pk,'archived':True,'reason':'Перевірено поточний архів'})
        self.assertEqual(noop['state'],'no_change');self.assertIsNone(noop['id']);self.assertEqual(ActionProposal.objects.count(),count);self.assertEqual(self.state(),before)
        self.command({'action':'update_task','task_id':task.pk,'archived':False,'reason':'Відновити до перегляду'});task.refresh_from_db();self.assertIsNone(task.archived_at);self.assertEqual(task.assignee,'Колишній виконавець');self.assertIsNone(task.result)

    def test_new_session_can_read_exact_completed_proposal_but_cannot_confirm_it(self):
        task,proposal,receipt=self.create();new=Client(enforce_csrf_checks=True,raise_request_exception=False)
        from django.test.client import RequestFactory
        new.cookies=deepcopy(self.http.cookies)
        # A genuine fresh login for the same user; the known test password is set explicitly.
        self.user.set_password('Synthetic-C01-login-password');self.user.save(update_fields=['password'])
        new=Client(enforce_csrf_checks=True,raise_request_exception=False);new.get('/api/auth/csrf/');login=self.post('/api/auth/login/',{'username':self.user.username,'password':'Synthetic-C01-login-password'},new);self.assertEqual(login.status_code,200,login.content)
        result=new.get('/api/operations/task-proposals/'+proposal['id']+'/');self.assertEqual(result.status_code,200,result.content);self.assertEqual(result.json()['receipt'],receipt);self.assertFalse(result.json()['same_session'])
        self.assertEqual(self.confirm(proposal,new).status_code,403)

    def source(self,code):
        import hashlib
        from operations.models import Document,ProcurementRequest
        from finance.models import Counterparty
        from erp.models import SalesOrder,SalesLine,Item
        raw=('Synthetic C01 '+code).encode();doc=Document.objects.create(code=code,revision='A',title=code,content=raw,checksum=hashlib.sha256(raw).hexdigest(),text=raw.decode(),status='approved',access_level='operational')
        request=ProcurementRequest.objects.create(code=code+'-R',part=code,revision='A',quantity=1,unit='шт.',currency='EUR',required_by='2026-10-01',owner=self.employee,document=doc)
        item=Item.objects.create(code=code,name=code,revision='A',unit='шт.',document=doc)
        customer=Counterparty.objects.create(name=code,type='customer');order=SalesOrder.objects.create(code=code,customer=customer,owner=self.employee,due_date='2026-10-01',currency='EUR')
        SalesLine.objects.create(order=order,item=item,revision='A',quantity='1.000',price='1.00')
        return doc,request,order

    def test_all_historical_sources_hide_unlinked_task_history_summary_and_recovery(self):
        doc,request,order=self.source('C01-HIST');otherdoc,otherrequest,otherorder=self.source('C01-NOW')
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document','export_workspace'))
        p,r=self.command({'action':'create_task','title':'C01 HISTORICAL RESULT CANARY','assignee_id':self.employee.pk,'deadline':'2026-09-15','order_id':order.pk,'request_code':request.code},manager);task=Task.objects.get(pk=r['task_id'])
        self.command({'action':'update_task','task_id':task.pk,'order_id':otherorder.pk,'deadline':'2026-09-01','result':'C01 RESULT SECRET CANARY','reason':'Змінено поточне замовлення'},manager)
        self.command({'action':'update_task','task_id':task.pk,'order_id':None,'reason':'Зв’язок явно знято'},manager)
        for n in range(105):AuditEvent.objects.create(action='legacy_task',task=task,payload={'legacy':n})
        self.assertEqual(manager.get(f'/api/tasks/{task.pk}/history/').status_code,200)
        old=list(AuditEvent.objects.filter(task=task).order_by('pk').values());doc.access_level='ceo';doc.save(update_fields=['access_level'])
        for path in (f'/api/tasks/{task.pk}/',f'/api/tasks/{task.pk}/history/',f'/api/operations/task-proposals/{p["id"]}/'):
            reply=manager.get(path);self.assertEqual(reply.status_code,404,(path,reply.content));self.assertNotIn(b'CANARY',reply.content)
        for path in ('/api/tasks/','/api/operations/summary/','/api/operations/export/','/api/erp/snapshot/'):
            reply=manager.get(path);self.assertEqual(reply.status_code,200,(path,reply.content));self.assertNotIn(b'C01 HISTORICAL RESULT CANARY',reply.content);self.assertNotIn(b'C01 RESULT SECRET CANARY',reply.content)
        self.assertEqual(self.confirm(p,manager).status_code,404);self.assertEqual(list(AuditEvent.objects.filter(task=task).order_by('pk').values()),old)
        self.assertEqual(self.http.get(f'/api/tasks/{task.pk}/history/').status_code,200)

    def test_history_cursor_binds_actor_task_revision_and_cutoff_without_duplicate_page(self):
        task,p,r=self.create()
        for n in range(5):self.command({'action':'update_task','task_id':task.pk,'title':'Змістовна зміна '+str(n),'reason':'Відповідальний уточнив завдання'})
        first=self.http.get(f'/api/tasks/{task.pk}/history/',{'limit':'2'});self.assertEqual(first.status_code,200,first.content);a=first.json();cursor=a['next_cursor'];self.assertTrue(cursor)
        self.command({'action':'update_task','task_id':task.pk,'title':'Після початкового зрізу','reason':'Нова паралельна зміна'})
        ids=[r['id'] for r in a['items']]
        while cursor:
            reply=self.http.get(f'/api/tasks/{task.pk}/history/',{'limit':'2','cursor':cursor});self.assertEqual(reply.status_code,200,reply.content);page=reply.json();ids += [r['id'] for r in page['items']];cursor=page['next_cursor']
        self.assertEqual(len(ids),6);self.assertEqual(len(ids),len(set(ids)));self.assertNotIn(str(AuditEvent.objects.latest('created_at').pk),ids)
        second=Task.objects.create(title='Інше доручення');manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        for client,path in ((self.http,f'/api/tasks/{second.pk}/history/'),(manager,f'/api/tasks/{task.pk}/history/')):
            self.assertEqual(client.get(path,{'cursor':a['next_cursor']}).status_code,400)
        for query in ({'cursor':a['next_cursor']+'X'},{'limit':'0'},{'limit':'51'},{'limit':'true'}):self.assertEqual(self.http.get(f'/api/tasks/{task.pk}/history/',query).status_code,400)

    def test_employee_rename_reassignment_and_archive_keep_historical_name_branch_and_result(self):
        from branches.models import Branch
        b1=Branch.objects.create(code='C01-A',name='C01 перша');b2=Branch.objects.create(code='C01-B',name='C01 друга')
        self.employee.branch=b1;self.employee.save(update_fields=['branch']);self.other.branch=b2;self.other.save(update_fields=['branch'])
        task,_,_=self.create();self.assertEqual(task.branch_id,b1.pk)
        original=AuditEvent.objects.get(task=task).payload
        self.command({'action':'update_task','task_id':task.pk,'assignee_id':self.other.pk,'reason':'Призначено другого працівника з таким самим ім’ям'})
        task.refresh_from_db();self.assertEqual(task.assignee_employee_id,self.other.pk);self.assertEqual(task.branch_id,b1.pk);self.assertEqual(task.assignee,'')
        self.other.full_name='Нове повне ім’я виконавця';self.other.save(update_fields=['full_name']);self.assertEqual(self.http.get(f'/api/tasks/{task.pk}/').json()['assignee_name'],self.other.full_name)
        self.assertEqual(AuditEvent.objects.filter(task=task,action='create_task').get().payload,original)
        archived=self.http.delete(f'/api/employees/{self.other.pk}/',HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value);self.assertEqual(archived.status_code,204,archived.content);self.other.refresh_from_db();self.assertIsNotNone(self.other.archived_at)
        self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'Результат уже призначеного працівника','reason':'Фактично завершено раніше призначеним виконавцем'})
        denied=self.post('/api/operations/preview/',{'action':'update_task','task_id':task.pk,'assignee_id':self.other.pk,'reason':'Спроба нового призначення архівного працівника'});self.assertEqual(denied.status_code,422)

    def test_strict_fields_normalized_noops_and_archive_separate_intent(self):
        task,_,_=self.create();base={'action':'update_task','task_id':task.pk,'reason':'Перевірено заявлену зміну'}
        bad=[{'assignee_id':None},{'assignee_id':True},{'deadline':None},{'result':None},{'order_id':1.0},{'status':'overdue'},{'archived':'true'},{'archived':True,'title':'Недопустимий пакет'},{'request_code':'R-NOT-MUTABLE'},{'result':'x'*2001},{'reason':'x','title':'Зміна'}]
        before=self.state();count=ActionProposal.objects.count()
        for patch in bad:
            reply=self.post('/api/operations/preview/',{**base,**patch});self.assertEqual(reply.status_code,422,(patch,reply.content));self.assertEqual(self.state(),before)
        self.assertEqual(ActionProposal.objects.count(),count)
        self.command({**base,'priority':'none'});count=ActionProposal.objects.count();no=self.preview({**base,'priority':''});self.assertIsNone(no['id']);self.assertEqual(no['state'],'no_change');self.assertEqual(ActionProposal.objects.count(),count)
        self.command({**base,'archived':True});denied=self.post('/api/operations/preview/',{**base,'title':'Зміна архівного доручення'});self.assertEqual(denied.status_code,422)

    def test_shared_overdue_partition_excludes_archived_and_never_substitutes_demo_zero(self):
        from django.utils import timezone
        from tasks.queries import statistics
        from ai_assistant.views import _build_tasks_context
        rows=[Task.objects.create(title='C01 OPEN '+str(n),status=status,deadline=deadline) for n,(status,deadline) in enumerate((('done',date(2026,9,1)),('process',date(2026,9,1)),('active',date(2026,9,1)),('process',date(2026,9,20)),('overdue',date(2026,9,20)),('active',None)))]
        archived=Task.objects.create(title='ARCHIVED-C01-CANARY',status='process',deadline=date(2026,9,1),archived_at=timezone.now())
        expected={'total':6,'done':1,'overdue':2,'process':1,'active':2,'completion_rate':17};self.assertEqual(statistics(Task.objects.all()),expected)
        self.assertEqual({r['id'] for r in self.http.get('/api/tasks/',{'overdue':'true'}).json()},{rows[1].pk,rows[2].pk})
        self.assertEqual(self.http.get('/api/tasks/',{'status':'overdue'}).json()[0]['status'],'overdue')
        for path,key in (('/api/operations/summary/','overdue_tasks'),('/api/erp/snapshot/','home')):
            response=self.http.get(path);self.assertEqual(response.status_code,200,response.content);items=response.json()[key];items=items['tasks'] if key=='home' else items;self.assertNotIn(archived.pk,[r['id'] for r in items]);self.assertEqual({r['id'] for r in items if r['is_overdue']},{rows[1].pk,rows[2].pk})
        response=self.http.get('/api/dashboard/summary/');self.assertEqual(response.status_code,200,response.content);self.assertEqual(response.json()['tasks'],expected)
        context=_build_tasks_context(self.http.get('/api/operations/status/').wsgi_request);self.assertNotIn('ARCHIVED-C01-CANARY',context);self.assertIn('C01 OPEN 4',context)
        Task.objects.filter(archived_at=None).update(archived_at=timezone.now())
        response=self.http.get('/api/dashboard/summary/');self.assertEqual(response.json()['tasks'],{'total':0,'done':0,'overdue':0,'process':0,'active':0,'completion_rate':0});self.assertEqual(self.http.get('/api/operations/summary/').json()['overdue_tasks'],[])

    def test_locked_stale_expiry_recovery_and_late_sql_failure_preserve_same_intent(self):
        from datetime import timedelta
        from django.utils import timezone
        task,created,_=self.create();payload={'action':'update_task','task_id':task.pk,'title':'Новий погоджений зміст','reason':'Актуалізовано за джерелом'}
        first=self.preview(payload);second=self.preview({**payload,'title':'Інший погоджений зміст'});self.assertEqual(self.confirm(first).status_code,200)
        stale=self.confirm(second);self.assertEqual(stale.status_code,409,stale.content);self.assertEqual(stale.json()['code'],'proposal_stale')
        pending=self.preview({**payload,'title':'Майбутнє погодження'});ActionProposal.objects.filter(pk=pending['id']).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.http.get('/api/operations/task-proposals/'+pending['id']+'/').json()['state'],'expired');expired=self.confirm(pending);self.assertEqual(expired.json()['code'],'proposal_expired')
        ActionProposal.objects.filter(pk=created['id']).update(expires_at=timezone.now()-timedelta(days=1));self.assertEqual(self.http.get('/api/operations/task-proposals/'+created['id']+'/').json()['state'],'succeeded')
        late=self.preview({**payload,'title':'Зміна з реальним пізнім SQL відхиленням'});before=self.state()
        if connection.vendor!='sqlite':self.fail('C01 late SQL fixture requires explicit vendor implementation; not a skipped claim.')
        with connection.cursor() as cursor:cursor.execute("CREATE TRIGGER c01_fail_audit BEFORE INSERT ON operations_auditevent BEGIN SELECT RAISE(ABORT, 'synthetic audit write rejected'); END")
        try:failed=self.confirm(late);self.assertEqual(failed.status_code,409,failed.content);self.assertEqual(failed.json()['code'],'write_conflict');self.assertEqual(self.state(),before);self.assertIsNone(ActionProposal.objects.get(pk=late['id']).receipt)
        finally:
            with connection.cursor() as cursor:cursor.execute('DROP TRIGGER c01_fail_audit')
        actual=self.confirm(late);self.assertEqual(actual.status_code,200,actual.content);self.assertEqual(self.confirm(late).json(),actual.json());self.assertEqual(AuditEvent.objects.count(),len(before['operations.AuditEvent'])+1)

    def test_draft_result_literal_is_not_completion_evidence(self):
        task,_,_=self.create()
        for text in ('OK','  \n  '):
            self.command({'action':'update_task','task_id':task.pk,'result':text,'reason':'Збережено проміжний текст виконавця'})
            row=self.http.get(f'/api/tasks/{task.pk}/').json();self.assertEqual(row['result'],text);self.assertFalse(row['result_recorded'])
            denied=self.post('/api/operations/preview/',{'action':'update_task','task_id':task.pk,'status':'done','result':text,'reason':'Спроба завершення чернеткою'});self.assertEqual(denied.status_code,422)
        self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'Змістовний фінальний результат','reason':'Фактично завершено'})
        self.assertEqual(self.post('/api/operations/preview/',{'action':'update_task','task_id':task.pk,'result':'OK','reason':'Спроба зіпсувати результат'}).status_code,422)

    def test_actual_effective_day_rollover_invalidates_task_proposal(self):
        from unittest.mock import patch
        task,_,_=self.create();Configuration.objects.filter(key='dataset').delete()
        with patch('operations.service.as_of',return_value=date(2026,9,12)):
            proposal=self.preview({'action':'update_task','task_id':task.pk,'deadline':'2026-09-12','reason':'Строк погоджений у конкретний день'})
        before=self.state()
        with patch('operations.service.as_of',return_value=date(2026,9,13)):
            response=self.confirm(proposal)
        self.assertEqual(response.status_code,409,response.content);self.assertEqual(response.json()['code'],'proposal_stale');self.assertEqual(self.state(),before)

    def test_reopen_cannot_replace_previous_result_in_the_same_transition(self):
        task,_,_=self.create();self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'Попередній збережений результат','reason':'Фактично завершено'})
        before=self.state();response=self.post('/api/operations/preview/',{'action':'update_task','task_id':task.pk,'status':'active','result':'Інший результат при відкритті','reason':'Повернути в роботу'})
        self.assertEqual(response.status_code,422,response.content);self.assertEqual(self.state(),before)
        self.command({'action':'update_task','task_id':task.pk,'status':'active','result':'Попередній збережений результат','reason':'Явно повернути в роботу'});task.refresh_from_db();self.assertEqual(task.result,'Попередній збережений результат');self.assertEqual(AuditEvent.objects.filter(task=task).latest('created_at').payload['transition'],'reopen')

    def test_malformed_large_assignee_filter_returns_controlled_400(self):
        for value in ('9'*5000,'9223372036854775808','1.0','true','0','-1'):
            response=self.http.get('/api/tasks/',{'assignee_id':value});self.assertEqual(response.status_code,400,(len(value),response.content));self.assertEqual(Task.objects.count(),0)
