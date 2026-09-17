import django_filters
from .models import Task


class TaskFilterSet(django_filters.FilterSet):
    """Custom FilterSet for Task — adds date range filters on top of plain field filters.
    URL examples:
      ?deadline_after=2026-01-01           — задачі з дедлайном від цієї дати
      ?deadline_before=2026-12-31          — і навпаки до
      ?deadline_after=2026-06-01&deadline_before=2026-06-30  — діапазон
    Plain fields below work as exact match: ?status=active, ?priority=high.
    """
    deadline_after = django_filters.DateFilter(field_name='deadline', lookup_expr='gte')
    deadline_before = django_filters.DateFilter(field_name='deadline', lookup_expr='lte')

    class Meta:
        model = Task
        fields = ['status', 'priority', 'assignee', 'category']
