from datetime import date
from rest_framework import serializers
from .models import Employee
from boss_project.policy import ScopedSerializerMixin


class EmployeeSerializer(ScopedSerializerMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ['id', 'full_name', 'role', 'department', 'birthday', 'kpi', 'phone', 'email', 'branch', 'branch_name', 'created_at', 'archived_at']

    def validate_full_name(self, value):
        """Full name must be a real name — not 1-2 characters."""
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Ім'я повинно містити мінімум 3 символи.")
        return value

    def validate_kpi(self, value):
        """KPI is a percentage — 0 to 100 only. 150 makes no sense."""
        if value < 0 or value > 100:
            raise serializers.ValidationError("KPI повинен бути від 0 до 100.")
        return value

    def validate_birthday(self, value):
        """Birthday can't be in the future — a person not yet born can't be an employee."""
        if value and value > date.today():
            raise serializers.ValidationError("Дата народження не може бути в майбутньому.")
        return value
