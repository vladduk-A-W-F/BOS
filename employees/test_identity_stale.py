"""A03: a profile form read before linking must not erase the identity link."""
from django.contrib import admin
from django.test import RequestFactory
from employees.models import Employee
from employees.serializers import EmployeeSerializer
from employees.test_identity import IdentityBase


class IdentityStaleTests(IdentityBase):
    def test_stale_profile_serializer_preserves_explicit_user_link(self):
        employee = self.employee()
        stale = Employee.objects.get(pk=employee.pk)
        serializer = EmployeeSerializer(stale, data={'role': 'Інженер проєкту'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.link(self.manager, employee)
        serializer.save()
        employee.refresh_from_db()
        self.assertEqual(employee.user_id, self.manager.pk)
        self.me(self.login(self.manager), self.manager, 'manager', employee.pk)

    def test_stale_admin_profile_preserves_explicit_user_link(self):
        employee = self.employee()
        stale = Employee.objects.get(pk=employee.pk)
        model_admin = admin.site._registry[Employee]
        request = RequestFactory().post('/admin/employees/employee/')
        request.user = self.ceo
        form = model_admin.get_form(request, obj=stale)(data={
            'full_name': stale.full_name, 'role': 'Інженер проєкту', 'department': '',
            'birthday': '', 'kpi': '0', 'phone': '', 'email': '', 'branch': '',
        }, instance=stale)
        self.assertTrue(form.is_valid(), form.errors)
        candidate = model_admin.save_form(request, form, change=True)
        self.link(self.manager, employee)
        model_admin.save_model(request, candidate, form, change=True)
        employee.refresh_from_db()
        self.assertEqual(employee.user_id, self.manager.pk)
