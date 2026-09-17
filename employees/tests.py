from scripts.check_support import login_test_client
from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from .models import Employee


class EmployeeAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        login_test_client(self.client)

    def test_create_employee(self):
        resp = self.client.post('/api/employees/', {
            'full_name': 'Олексій Іванов', 'role': 'Заступник директора',
            'department': 'Управління', 'kpi': 87,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Employee.objects.count(), 1)

    def test_name_too_short_rejected(self):
        resp = self.client.post('/api/employees/', {'full_name': 'Аб'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kpi_out_of_range_rejected(self):
        resp = self.client.post('/api/employees/', {
            'full_name': 'Тест Тестович', 'role': 'Бухгалтер', 'kpi': 150,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_birthday_in_future_rejected(self):
        resp = self.client.post('/api/employees/', {
            'full_name': 'Тест Тестович', 'role': 'Бухгалтер',
            'birthday': str(date.today() + timedelta(days=365)),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_and_filter(self):
        Employee.objects.create(full_name='Марія Петренко', role='Директор', department='Фінанси')
        Employee.objects.create(full_name='Василь Сидоренко', role='Менеджер', department='Операції')
        by_dept = self.client.get('/api/employees/', {'department': 'Фінанси'}).data
        self.assertEqual(len(by_dept), 1)
        by_search = self.client.get('/api/employees/', {'search': 'Петренко'}).data
        self.assertEqual(len(by_search), 1)

    def test_delete_employee(self):
        emp = Employee.objects.create(full_name='На видалення', role='Стажер')
        resp = self.client.delete(f'/api/employees/{emp.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # A05: DELETE archives the same row; financial history must survive.
        self.assertEqual(Employee.objects.count(), 1)
        emp.refresh_from_db()
        self.assertIsNotNone(emp.archived_at)
