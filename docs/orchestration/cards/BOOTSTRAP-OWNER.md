# BOOTSTRAP-OWNER · 20.09.2026

ACCEPT_SCOPED після незалежного review ua_vertical_ui_audit. Автор install_readiness_audit, root інтегрує. Allowlist: нова management command bootstrap_bos_owner, operations/test_bootstrap_owner.py, docs/FIRST_OWNER_UA.md, ця картка.

Порожня working установка отримує одного CEO без staff/superuser, з явними document-download/export flags. Пароль getpass/stdin, жодного secret argv/log; GetPassWarning перериває обидва prompts до echo fallback. Унікальний Configuration marker, користувач, свіжа роль, grants та audit атомарні. Існуючі дані/акаунти/групи/сесії забороняють bootstrap; інші writers мають бути зупинені.

SQLite16/16 початково + новий warning regression1/1. PG16.15 17/17,25.951s tests/52.578s wrapper; дві справжні connections, created1/refused1. Обидві виділені БД очищено; початкова БД лишилася порожньою. Raw PG SHA25665d8ab9c550cef9ebfe6044464758eb4f65b42be62febd37c19477fc363dccd6. Installer/production/fullsuite не запускалися. Readiness/pilot=false. Докладний evidence додається до звіту VERTICAL_UA_UA.md.
