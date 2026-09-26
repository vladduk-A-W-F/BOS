from django.db import models
from django.conf import settings
from boss_project.archive import ArchiveModel


class Employee(ArchiveModel):
    """Real employee of the company — replaces hardcoded INIT_EMPLOYEES in the frontend.
    Department is a plain string for now (matching Task.category pattern);
    can migrate to a FK on a Department model later if needed."""

    command_fields = (*ArchiveModel.command_fields, 'user')

    # Full name in Ukrainian — "Олексій Іванов"
    full_name = models.CharField(max_length=200)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='employee')

    # Job title — "Заступник директора", "Фінансовий директор"
    role = models.CharField(max_length=100)

    # Department name — plain string for now ("Управління", "Фінанси", "IT")
    department = models.CharField(max_length=100, blank=True, db_index=True)

    # Optional birthday — used by the Birthdays section in frontend
    birthday = models.DateField(null=True, blank=True)

    # KPI score 0-100. Default 0 = not measured yet
    kpi = models.IntegerField(default=0)

    # Contact info — optional
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Branch assignment — nullable for backward compatibility with existing data
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='employees',
    )

    # Audit timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.role})"
