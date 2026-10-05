from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.conf import settings
from boss_project.identity import actor, IdentityDenied

class LocalRoleGuard:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        response=self.handle(request)
        if hasattr(request,'bos_access_revision'):
            response['X-BoS-Access']=request.bos_access_revision
        return response

    def handle(self,request):
        from finance.statement_views import pre_body
        rejected=pre_body(request)
        if rejected is not None:return rejected
        if request.path.startswith('/admin/') and request.user.is_authenticated:
            from django.contrib.auth import get_user_model
            from boss_project.identity import ROLES
            from employees.models import Employee
            user=get_user_model().objects.filter(pk=request.user.pk,is_active=True).first()
            if user and (user.groups.filter(name__in=ROLES).exists() or Employee.objects.filter(user_id=user.pk,archived_at__isnull=False).exists()):
                return JsonResponse({'error':'Адміністрування потребує окремого технічного облікового запису з явно наданими правами.'},status=403)
        if request.path.startswith(settings.MEDIA_URL):
            # Raw media has no actor/object policy, even when DEBUG is enabled.
            return JsonResponse({'error':'Сторінку не знайдено.'},status=404)
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        demo = settings.BOS_DATA_MODE == 'demo'
        if request.path in ('/api/operations/role/', '/api/auth/demo/') and not demo:
            return JsonResponse({'error':'Сторінку не знайдено.'}, status=404)
        if request.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
            guard=CsrfViewMiddleware(lambda r:None);guard.process_request(request)
            rejected=guard.process_view(request,lambda r:None,(),{})
            if rejected:return JsonResponse({'error':'Перевірка сесії не пройшла. Оновіть сторінку.'},status=403)
        public = {'/api/auth/csrf/', '/api/auth/login/', '/api/auth/logout/', '/api/auth/me/'}
        if demo:
            public |= {'/api/auth/demo/', '/api/operations/role/', '/api/operations/status/', '/api/runtime/status/', '/api/erp/showcase/'}
        if request.path in public and request.user.is_authenticated:
            # A public demo read still says which access revision it was computed for, so a signed-in
            # screen can tell fresh facts from a changed session (otherwise «Доручення» refuses the list).
            try:
                actor(request)
            except IdentityDenied:
                pass
            else:
                from boss_project.policy import Policy
                request.bos_access_revision=Policy(request).access_revision()
        if request.path not in public:
            try:
                principal = actor(request)
            except IdentityDenied as exc:
                response=JsonResponse({'error':str(exc),'code':'identity_denied'},status=exc.status)
                response['X-BoS-Identity']='denied'
                return response
            from boss_project.policy import Policy
            request.bos_access_revision=Policy(request).access_revision()
            resource=request.path.removeprefix('/api/').split('/')[0].split('.')[0]
            unsafe=request.method not in ('GET','HEAD','OPTIONS')
            if principal.role != 'ceo' and (resource=='salaries' or (resource=='transactions' and (principal.role=='observer' or unsafe)) or (resource=='employees' and unsafe)):
                return JsonResponse({'error':'Ці дані або дія недоступні для вашої ролі.'},status=403)
            training_progress = (request.method == 'POST' and resource == 'training'
                and request.path.startswith('/api/training/sessions/')
                and request.path.rstrip('/').split('/')[-1] in ('start', 'pause', 'navigate', 'check', 'tour'))
            if principal.role == 'observer' and request.method not in ('GET','HEAD','OPTIONS') and request.path != '/api/operations/chat/' and not training_progress:
                return JsonResponse({'error':'Спостерігач не може змінювати записи.'},status=403)
            ai_paths = ('/api/chat/','/api/chat/file/','/api/meeting/protocol/','/api/dictate/process/')
            if request.method == 'POST' and request.path in ai_paths:
                # C02 is deferred. A key alone must not enable the legacy
                # unscoped mutation adapter; the local reader remains active.
                return JsonResponse({'error':'Зовнішній ІІ-адаптер ще не підключений. Локальний помічник та інші розділи доступні.'},status=503)
        return self.get_response(request)
