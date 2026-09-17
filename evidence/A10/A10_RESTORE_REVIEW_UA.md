# A10 — незалежний огляд native capture та чистого відновлення

Дата: 12.09.2026. Рецензент: `/root/a09_server_review`.

**Висновок: вузький консенсус для фактичного capture під живою lease та clean restore лише в нову інсталяцію. Знайдений блокер фінальної готовності виправлено й перевірено red → green. A10, generation activation, upgrade та rollback загалом не прийняті.**

Прочитано реалізацію, фактичні JSON-звіти й fixture коду їх отримання. Checkout та вихідні бази цим оглядом не змінювалися. Нових запусків або boundary probes не виконували. Висновок щодо control/adapter збережено окремо в `tmp/A10_INPROCESS_REVIEW_UA.md`; історію backup defects збережено в `tmp/A10_BACKUP_REVIEW_UA.md`.

## Точні версії

| Частина | SHA256 |
|---|---|
| Backup, актуальна версія й фактичний capture | `27430b053bf714b09b89214278454144b6587040754f0db8d1d79f874e0cbed8` |
| Restore, початковий повний позитивний прогін | `c3d4dba5051a4ca7b739192944ecb0c6bcbf7f9821f1b37f296e22537a7bdfaf` |
| Restore, фінальна правка late admission | `baaf64239df69dd0a2c19bcab7b67044af3ad19cd9790f7d95e0b47f5b323eb0` |
| Ledger, тільки перевірена FS/current-owned частина | `b68298be377367ae8bfcddd3ec44cfff446dcd9dc0698864a9a822ea6b8df3f1` |

Шлях backup/restore: `tmp/a10_backup_draft/scripts/`. Ledger: `tmp/a10_generation_ledger_draft.py`. Management coordinator у прогоні завантажений із цих окремих перевірених файлів; versioned worker використовує Python/code фактичної immutable release BoS 0.2.10-dev. Це важлива межа доказу: management модулі ще не перевірялися як частина інтегрованого checkout package.

## Що підтверджує код

Capture вимагає видані `GenerationLedger` та `QuiescenceLease` і виконується всередині `fenced_for` з утриманням owner RLock. `current_owned/assert_owned` повторно звіряють registry/root/config/source та файлову authority anchor. FS capability зареєстрована в поточному процесі, прив’язана до незмінних полів; ledger flock неблокувальний. Огляд цього коду не приймає методи activation або candidate-generation workflow.

Backup створюється лише в новому приватному каталозі, поза installation/registry/code. Зберігає native SQLite, точні code/config/static та всі приватні файли, включно з orphan і порожніми каталогами. Native snapshot створюється API активної версії; sealed snapshot перевіряється typed validator, source files перевіряються до/після. Відомі API-помилки попередніх draft усунені. COMPLETE публікується тільки після перевірок; helper прибирає лише власний marker inode при контрольованих I/O failures.

Restore відмовляє для існуючого target і не має resume. Нову інсталяцію створює цей самий виклик; далі утримується її instance lock, а readiness позначається false. Worker перевіряє відсутність business rows, users/groups/sessions і sidecars; записує лише у вже створений власний порожній DB inode. Нова DB має точні bytes native snapshot, typed schema/rows/sequences/media; code/static і backup inventory звіряються. Нові installation UUID, secret та namespace cookies не змінюють збережені identities/history у snapshot. Старі підписані cookies не заявляються як придатні до входу в нову установку.

## Знайдений блокер та його закриття

У restore `c3d4dba…` `application_provisioned=True` і `restore.complete=True` публікувалися перед фінальним `load_owned`. Пізня відмова могла повернути помилку, залишивши readiness true. Це суперечило правилу «невдалий target не запускається».

У `baaf642…` final admission обгорнуто try/except. Поки instance lock ще утримується, будь-яка пізня відмова відкликає обидві readiness ознаки й записує `late_admission_failed=True`; лише потім виняток виходить назовні. Інший керований запуск не може потрапити між publication та revoke під цим lifetime lock.

Фактичні `tmp/A10_RESTORE_LATE_BEFORE.json` та `tmp/A10_RESTORE_LATE_AFTER.json`, разом із прочитаним `tmp/a10_restore_late_probe.py`, підтверджують вузький red → green. Виконувалися реальні provision, media/native copy і typed verification у нові власні target; ін’єкція лише `OSError` другого, фінального `load_owned`. BEFORE: відмова з true/true. AFTER: відмова з false/false. Це контрольований failure-path proof; загальні crash/power-loss гарантії ним не заявляються.

## Фактичні результати основного прогону

`tmp/A10_NATIVE_CAPTURE_RESULT.json` і fixture `tmp/a10_native_capture_probe.py`: **8 сценаріїв пройдено**.

| Сценарій | Фактичний результат |
|---|---|
| Оригінальна власна установка | HTTPS login та exact document SHA. |
| Зупинка й capture | Фактична lease, native snapshot, 2 private files включно з orphan; 4,804 с. |
| Пошкоджена окрема копія backup | Відмова. |
| Restore в існуючу установку | Відмова без записів. |
| Нова установка | Native DB SHA точний; typed proof 45 таблиць, 2 private files, code/static; 29,393 с; backup незмінний. |
| Відновлення роботи джерела same-N | Обидва HTTPS health endpoints — 200. |
| Відновлена установка | Реальний HTTPS login, document bytes та version 0.2.10-dev; новий cookie namespace. |
| Завершення | Усі власні процеси зупинено; вихідний backup зберіг валідний manifest. |

Native DB SHA у capture та clean restore однаковий: `dce9e6edeb26d964737179cdc7d32a66fcfb534c656b7bdb0180b9cefc195297`. Document SHA до/після: `bba0159323a4d10c1954fea3eb175e0b9a10eb26a76b80dcf4a0f310264f2111`.

Ці 8 сценаріїв прив’язані до restore `c3d4dba…`; нова версія `baaf642…` додатково має окремий фактичний late-failure доказ. Не підміняємо цим повний повторний прогін інтегрованого package.

## Неприйняті межі

- Немає приймання generation activation, upgrade/rollback, відновлення поверх існуючої установки або керування довільним зовнішнім сервером.
- Немає crash/power-loss випробувань повної дерева backup; fsync marker/root не доводить durable entries всіх вкладених каталогів.
- Read-only/hash `inspect_backup` сам по собі не засвідчує довіреність зовнішнього backup з виконуваним code. Поточний доказ стосується власної копії, отриманої з owned release під фактичною lease.
- AF_UNIX, PostgreSQL, Windows та CI залишаються зафіксованими окремими непройденими межами. Відомий A09 13 MiB boundary залишається blocked; нових спроб не було. Заморожені 11 gates не змінюються.

У перевірених межах додаткових блокерів не залишилося. Наступне приймання має стосуватися конкретного інтегрованого package та визначеного нового сценарію, а не повторного оголошення A10 завершеною.
