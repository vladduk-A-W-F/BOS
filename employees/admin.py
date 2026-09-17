from django.contrib import admin
from .models import Employee
from boss_project.archive_admin import ArchiveAdmin


@admin.register(Employee)
class EmployeeAdmin(ArchiveAdmin):
    # list_display: columns in the table view at /admin/employees/employee/
    list_display = ['full_name', 'role', 'department', 'kpi', 'birthday', 'archived_at']
    # list_filter: sidebar chips to filter by department
    list_filter = ['department']
    # search_fields: search box at the top — matches name, role or email
    search_fields = ['full_name', 'role', 'email']
    # readonly_fields: created_at is auto-set — never editable by hand
    readonly_fields = ['created_at', 'archived_at', 'user']
