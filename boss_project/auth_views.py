import json
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login as sign_in, logout as sign_out
from django.contrib.auth.models import Group, Permission
from django.db import transaction, models, IntegrityError, OperationalError
from django.http import JsonResponse
from django.middleware.csrf import rotate_token
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.views.decorators.http import require_GET, require_POST
from .identity import actor, actor_for_user, IdentityDenied, ROLES
from . import login_limit


def payload(request):
    if len(request.body) > 4096:
        raise ValueError('Запит завеликий.')
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError('Потрібен об’єкт запиту.')
    return data


@require_GET
@ensure_csrf_cookie
def csrf(request):
    from training.access import enabled
    return JsonResponse({'mode': settings.BOS_DATA_MODE, 'authenticated': request.user.is_authenticated,
                         'training_enabled': enabled()})


@require_POST
@csrf_protect
def login(request):
    try:
        data = payload(request)
        username, password = data.get('username'), data.get('password')
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 150 or len(password) > 512:
            raise ValueError('Вкажіть логін і пароль.')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Вкажіть коректні логін і пароль.'}, status=400)
    try:
        ticket, retry_after = login_limit.reserve(username, request.META.get('REMOTE_ADDR', ''))
    except (IntegrityError, OperationalError):
        ticket, retry_after = None, 1
    if ticket is None:
        response = JsonResponse({'error': 'Забагато невдалих спроб. Повторіть вхід за хвилину.'}, status=429)
        response['Retry-After'] = str(retry_after)
        return response
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({'error': 'Невірний логін або пароль.'}, status=401)
    try:
        principal = actor_for_user(user)
    except IdentityDenied as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)
    sign_in(request, user)
    request.session.pop('bos_role', None)
    request.session.pop('bos_demo_identity', None)
    login_limit.succeeded(ticket)
    return JsonResponse(principal.as_dict())


@require_POST
@csrf_protect
def logout(request):
    sign_out(request)
    rotate_token(request)
    return JsonResponse({'signed_out': True})


@require_GET
def me(request):
    try:
        return JsonResponse(actor(request).as_dict())
    except IdentityDenied as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)


@require_POST
@csrf_protect
def demo(request):
    from training.access import enabled
    if enabled():
        return JsonResponse({'error': 'У цій навчальній установці потрібен особистий вхід.'}, status=404)
    if settings.BOS_DATA_MODE != 'demo' or request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
        return JsonResponse({'error': 'Сторінку не знайдено.'}, status=404)
    try:
        role = payload(request).get('role', 'ceo')
        if role not in ROLES:
            raise ValueError('Оберіть навчальну роль.')
        from operations.models import Configuration
        with transaction.atomic():
            config, _ = Configuration.objects.get_or_create(key='demo_identities', defaults={'value': {}})
            Configuration.objects.filter(pk=config.pk).update(value=models.F('value'))
            config.refresh_from_db()
            known = config.value.get(role)
            user = get_user_model().objects.filter(pk=known).first() if known else None
            if known and user is None:
                raise IdentityDenied('Навчальний обліковий запис видалено. Потрібне відновлення демо.')
            if user is None:
                username = 'bos-demo-' + role
                if get_user_model().objects.filter(username=username).exists():
                    raise IdentityDenied('Навчальне ім’я зайняте іншим обліковим записом.')
                user = get_user_model().objects.create_user(username=username, password=None)
                user.groups.add(Group.objects.get_or_create(name=role)[0])
                capabilities=['view_document','download_document']
                if role in ('ceo','manager'):capabilities.append('export_workspace')
                user.user_permissions.add(*Permission.objects.filter(content_type__app_label='operations',content_type__model='document',codename__in=capabilities))
                config.value = {**config.value, role: user.pk}
                config.save(update_fields=['value'])
            if user.has_usable_password() or user.is_staff or user.is_superuser:
                raise IdentityDenied('Цей обліковий запис не є навчальним.')
            principal = actor_for_user(user)
            if principal.role != role:
                raise IdentityDenied('Повноваження навчального облікового запису змінено.')
            sign_in(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session.pop('bos_role', None)
            request.session['bos_demo_identity'] = True
        return JsonResponse(principal.as_dict())
    except IdentityDenied as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Оберіть навчальну роль.'}, status=400)
    except (IntegrityError, OperationalError):
        return JsonResponse({'error': 'Сесію ще не відкрито. Повторіть вхід.'}, status=409)
