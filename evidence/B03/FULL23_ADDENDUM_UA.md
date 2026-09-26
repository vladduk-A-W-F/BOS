# B03 — незалежне доповнення за фактичним full verify №23

12.09.2026. **У виконаному локальному B03 scope нових регресій не виявлено. Повний прогін не пройдено: complete=false, exit 1.** Відома перевірка 13 MiB у gate 8 знову завершилася ConnectionResetError. PostgreSQL, Windows, CI та нереалізовані gates залишаються відкритими.

Reviewer прочитав canonical report і підсумки журналів, самостійно перерахував лише source fingerprint та SHA файлів. Нових тестів, серверів, restore або A09 спроб не виконував; checkout і оригінальні DB/media не змінював і не відкривав.

## Точна версія

Canonical `evidence/B03/verify-1/report.json`: SHA256 `a9b9b69b641e2930602d73a4925cdb563ed6e391b91fa0291d786c83eaed8bd3`.

Фактичний `source_sha256` із report і незалежно виконаного чистого `source_digest()` збігається: `4fd37c76b235f94140aaa156ef6fee589a5e3bd789b1d0d144225c39abeb8ed1`. Середовище Linux / Python 3.12.14, серверна версія 0.2.13-dev. Verifier зафіксував `source_database_count=2`, `source_databases_unchanged=true`; цей висновок посилається на його before/after контроль, а не на нове читання вихідних баз reviewer.

## Фактичні результати

| Перевірка | Результат |
|---|---|
| SQLite міграції | Пройдено. |
| Старі функціональні та launcher | 22 + 49 + 48 + 32 = 151; додатково 5 launcher, усі пройдені. |
| Django | 521/521, 308.948 s, OK. |
| П’ять інваріантів | По 1000 фактичних прогонів; усі пройдені, role_failed_sequences=0. |
| Gate 4 | 8694/8694 HTTP cases та 9 redirect responses, 177 route definitions, 57/57 field tests; failures порожній. |
| Gate 5 SQLite | 99/99 methods, 74.233 s; 110/110 унікальних ERP records, exact 33 actions; missing/duplicates/failures порожні. Source SHA до/після однакові. PostgreSQL тут не приймається. |
| Gate 7 | 14/14 фактичних native backup/clean restore/HTTPS сценаріїв, exact 53 таблиці. Шість B03 ledgers заповнені, сім canonical intents повторно прочитані/повторені без нових бізнес-ефектів. |
| Gate 8 | 30/31. TLS, cookies, role/CSRF checks, приватний документ, health, duplicate refusal, restart і normalized logs пройдено. Обов’язковий 13 MiB сценарій не пройдено. |

Gate 7 порівняв повний B03 snapshot до й після відновлення: SHA `1e8e168093de975262960c1913a74bb75f8212bb84cb240a6784727997a282a8`. Native DB SHA capture/restore однаковий, збережено три приватні файли; backup лишився незмінним. Це фактичний canonical run 0.2.13-dev, додатковий до попереднього isolated proof 14/14 версії 0.2.12-dev.

Gate 8: `oversized_request_413_no_partial_document` має passed=false, status=null, error_type=ConnectionResetError, `documents_and_private_bytes_unchanged=true`. Normalized proxy log містить 413, але клієнт у цьому прогоні не отримав доказову HTTP-відповідь 413. Лог проксі не замінює обов’язковий client oracle. Обидва власні stop завершилися exit 0 без force; private canaries відсутні у 29 перевірених log files.

`check_install.py` і `server_http_checks.py` буквально незмінні проти B02/попереднього HEAD: SHA відповідно `af1fb85dbd4641479ed666ca080a3a42423b23d7560513434e69875fef0549c7` і `cccb3b878f542dbe18adaa080123805900c423deffbfdb3d5a2ae275f1926a11`. У full22 той самий обов’язковий probe отримав client413 і gate 8 був 31/31. У full23 нестабільність знову проявилася. Причину не встановлено; жодної заяви про усунення цієї проблеми або нову B03-причину немає.

## Межі приймання

Незалежний scoped consensus B03 backend збережено; фактичний full23 підтвердив локальні функціональні, доступ, concurrency та restore докази. Усі 11 gates лишаються обов’язковими. PostgreSQL частини 1/2/3/5 і Windows gate 11 не запущені; CI identity відсутня. Gates 6 (наскрізний процес), 9 (upgrade/rollback), 10 (браузер) не реалізовані. Загального приймання BoS MVP, production deployment або фактичного browser UX цей звіт не дає.

## SHA журналів

| Журнал | SHA256 |
|---|---|
| gate-04-sqlite.log | `d9b646d5e57600a48d357b55b43ec3b1bac3c482a325f6eda3cba5c0e8e4612a` |
| gate-05-sqlite.log | `712a7b0188344f5f8152632dd1c7027493284c2a17c71b8dc631b9a42669d50a` |
| gate-07-sqlite.log | `f8e9981f3740a2332f83b548840980b32c7f1b8ccdc7b45119467cf7b2b0a5d6` |
| gate-08-sqlite.log | `2bb7c1c5164a759b3d97a1a8dc8056aacaea9c18e19b39d2a2e2bf296992c320` |
