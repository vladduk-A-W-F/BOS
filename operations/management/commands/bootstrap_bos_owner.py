"""Create the first business owner in an empty, explicitly selected installation."""
import getpass
import sys
import warnings

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, OperationalError, transaction

from operations.models import AuditEvent, Configuration


MARKER = 'initial_business_owner'


class Command(BaseCommand):
    help = 'Створює першого керівника BoS лише в порожній робочій установці.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--password-stdin', action='store_true',
                            help='Прочитати один рядок пароля зі stdin замість прихованого запиту.')
        parser.add_argument('--allow-document-download', action='store_true',
                            help='Явно дозволити перегляд і завантаження доступних документів.')
        parser.add_argument('--allow-workspace-export', action='store_true',
                            help='Явно дозволити експорт доступного робочого контексту.')

    def _password(self, from_stdin):
        if from_stdin:
            if sys.stdin.isatty():
                raise CommandError('Для --password-stdin потрібний закритий канал вводу, а не термінал.')
            password = sys.stdin.readline(515)
            if password.endswith('\n'):
                password = password[:-1]
                if password.endswith('\r'):
                    password = password[:-1]
        else:
            if not sys.stdin.isatty():
                raise CommandError('Прихований ввід потребує термінала; для автоматизації використайте --password-stdin.')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', getpass.GetPassWarning)
                    password = getpass.getpass('Пароль нового керівника: ')
                    if password != getpass.getpass('Повторіть пароль: '):
                        raise CommandError('Паролі не збігаються; обліковий запис не створено.')
            except getpass.GetPassWarning:
                raise CommandError('Прихований ввід недоступний; пароль не прочитано. Використайте захищений stdin.') from None
        if not 1 <= len(password) <= 512:
            raise CommandError('Пароль має містити від 12 до 512 символів.')
        return password

    def _require_empty(self, marker):
        # Permission and ContentType rows are produced by migrate on an empty
        # database. Every other managed model, including users, groups, sessions,
        # archived business data and configuration, must still be empty.
        for model in sorted(apps.get_models(), key=lambda m: m._meta.label_lower):
            if not model._meta.managed or model._meta.proxy:
                continue
            if model._meta.label_lower in {'auth.permission', 'contenttypes.contenttype'}:
                continue
            rows = model._base_manager.all()
            if model is Configuration:
                rows = rows.exclude(pk=marker.pk)
            if rows.exists():
                raise CommandError('Установка вже містить облікові записи або дані. Початкове створення заборонено.')

    def handle(self, *args, **options):
        if getattr(settings, 'BOS_DATA_MODE', None) != 'working':
            raise CommandError('Початковий керівник дозволений лише для явно вибраної робочої установки (BOS_DATA_MODE=working).')
        user_model = get_user_model()
        user = user_model(username=user_model.normalize_username(options['username']))
        try:
            user.username = user_model._meta.get_field('username').clean(user.username, user)
            password = self._password(options['password_stdin'])
            # Local/server profiles intentionally have no implicit global
            # password-validator defaults. The bootstrap baseline always applies;
            # any explicitly configured project validators apply as well.
            validators = [
                password_validation.UserAttributeSimilarityValidator(),
                password_validation.MinimumLengthValidator(min_length=12),
                password_validation.CommonPasswordValidator(),
                password_validation.NumericPasswordValidator(),
                *password_validation.get_default_password_validators(),
            ]
            password_validation.validate_password(password, user, validators)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages)) from None
        except (EOFError, KeyboardInterrupt):
            raise CommandError('Ввід скасовано; обліковий запис не створено.') from None

        grants = []
        if options['allow_document_download']:
            grants += ['view_document', 'download_document']
        if options['allow_workspace_export']:
            grants.append('export_workspace')
        try:
            with transaction.atomic():
                # Insert before any database reads: the unique key serializes
                # bootstrap invocations in PostgreSQL and obtains SQLite's writer
                # lock. A failed attempt rolls back the marker with every change.
                marker = Configuration.objects.create(key=MARKER, value={})
                Configuration.objects.select_for_update().get(pk=marker.pk)
                self._require_empty(marker)
                permissions = list(Permission.objects.filter(
                    content_type__app_label='operations', content_type__model='document',
                    codename__in=grants))
                if {p.codename for p in permissions} != set(grants):
                    raise CommandError('Права документів відсутні. Спочатку виконайте всі міграції цієї установки.')
                user.is_active = True
                user.is_staff = False
                user.is_superuser = False
                user.set_password(password)
                user.save(force_insert=True)
                user.groups.add(Group.objects.create(name='ceo'))
                user.user_permissions.set(permissions)
                password_validation.password_changed(password, user, validators)
                marker.value = {'schema': 1, 'user_id': user.pk, 'role': 'ceo',
                                'permissions': sorted(grants)}
                marker.save(update_fields=['value'])
                AuditEvent.objects.create(action='identity.bootstrap_owner', payload={
                    **marker.value, 'source': 'management_command',
                })
        except (IntegrityError, OperationalError):
            # Do not leak backend errors, SQL, usernames or secret input. There
            # is no automatic retry/cleanup that could replace an existing owner.
            raise CommandError('Керівника не створено: установка вже ініціалізована, зайнята або база недоступна. Дані не перезаписано.') from None
        self.stdout.write(self.style.SUCCESS(
            'Першого керівника BoS створено. Технічні права адміністратора не надано.'))
