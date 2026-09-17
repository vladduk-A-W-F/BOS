"""C01 additive real HTTP/SQL races; no simulated worker result."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json,threading
from django.conf import settings
from django.db import connections,connection,transaction
from django.test import Client,TransactionTestCase,override_settings
from tasks.test_commands import CommandFixture
from tasks.models import Task
from operations.models import AuditEvent,ActionProposal
from employees.models import Employee

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TaskConcurrencyTests(CommandFixture,TransactionTestCase):
    def pair(self,proposals):
        barrier=threading.Barrier(2)
        def worker(index):
            connections.close_all();client=Client(enforce_csrf_checks=True,raise_request_exception=False);client.cookies=deepcopy(self.http.cookies)
            try:
                barrier.wait(timeout=10);response=self.confirm(proposals[index],client);return {'status':response.status_code,'json':response.json()}
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(worker,range(2)))

    def test_same_create_proposal_two_actual_requests_commit_one_task_and_audit(self):
        proposal=self.preview({'action':'create_task','title':'Одне доручення у двох HTTP запитах','assignee_id':self.employee.pk,'deadline':'2026-09-15'})
        replies=self.pair([proposal,proposal]);self.assertIn(200,[r['status'] for r in replies]);self.assertTrue(all(r['status'] in (200,409) for r in replies),replies)
        good=next(r['json'] for r in replies if r['status']==200);self.assertEqual(Task.objects.count(),1);self.assertEqual(AuditEvent.objects.count(),1)
        for reply in replies:
            if reply['status']==200:self.assertEqual(reply['json'],good)
        self.assertEqual(self.confirm(proposal).json(),good);self.assertEqual(AuditEvent.objects.count(),1)
        print('C01_TASK_PAIR '+json.dumps({'scenario':'create','statuses':[r['status'] for r in replies],'one_task_audit':True}))

    def test_competing_title_and_archive_have_one_winner_and_authoritative_stale(self):
        task,_,_=self.create();base={'action':'update_task','task_id':task.pk,'reason':'Конкурентне погодження власника'}
        proposals=[self.preview({**base,'title':'Нова погоджена назва'}),self.preview({**base,'archived':True})];replies=self.pair(proposals)
        self.assertEqual(sorted(r['status'] for r in replies),[200,409],replies);self.assertEqual(AuditEvent.objects.filter(task=task).count(),2)
        winner=next(i for i,r in enumerate(replies) if r['status']==200);loser=1-winner;retry=self.confirm(proposals[loser]);self.assertEqual(retry.status_code,409);self.assertEqual(retry.json()['code'],'proposal_stale')
        task.refresh_from_db();self.assertEqual(task.title,'Нова погоджена назва' if winner==0 else 'Перевірити фактичний результат');self.assertEqual(task.archived_at is not None,winner==1)

    def test_same_archive_and_restore_retries_preserve_timestamp_and_history(self):
        task,_,_=self.create()
        for desired in (True,False):
            proposal=self.preview({'action':'update_task','task_id':task.pk,'archived':desired,'reason':'Фактичний архівний перехід'});count=AuditEvent.objects.count();results=self.pair([proposal,proposal]);self.assertIn(200,[r['status'] for r in results]);self.assertTrue(all(r['status'] in (200,409) for r in results));before=self.state()
            self.assertEqual(self.confirm(proposal).status_code,200);self.assertEqual(self.state(),before);self.assertEqual(AuditEvent.objects.count(),count+1);task.refresh_from_db();self.assertEqual(task.archived_at is not None,desired)

    def test_employee_archive_and_reassignment_revalidate_after_real_row_writer(self):
        task,_,_=self.create();proposal=self.preview({'action':'update_task','task_id':task.pk,'assignee_id':self.other.pk,'reason':'Призначення перед конкурентним архівом'})
        barrier=threading.Barrier(2)
        def worker(kind):
            connections.close_all();client=Client(enforce_csrf_checks=True,raise_request_exception=False);client.cookies=deepcopy(self.http.cookies)
            try:
                barrier.wait(timeout=10)
                response=self.confirm(proposal,client) if kind==0 else client.delete(f'/api/employees/{self.other.pk}/',HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
                return {'status':response.status_code,'body':response.content.decode()}
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(worker,range(2)))
        self.assertIn(responses[0]['status'],(200,409,422),responses);self.assertIn(responses[1]['status'],(204,409),responses)
        task.refresh_from_db();self.assertEqual(task.assignee_employee_id,self.other.pk if responses[0]['status']==200 else self.employee.pk)
        self.assertEqual(AuditEvent.objects.filter(task=task).count(),2 if responses[0]['status']==200 else 1)
        if responses[0]['status']!=200:
            retry=self.confirm(proposal);self.assertEqual(retry.status_code,409);self.assertEqual(retry.json()['code'],'proposal_stale')
        else:self.assertEqual(self.confirm(proposal).status_code,200)
        print('C01_TASK_PAIR '+json.dumps({'scenario':'employee_archive','responses':responses,'task_id':task.pk,'assignee_id':task.assignee_employee_id}))

    def test_uncommitted_confirm_recovery_is_not_false_authority_and_same_id_retries(self):
        task,_,_=self.create();proposal=self.preview({'action':'update_task','task_id':task.pk,'title':'Зміна видима тільки після commit','reason':'Перевірка паралельного outcome'})
        held=threading.Event();finish=threading.Event();result=[]
        def worker():
            connections.close_all();client=Client(enforce_csrf_checks=True,raise_request_exception=False);client.cookies=deepcopy(self.http.cookies)
            try:
                with transaction.atomic():
                    response=self.confirm(proposal,client);result.append((response.status_code,response.json()));held.set()
                    if not finish.wait(10):raise RuntimeError('Synthetic release deadline missed')
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(worker)
            try:
                self.assertTrue(held.wait(10));self.assertEqual(result[0][0],200,result)
                outcome=self.http.get('/api/operations/task-proposals/'+proposal['id']+'/');self.assertEqual(outcome.status_code,200,outcome.content);self.assertEqual(outcome.json()['state'],'pending');self.assertIsNone(outcome.json()['receipt']);task.refresh_from_db();self.assertEqual(task.title,'Перевірити фактичний результат')
            finally:finish.set();future.result(timeout=10)
        self.assertEqual(self.confirm(proposal).json(),result[0][1]);self.assertEqual(AuditEvent.objects.filter(task=task).count(),2)
