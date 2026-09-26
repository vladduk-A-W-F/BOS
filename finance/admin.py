from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from uuid import uuid4
from .models import Counterparty, Contract, Transaction, Salary
from .commands import (save_salary, save_transaction, intent_key, replay_create,
                       FinancialIntentConflict, SALARY_FIELDS, TRANSACTION_FIELDS)
from boss_project.archive_admin import ArchiveAdmin

admin.site.register(Counterparty)
admin.site.register(Contract)


class FinancialIntentForm(forms.ModelForm):
    bos_operation_id = forms.CharField(widget=forms.HiddenInput, initial=uuid4, required=False)

    def clean_bos_operation_id(self):
        value = self.cleaned_data.get('bos_operation_id')
        return intent_key(value, required=True) if self.instance.pk is None else value


class FinancialAdmin(ArchiveAdmin):
    form = FinancialIntentForm

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # A committed Salary intent must be replayable before ModelForm rejects
        # its employee/period as a duplicate new accrual. Only typed form fields
        # are compared, and no command executes during form validation.
        if request.method == 'POST' and object_id is None and self.has_add_permission(request):
            try:
                token = intent_key(request.POST.get('bos_operation_id'), required=True)
                form = self.get_form(request)(data=request.POST)
                allowed = SALARY_FIELDS if self.model is Salary else TRANSACTION_FIELDS
                values = {name: form.fields[name].clean(form[name].data)
                          for name in allowed if name in form.fields}
                previous = replay_create(self.model, values, actor=request.user, operation_id=token)
                if previous is not None:
                    self.message_user(request, 'Цей намір уже збережено. Повторний фінансовий запис не створено.')
                    return HttpResponseRedirect(reverse(f'admin:finance_{self.model._meta.model_name}_change', args=[previous.pk]))
            except FinancialIntentConflict as exc:
                return HttpResponse('; '.join(exc.messages), status=409, content_type='text/plain; charset=utf-8')
            except ValidationError:
                # The normal form reports malformed or missing fields.
                pass
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(Transaction)
class TransactionAdmin(FinancialAdmin):
    list_display = ['date', 'direction', 'amount', 'currency', 'category', 'archived_at']
    readonly_fields = ['created_at', 'archived_at']

    def save_model(self, request, obj, form, change):
        save_transaction(instance=obj, actor=request.user, operation_id=form.cleaned_data.get('bos_operation_id') if not change else None)


@admin.register(Salary)
class SalaryAdmin(FinancialAdmin):
    list_display = ['employee', 'period_year', 'period_month', 'amount', 'currency', 'status', 'archived_at']
    readonly_fields = ['created_at', 'archived_at']

    def save_model(self, request, obj, form, change):
        save_salary(instance=obj, actor=request.user, operation_id=form.cleaned_data.get('bos_operation_id') if not change else None)
