# BATCH-03 · пакет SaaS

Модель: керована окрема установка компанії. Підготовлено `SAAS_HANDOFF_UA.md` і описовий `SERVICE_PROFILE.json`: онбординг, ізоляція, доступи, відкриті умови запуску й наступні етапи. Незалежний review — ACCEPT_SCOPED_STATIC.

Штатний `scripts/package_server.py` зібрав кодовий пакет 0.2.16-dev: 320 файлів, жодної БД. SHA кожного файла звірено; manifest і receipt збережено в evidence/batch03. Package digest і runtime digest мають різний склад входів і не підміняють один одного. Код пакета відтворюється з GitHub-кандидата BATCH-02; повторна копія коду в репозиторій не додається.

Інсталятор, activation, upgrade/rollback і перенесення клієнтських даних не виконувались. Перший адміністратор, A09/A10/P06 і приймання цільового середовища залишаються відкритими. TECHNICAL_READY=false; PILOT_ALLOWED=false. Статус пакета: PACKAGED_NOT_PRODUCTION_READY. Наступний пакет — лендинг і приватна демонстрація.
