from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from boss_project.identity import IdentityDenied
from connectors import mcp


class Command(BaseCommand):
    help = ('Ключі доступу ІІ-клієнтів до BoS через MCP (лише читання). Без жодного ключа доступ вимкнено. '
            'Ключ діє як вказаний користувач BoS і бачить те саме, що він; ключ показується один раз.')

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest='action', required=True)
        create = actions.add_parser('create', help='Видати новий ключ для користувача BoS.')
        create.add_argument('--user', required=True, help="Ім'я користувача BoS.")
        create.add_argument('--label', default='', help='Де використовується ключ, наприклад «Claude на ноутбуці».')
        actions.add_parser('list', help='Показати видані ключі (без самих ключів).')
        revoke = actions.add_parser('revoke', help='Відкликати ключ за його номером.')
        revoke.add_argument('id')

    def handle(self, *args, **options):
        if options['action'] == 'create':
            user = get_user_model().objects.filter(username=options['user']).first()
            if user is None:
                raise CommandError('Користувача не знайдено.')
            try:
                token, entry = mcp.issue(user, options['label'])
            except IdentityDenied as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f'Ключ {entry["id"]} для {user.username} ({entry["label"] or "без опису"}). '
                              'Збережіть його зараз — повторно він не показується:')
            self.stdout.write(token)
            self.stdout.write('Адреса MCP: <адреса BoS>/mcp/ , заголовок Authorization: Bearer <ключ>.')
        elif options['action'] == 'list':
            users = dict(get_user_model().objects.values_list('pk', 'username'))
            for entry in mcp.keys():
                self.stdout.write(f'{entry.get("id")}\t{users.get(entry.get("user_id"), "—")}\t'
                                  f'{entry.get("label", "")}\t{entry.get("created_at", "")}')
        elif not mcp.revoke(options['id']):
            raise CommandError('Ключ із таким номером не знайдено.')
        else:
            self.stdout.write('Ключ відкликано.')
