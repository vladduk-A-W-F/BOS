from rest_framework import serializers
from .models import Counterparty, Contract, Transaction, Salary
from .commands import save_salary, save_transaction, intent_key, FinancialIntentConflict
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, OperationalError
from rest_framework.exceptions import APIException
from boss_project.policy import ScopedSerializerMixin


class FinancialConflict(APIException):
    status_code = 409
    default_detail = 'Запис не завершено через конфлікт. Оновіть дані й повторіть дію.'


class FinancialCommandSerializer(ScopedSerializerMixin, serializers.ModelSerializer):
    def _save_command(self, instance, data):
        try:
            request = self.context.get('request')
            operation_id = intent_key(request.headers.get('Idempotency-Key'), required=True) if instance is None and request is not None else None
            return self.command(instance=instance, changes=data, actor=getattr(request, 'user', None), operation_id=operation_id)
        except FinancialIntentConflict as exc:
            raise FinancialConflict(detail=exc.messages) from exc
        except ModelValidationError as exc:
            raise serializers.ValidationError(getattr(exc, 'message_dict', {'non_field_errors': exc.messages})) from exc
        except (IntegrityError, OperationalError) as exc:
            raise FinancialConflict() from exc

    def create(self, validated_data):
        return self._save_command(None, validated_data)

    def update(self, instance, validated_data):
        return self._save_command(instance, validated_data)


class CounterpartySerializer(ScopedSerializerMixin, serializers.ModelSerializer):
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Counterparty
        fields = ['id', 'name', 'type', 'edrpou', 'phone', 'email', 'address', 'notes', 'is_active', 'created_at', 'total_debit', 'total_credit', 'balance']

    def get_total_debit(self, obj):
        return float(getattr(obj, 'total_debit', 0) or 0)

    def get_total_credit(self, obj):
        return float(getattr(obj, 'total_credit', 0) or 0)

    def get_balance(self, obj):
        return float(getattr(obj, 'total_debit', 0) or 0) - float(getattr(obj, 'total_credit', 0) or 0)


class ContractSerializer(ScopedSerializerMixin, serializers.ModelSerializer):
    counterparty_name = serializers.CharField(source='counterparty.name', read_only=True)

    class Meta:
        model = Contract
        fields = ['id', 'number', 'name', 'counterparty', 'counterparty_name', 'category', 'status', 'amount', 'currency', 'start_date', 'end_date', 'notes', 'created_at']


class TransactionSerializer(FinancialCommandSerializer):
    command = staticmethod(save_transaction)
    counterparty_name = serializers.CharField(source='counterparty.name', read_only=True, default=None)
    contract_number = serializers.CharField(source='contract.number', read_only=True, default=None)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)

    class Meta:
        model = Transaction
        fields = ['id', 'direction', 'amount', 'currency', 'date', 'description', 'category', 'counterparty', 'counterparty_name', 'contract', 'contract_number', 'branch', 'branch_name', 'created_at', 'archived_at']


class SalarySerializer(FinancialCommandSerializer):
    command = staticmethod(save_salary)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_role = serializers.CharField(source='employee.role', read_only=True)
    employee_dept = serializers.CharField(source='employee.department', read_only=True)

    class Meta:
        model = Salary
        # The shared command validates this constraint under its write lock.
        # Pre-command uniqueness would reject an already committed intent replay.
        validators = []
        fields = ['id', 'employee', 'employee_name', 'employee_role', 'employee_dept', 'amount', 'currency', 'period_year', 'period_month', 'payment_date', 'status', 'notes', 'transaction', 'created_at', 'archived_at']
