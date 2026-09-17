from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse


class ArchiveAdmin(admin.ModelAdmin):
    delete_confirmation_template = 'admin/archive_confirmation.html'

    def get_deleted_objects(self, objs, request):
        # This is an archive confirmation, never Django's cascading collector.
        return [str(obj) for obj in objs], {str(self.model._meta.verbose_name_plural): len(objs)}, set(), []

    def delete_model(self, request, obj):
        obj.delete(actor=request.user)

    def delete_queryset(self, request, queryset):
        queryset.delete(actor=request.user)

    def response_delete(self, request, obj_display, obj_id):
        self.message_user(request, 'Запис архівовано. ID, джерела й фінансові підсумки збережено.', messages.SUCCESS)
        opts = self.model._meta
        return HttpResponseRedirect(reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist', current_app=self.admin_site.name))

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            # Keep the existing URL/action key: old clients cannot invoke a
            # physical deletion by replaying the old bulk action POST.
            actions['delete_selected'] = (type(self).archive_selected, 'delete_selected', 'Архівувати обрані записи')
        return actions

    @admin.action(permissions=['delete'], description='Архівувати обрані записи')
    def archive_selected(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        if request.POST.get('post'):
            self.delete_queryset(request, queryset)
            self.message_user(request, 'Обрані записи архівовано; історія та суми збережені.', messages.SUCCESS)
            return None
        return TemplateResponse(request, self.delete_confirmation_template, {
            **self.admin_site.each_context(request), 'title': 'Архівувати записи',
            'opts': self.model._meta, 'objects': queryset,
            'bulk_archive': True, 'action': 'delete_selected',
        })

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Model.clean supplies ordinary form errors. A race after validation is
        # rechecked by save_model's command and must roll back without a 500 or
        # a misleading successful redirect.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except (ValidationError, IntegrityError, OperationalError):
            return HttpResponse('Запис не збережено: дані змінилися або суперечать історії. Оновіть форму й повторіть дію.', status=409, content_type='text/plain; charset=utf-8')

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except (ValidationError, IntegrityError, OperationalError):
            return HttpResponse('Запис не архівовано через конфлікт. Історію збережено.', status=409, content_type='text/plain; charset=utf-8')

    def changelist_view(self, request, extra_context=None):
        try:
            return super().changelist_view(request, extra_context)
        except (ValidationError, IntegrityError, OperationalError):
            return HttpResponse('Обрані зміни не виконано через конфлікт. Історію збережено.', status=409, content_type='text/plain; charset=utf-8')
