from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Employee
from .serializers import EmployeeSerializer
from boss_project.archive import ArchiveViewSetMixin
from boss_project.policy import Policy
from rest_framework.exceptions import PermissionDenied


class EmployeeViewSet(ArchiveViewSetMixin, viewsets.ModelViewSet):
    """Full CRUD over Employee — same pattern as TaskViewSet, plus search & ordering.
    filter by department, search by name/role, sort by any field."""
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    # We list ALL three backends explicitly. The global default in settings.py has
    # only DjangoFilterBackend — and setting filter_backends here OVERRIDES that global,
    # so we must re-include DjangoFilterBackend or ?department=IT would stop working.
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department']                 # ?department=IT  — exact match
    search_fields = ['full_name', 'role']             # ?search=Іванов  — partial text search
    ordering_fields = ['full_name', 'kpi', 'birthday', 'created_at']  # ?ordering=-kpi

    def filter_queryset(self, queryset):
        requested = self.request.query_params.get('ordering', '')
        if not Policy(self.request).ceo and any(field.lstrip('-') != 'full_name' for field in requested.split(',') if field):
            raise PermissionDenied('Для цієї ролі доступне сортування довідника за ім’ям.')
        return super().filter_queryset(queryset)
