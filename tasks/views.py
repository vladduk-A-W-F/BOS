from django.db.models import Q
from rest_framework import viewsets,status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter,OrderingFilter
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,NotFound
from django_filters.rest_framework import DjangoFilterBackend
from boss_project.policy import Policy
from .models import Task
from .serializers import TaskSerializer
from .filters import TaskFilterSet
from .queries import overdue_q

class TaskViewSet(viewsets.ModelViewSet):
    queryset=Task.objects.all();serializer_class=TaskSerializer
    filter_backends=[DjangoFilterBackend,SearchFilter,OrderingFilter];filterset_class=TaskFilterSet
    search_fields=['title','assignee','assignee_employee__full_name','category'];ordering_fields=['title','priority','status','deadline','created_at']
    def get_queryset(self):
        rows=Policy(self.request).tasks().select_related('assignee_employee','sales_order','branch')
        if self.action!='list':return rows
        for key in ('archived','overdue','assignee_id'):
            if len(self.request.query_params.getlist(key))>1:raise ValidationError({key:'Повторний параметр.'})
        archived=self.request.query_params.get('archived','false')
        if archived not in ('true','false'):raise ValidationError({'archived':'Потрібно true або false.'})
        rows=rows.filter(archived_at__isnull=archived=='false')
        if 'overdue' in self.request.query_params:
            value=self.request.query_params['overdue']
            if value not in ('true','false'):raise ValidationError({'overdue':'Потрібно true або false.'})
            rows=rows.filter(overdue_q()) if value=='true' else rows.exclude(overdue_q())
        if 'assignee_id' in self.request.query_params:
            value=self.request.query_params['assignee_id']
            if not value.isascii() or not value.isdigit() or len(value)>19 or not 0<int(value)<=9223372036854775807:raise ValidationError({'assignee_id':'Потрібен позитивний ID.'})
            rows=rows.filter(assignee_employee_id=int(value))
        return rows
    def approval_required(self,*args,**kwargs):return Response({'code':'approval_required','error':'Зміни доручень потребують попереднього перегляду та погодження.'},status=403)
    create=approval_required;update=approval_required;partial_update=approval_required;destroy=approval_required
    @action(detail=True,methods=['get'])
    def history(self,request,pk=None,format=None):
        self.get_object()
        from .history import page
        try:return Response(page(request,int(pk)))
        except ValueError as exc:raise ValidationError(str(exc))
