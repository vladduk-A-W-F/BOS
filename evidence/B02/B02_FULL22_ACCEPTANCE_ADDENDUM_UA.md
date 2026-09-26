# B02 full22 — незалежний read-only addendum

12.09.2026. Перевірено завершений `evidence/B02/verify-1/report.json`, gate07/gate08/Django журнали, чинний source fingerprint і точні HEAD diff. Жодного нового серверного запуску, HTTP13MiB probe, тесту, зміни checkout або читання оригінальних DB/media не виконувалося.

**Mandatory full22 має успішний gate8 саме в цьому запуску:31/31, клієнт фактично отримав HTTP413 на13MiB. Причину попередніх reset не встановлено; повторювану стабільність або виправлення A09 цим результатом не доведено.** Попередні невдалі докази зберігають історичну силу. Їх не слід вилучати або описувати як виправлені B02.

Точні підтвердження:

| Перевірка | Факт |
|---|---|
| Source fingerprint | Самостійно обчислений чистою функцією source_digest без Django/DB: `dbff81af9070a059c48f91ae6bbbedd58c7448dc766469112bef120e307c73a0`, точно дорівнює report. |
| Gate2 SQLite | Старі22+49+48+32=151, launcher5, Django487 пройшли; Django log202.180s. |
| Gate7 | Фактичні12/12, нові47 таблиць,3 private files; остаточний restored replay має no_new_business_effects=true. Прочитаний незмінний check_restore source містить GET ERP snapshot до/після replay і deep equality; отже раніше відкладена assertion виконана в цьому canonical run. |
| Gate8 | complete=true,31checks, статус ПРОЙДЕНО; oversized_request_413_no_partial_document має passed=true, status413, documents_and_private_bytes_unchanged=true. Це HTTP-клієнтський результат, а не лише proxy log413. |
| Restart/logs | Обидва owned children завершилися0 без forced; restart exact DB/private bytes збережено; nonempty allowlisted application/proxy logs; private_canaries_absent=true,29logfiles checked. |
| Оригінальні бази | full22 report має source_database_count=2 та source_databases_unchanged=true. Код verifier порівнює SHA до/після. Reviewer не відкривав ці бази і не створює новий незалежний runtime proof їхніх bytes. |

`check_install.py` буквально незмінний проти HEAD, SHA `af1fb85dbd4641479ed666ca080a3a42423b23d7560513434e69875fef0549c7`; `server_http_checks.py` теж буквально незмінний, SHA `cccb3b878f542dbe18adaa080123805900c423deffbfdb3d5a2ae275f1926a11`. Його oracle досі приймає тільки отриманий413; reset/timeout/502 не зараховується. Payload досі13×1024×1024 bytes POST `/api/operations/documents/upload/`; після нього перевіряються точні document list і private bytes.

B02 diff у `server_config.py` та `demo_middleware.py` додає тільки виклик `capture_import_body` після вже чинного peer check. Helper одразу повертає None, якщо path не `/api/erp/import/preview/` або method неPOST. Тому13MiB upload path не потрапляє під новий import reader. Source diff не встановлює причини зміни результату та не дає підстав називати B02 виправленням транспортного збою.

Report SHA `c48cd3af921c4a9fc7eb65c9630788523bc00f8501a3df2984382567868b4c6c`; gate08 log SHA `6c175fdd5c22d45ed33af3c1a85095319fa19c5680ef9b4753ac6f08744be613`.

Загальний complete=false правильний: усі11gates збережені; PG parts1/2/3/5, Windows11, CI не виконані, gates6/9/10 не реалізовані. Результат дозволяє оновити поточний gate8 на ПРОЙДЕНО з явною приміткою про історичну нестабільність, але не проголошувати весь MVP або весь A09 прийнятим.
