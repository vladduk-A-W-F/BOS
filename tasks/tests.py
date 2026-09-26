"""Seven original task use cases through the accepted C01 command boundary."""
from scripts.check_support import login_test_client
from datetime import date,timedelta
from rest_framework.test import APIClient
from django.test import TestCase
from employees.models import Employee
from operations.models import ActionProposal,AuditEvent,Configuration
from .models import Task

class TaskAPITestCase(TestCase):
    def setUp(self):
        self.client=APIClient();login_test_client(self.client)
        self.employee=Employee.objects.create(full_name='Іванов О.',role='Відповідальний')
        Configuration.objects.create(key='dataset',value={'as_of':str(date.today())})
    def preview(self,**payload):return self.client.post('/api/operations/preview/',payload,format='json')
    def execute(self,**payload):
        response=self.preview(**payload);self.assertEqual(response.status_code,200,response.content)
        response=self.client.post('/api/operations/confirm/',{'proposal_id':response.json()['id'],'confirmed':True},format='json');self.assertEqual(response.status_code,200,response.content);return response
    def create_payload(self,**fields):return {'action':'create_task','title':'Підготувати звіт','assignee_id':self.employee.pk,'deadline':str(date.today()+timedelta(days=5)),**fields}
    def test_create_task(self):
        raw=self.client.post('/api/tasks/',{'title':'Підготувати звіт'},format='json');self.assertEqual(raw.status_code,403);self.assertEqual(raw.data['code'],'approval_required');self.assertEqual(Task.objects.count(),0)
        resp=self.execute(**self.create_payload(priority='high'));self.assertEqual(Task.objects.count(),1);task=Task.objects.get(pk=resp.json()['task_id']);self.assertEqual(task.title,'Підготувати звіт');self.assertEqual(task.priority,'high');self.assertEqual(task.assignee_employee_id,self.employee.pk);self.assertEqual(AuditEvent.objects.count(),1)
    def test_title_too_short_rejected(self):
        resp=self.preview(**self.create_payload(title='ab'));self.assertEqual(resp.status_code,422);self.assertEqual(Task.objects.count(),0);self.assertEqual(ActionProposal.objects.count(),0)
    def test_deadline_in_past_rejected_for_new_task(self):
        resp=self.preview(**self.create_payload(title='Прострочений дедлайн',deadline=str(date.today()-timedelta(days=1))));self.assertEqual(resp.status_code,422);self.assertEqual(Task.objects.count(),0);self.assertEqual(ActionProposal.objects.count(),0)
    def test_deadline_in_past_allowed_for_update(self):
        task=Task.objects.create(title='Існуюча задача',deadline=date.today());past=date.today()-timedelta(days=2)
        resp=self.execute(action='update_task',task_id=task.pk,deadline=str(past),reason='Строк виправлено за фактичним джерелом');self.assertEqual(resp.status_code,200);task.refresh_from_db();self.assertEqual(task.deadline,past);self.assertTrue(any(row['field']=='is_overdue' and row['after'] is True for row in resp.json()['impact']));self.assertEqual(AuditEvent.objects.count(),1)
    def test_priority_none_normalized(self):
        resp=self.execute(**self.create_payload(title='Без пріоритету',priority='none'));self.assertEqual(resp.status_code,200);self.assertIsNone(Task.objects.get(pk=resp.json()['task_id']).priority)
    def test_filter_and_search(self):
        Task.objects.create(title='Звіт для фінансів',category='Фінанси',status='active');Task.objects.create(title='Зустріч',category='Операції',status='done')
        by_status=self.client.get('/api/tasks/',{'status':'active'}).data;self.assertEqual(len(by_status),1)
        by_search=self.client.get('/api/tasks/',{'search':'для'}).data;self.assertEqual(len(by_search),1)
        other=Employee.objects.create(full_name=self.employee.full_name,role='Інша особа');one=self.execute(**self.create_payload());two=self.execute(**self.create_payload(assignee_id=other.pk))
        self.assertEqual({r['id'] for r in self.client.get('/api/tasks/',{'search':'Іванов'}).data},{one.json()['task_id'],two.json()['task_id']});self.assertEqual([r['id'] for r in self.client.get('/api/tasks/',{'assignee_id':str(other.pk)}).data],[two.json()['task_id']])
    def test_delete_task(self):
        task=Task.objects.create(title='На видалення');resp=self.client.delete(f'/api/tasks/{task.id}/');self.assertEqual(resp.status_code,403);self.assertEqual(resp.data['code'],'approval_required');self.assertEqual(Task.objects.count(),1)
        self.execute(action='update_task',task_id=task.pk,archived=True,reason='Прибрати з робочого списку');self.assertEqual(self.client.get('/api/tasks/').data,[]);self.assertEqual(Task.objects.count(),1);self.assertEqual(self.client.get('/api/tasks/',{'archived':'true'}).data[0]['id'],task.pk)
        self.execute(action='update_task',task_id=task.pk,archived=False,reason='Повернути до робочого списку');self.assertEqual(self.client.get('/api/tasks/').data[0]['id'],task.pk);self.assertEqual(Task.objects.get(pk=task.pk).title,'На видалення');self.assertEqual(AuditEvent.objects.filter(task=task).count(),2)
