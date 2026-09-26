from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display=['title','status','priority','assignee','deadline','category','archived_at']
    list_filter=['status','priority','category','archived_at'];search_fields=['title','assignee','assignee_employee__full_name'];ordering=['-created_at']
    readonly_fields=tuple(field.name for field in Task._meta.fields)
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
    def get_actions(self,request):return {}
