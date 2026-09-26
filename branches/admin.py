from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'code', 'type', 'parent', 'status', 'employee_count')
    list_editable = ('short_name',)
    list_filter = ('type', 'status')
    search_fields = ('name', 'short_name', 'code')
