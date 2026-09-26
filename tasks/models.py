from django.db import models


class Task(models.Model):
    # Lists of allowed values — Django validates these automatically
    PRIORITY_CHOICES = [
        ('high',   'High'),
        ('medium', 'Medium'),
        ('low',    'Low'),
    ]
    STATUS_CHOICES = [
        ('active',  'Active'),
        ('process', 'In process'),
        ('done',    'Done'),
        ('overdue', 'Overdue'),
    ]

    # The name of the task — short text, max 200 characters
    title = models.CharField(max_length=200)

    # Urgency level — 'high', 'medium', 'low', or NULL = "no priority".
    # null=True lets a task have no priority at all (e.g. auto-cleared when done).
    # New tasks still default to 'medium' unless explicitly set to none.
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', null=True, blank=True, db_index=True)

    # Current state of the task — one of the four values above
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', db_index=True)

    # Who the task is assigned to — plain string for now, ForeignKey later
    assignee = models.CharField(max_length=100, blank=True)

    # Due date — date only, no time (e.g. 2026-05-20); optional
    deadline = models.DateField(null=True, blank=True, db_index=True)

    # Task category — plain string for now (e.g. "Finance", "HR")
    category = models.CharField(max_length=50, blank=True)

    # Branch assignment — nullable for backward compatibility with existing data
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tasks',
    )

    # Set automatically when the task is first created — never edited manually
    created_at = models.DateTimeField(auto_now_add=True)

    assignee_employee = models.ForeignKey('employees.Employee', null=True, blank=True, on_delete=models.PROTECT, related_name='assigned_tasks')
    sales_order = models.ForeignKey('erp.SalesOrder', null=True, blank=True, on_delete=models.PROTECT, related_name='controlled_tasks')
    result = models.TextField(max_length=2000, null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    def __str__(self):
        # Django admin and shell will show the task title instead of "Task object (1)"
        return self.title