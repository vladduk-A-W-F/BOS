# Авторський висновок для root — A09 install/provision/lifecycle

У межах локального Linux amd64 стенду погоджую fixed installer/provisioner незалежного reviewer та final lifecycle кандидат. Concrete blockers, відтворені у цьому циклі, усунені; новий scope не відкривається.

- Installer/provisioner review: source↔registry disjoint до записів; завершену інсталяцію не перевстановлює resume; усі звичайні descendants runtime мають nlink=1; isolated `-I` bootstrap не виконує пакетні venv.py/pip.py; offline `--no-deps --only-binary=:all:` не підтягує URL metadata; wheelhouse має бути наявним каталогом. Незалежні 7+9 методів green прочитано. Фактичний новий complete application provision із усіма 33 pins після цих виправлень виконано у нашому mixed proof.
- Lifecycle: trusted registry + UUID + root/DB/runtime inode + точні configbytes + full release SHA; бізнес-медіа залишається mutable; executable venv без сторонніх hardlinks; foreground instance OS lock; жоден PID marker не дає права завершувати процес.
- Реальні процеси pinned Waitress/Caddy та перевірений TLS; missing TLS, duplicate instance, foreign company ID, зайнятий порт дають відмову. SIGTERM прибирає лише own Popen children; нормальні exit codes 0 без force. Restart зберігає бізнес-файли.
- Proxy stdout/stderr записуються виключно через allowlist normalizer; 65 actual lines перевірено, URI/header canary не збережений. Жодного raw fallback.
- Доведений ready race проти стороннього validTLS listener усунено власною Caddy startup Event перед health та recheck дітей. Red фактичний з першої спроби; final exact candidate дав 3/3 відмови без ready, чужий listener лишився живий, positive own HTTPS/duplicate/clean stop пройшли.

Точні шляхи/SHA у `A09_LIFECYCLE_FROZEN_MANIFEST.json`. Інтеграцію та canonical fullverify виконує root. Наші докази не підтверджують Windows, PostgreSQL, публічне розгортання, зовнішній домен, оновлення, backup/restore або реліз усієї A09/A10 системи. Усі тестові дочірні процеси зупинено; checkout та оригінальні БД цей агент не змінював.
