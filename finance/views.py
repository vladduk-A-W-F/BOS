from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import IntegrityError, OperationalError
from boss_project.archive import ArchiveViewSetMixin
from django.db.models.deletion import ProtectedError
from boss_project.policy import Policy

from .models import Counterparty, Contract, Transaction, Salary
from .serializers import (
    CounterpartySerializer, ContractSerializer,
    TransactionSerializer, SalarySerializer,
)


class SourceProtectionMixin:
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({'error': 'Запис є джерелом фінансової історії. Його та пов’язані дані збережено.'}, status=409)


class CounterpartyViewSet(SourceProtectionMixin, viewsets.ModelViewSet):
    queryset = Counterparty.objects.with_totals()
    serializer_class = CounterpartySerializer


class ContractViewSet(SourceProtectionMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.select_related('counterparty').all()
    serializer_class = ContractSerializer

    def get_queryset(self):
        return Policy(self.request).contracts().select_related('counterparty')


class TransactionViewSet(ArchiveViewSetMixin, viewsets.ModelViewSet):
    @action(detail=False,methods=['get'])
    def summary(self,request,format=None):
        from .statement_reads import transaction_summary
        from .statement_csv import StatementError
        try:return Response(transaction_summary(request))
        except StatementError as exc:return Response({'error':str(exc),'code':exc.code},status=exc.status)

    queryset = Transaction.objects.select_related('counterparty', 'contract').all()
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Policy(self.request).transactions().select_related('counterparty', 'contract')


class SalaryViewSet(ArchiveViewSetMixin, viewsets.ModelViewSet):
    queryset = Salary.objects.select_related('employee', 'transaction').all()
    serializer_class = SalarySerializer

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None, format=None):
        """POST /api/salaries/{id}/pay/ — помітити зарплату виплаченою + авто-створити транзакцію-витрату."""
        salary = self.get_object()
        try:
            salary.mark_paid(request.data.get('payment_date'))
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except (IntegrityError, OperationalError):
            return Response({'error': 'Запис не завершено через конфлікт. Оновіть дані й повторіть погодження.'}, status=409)
        return Response(SalarySerializer(salary).data)
