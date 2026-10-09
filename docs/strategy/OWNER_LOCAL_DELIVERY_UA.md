# Доставка owner-local локальною сесією Claude

Картку виконує сесія Claude на ПК власника.

**Дозвіл власника:** «ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ» (27.09) і «Переводи всю работу на себя все разрешаю ты главный теперь в проекте» (09.10.2026).

**Процедура** — кроки 2–9 `DEV10_INSTALL_UA.md`; тут точні команди.

**Заборонено:**
- init, seed, reset, flush, генерація пароля;
- зміна прав і запуск від адміністратора;
- автоматичні повтори.

Демо 1.0 не перемикати, ключі MCP не видавати. Секрети, паролі й рядки БД не виводити.

## Поточна доставка
- **Встановлено:** `9748b86`, версія `0.4.0-dev.1`.
- **Ціль:** main з версією `0.4.0-dev.2`. Точний SHA взяти на старті (`git rev-parse origin/main`) і записати в квитанцію.
- **Нові міграції від `9748b86`:** лише `connectors.0003_connector_url_kind`. Вона змінює тільки стан Django, `sqlmigrate` порожній.

## Підготовка (один раз)
- **Клієнт.** Claude Desktop або Claude Code CLI.
- **Робоча тека.** Сесію запускати в окремому клоні main, наприклад `D:/3/BOSDev/claude-work/BOS`, а не в копії-джерелі owner-local. Копія-джерело має лишатися чистою Git-копією, інакше `start` відмовить.
- **PowerShell** — звичайний, не «від адміністратора». Політику виконання не змінювати: команди викликаються напряму через Python.

```powershell
$Py   = 'D:/3/BOSDev/venv/Scripts/python.exe'
$Root = 'D:/3/BOSDev/local-bos3/owner'
```

## Кроки
1. **Поточний стан (лише читання).**
   - З `$Root/state/prepared.json` взяти `source` (далі `$Old`) і `source_sha256`.
   - Виконати: `cd $Old; & $Py -X utf8 -B -m scripts.bos3_delivery_preflight --root $Root --source $Old --source-sha256 <sha>`.
   - Очікується `"preflight": "PASS"`. Інакше — стоп і звіт.
2. **Нова копія-джерело.** Створити `$New` поруч із `$Old`, не всередині `$Root`:
   - `gh repo clone vladduk-A-W-F/BOS $New -- -c core.autocrlf=false`;
   - `git -C $New checkout --detach <sha>`;
   - `git -C $New status --porcelain` має бути порожнім;
   - дайджест: `cd $New; & $Py -X utf8 -B -c "from pathlib import Path; from scripts.bos3_local import digest_source; print(digest_source(Path.cwd().resolve()))"`.
3. **Зупинка.**
   - `& $Py -X utf8 -B $Old/scripts/bos3_local.py stop --root $Root`.
   - Потім `status`: процесу немає, порт 8030 вільний.
4. **Резервна копія.** Створити новий каталог у `$Root/backups/`; він успадковує захищені ACL `$Root`, перевірити через `Get-Acl`:
   ```python
   import datetime, hashlib, json, shutil, sqlite3
   from pathlib import Path
   root = Path('D:/3/BOSDev/local-bos3/owner')
   dest = root / 'backups' / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-0.4.0-dev.2')
   dest.mkdir(parents=True)
   src = sqlite3.connect(root.joinpath('data', 'bos3-fasteners.sqlite3').as_uri() + '?mode=ro', uri=True)
   dst = sqlite3.connect(dest / 'bos3-fasteners.sqlite3')
   src.backup(dst); src.close()
   assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'; dst.close()
   shutil.copytree(root / 'media', dest / 'media')
   state = ('prepared.json', 'owner-access.json', 'runtime-secrets.json')
   for name in state:
       shutil.copy2(root / 'state' / name, dest / name)
   sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
   assert all(sha(p) == sha(dest / 'media' / p.relative_to(root / 'media'))
              for p in (root / 'media').rglob('*') if p.is_file())
   assert all(sha(root / 'state' / n) == sha(dest / n) for n in state)
   manifest = {p.relative_to(dest).as_posix(): sha(p) for p in sorted(dest.rglob('*')) if p.is_file()}
   (dest / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
   print(dest, len(manifest), 'files')
   ```
5. **Міграції.**
   - На копії БД отримати список застосованих: `SELECT app || '.' || name FROM django_migrations`.
   - Порівняти з файлами `*/migrations/0*.py` у `$New`.
   - Якщо бракує лише `connectors.0003`, застосувати з `$New` (`cd $New`, `& $Py -X utf8 -B -c "..."`):
     ```python
     from pathlib import Path
     from scripts import bos3_local as L
     paths = L.instance_paths(Path('D:/3/BOSDev/local-bos3/owner'))
     secret = L.read_json(paths['runtime_secrets'])['django_secret']
     L.managed(['migrate', '--noinput'], L.environment(paths, Path.cwd().resolve(), secret), paths)
     ```
     Вивід потрапляє в `$Root/logs/migrate.log`.
   - Якщо бракує інших міграцій, переглянути `sqlmigrate` кожної:
     - лише нові таблиці чи індекси — застосувати так само;
     - будь-яка зміна чи видалення наявних таблиць — стоп, потрібен окремий план.
6. **Прив'язка.** Виконати з `$New`:
   `& $Py -X utf8 -B -c "from pathlib import Path; from scripts.bos3_prepared_update import update_prepared_source as u; from scripts.bos3_local import digest_source as d; s = Path.cwd().resolve(); u(Path('D:/3/BOSDev/local-bos3/owner/state/prepared.json'), str(s), d(s))"`.
7. **Старт.**
   - `& $Py -X utf8 -B $New/scripts/bos3_local.py start --root $Root`.
   - Потім `status`: процес працює.
8. **Перевірка.**
   - `http://127.0.0.1:8030/`: у заголовку сторінки `0.4.0-dev.2`.
   - `/api/auth/csrf/` відповідає 200, `/mcp/` — 404: MCP вимкнено, бо ключів немає.
   - Порівняти живу БД (лише читання) з копією:
     - кількість рядків у кожній таблиці однакова, крім `django_migrations` (+1) і `django_session`;
     - хеш пароля власника в `auth_user` однаковий (перевіряти без виводу);
     - прогрес не змінився;
     - хеші media збігаються.
   - Власник входить своїм логіном і бачить «Моніторинг» із бенто-плитками.
9. **Розбіжність** на будь-якому кроці після 3:
   - `stop`, зберегти діагностику;
   - відновити з копії БД (через `sqlite3` backup у зворотному напрямку), media і `prepared.json`;
   - запустити старою копією й перевірити;
   - написати звіт. Успіх не оголошувати.

## Квитанція
Зберегти `D:/3/BOSDev/qa-scratch/delivery-<версія>-<дата>/RECEIPT.json`. У ній:
- SHA і дайджест джерела, шлях `$New`;
- шлях резервної копії, кількість її файлів і байтів;
- застосовані міграції;
- результати кроку 8;
- exit code кожного кроку.

У Git потрапляють лише посилання й SHA-256 квитанції. Звіт власнику — до 10 рядків.
