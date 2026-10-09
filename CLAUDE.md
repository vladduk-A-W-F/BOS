# BoS · правила для Claude

@AGENTS.md

Правила й межі `AGENTS.md` вище діють для Claude повністю. Тут лише те, що змінила передача від Codex (`docs/strategy/BOS_HANDOVER_CODEX_TO_CLAUDE_UA.md`).

## Ролі
- **Claude — виконавець та інтегратор.**
  - Хмарна сесія веде картки, PR, CI і злиття в погодженому обсязі після зеленого CI та ACCEPT рецензента.
  - Локальна сесія на ПК власника (Claude Desktop або `claude remote-control`) доставляє owner-local за `docs/strategy/DEV10_INSTALL_UA.md`, лише з резервною копією й перевіркою.
- **Незалежне рев'ю** виконує агент `bos-reviewer` (`.claude/agents/bos-reviewer.md`). Він отримує картку, diff і сирий вивід, без міркувань автора. Автор не приймає власний код.
- **Власник** ухвалює рішення й вливає зміни меж `AGENTS.md`, архітектури, прав, схеми даних і секретів.
- **Codex** неактивний: не призначати йому роботу й не писати «@codex» у GitHub. Згадка будить бота, у якого немає середовища.

## Перевірки
- **Django.** Лише синтетичні БД SQLite; назва БД містить `bos3-fasteners`. Повний список модулів, як у CI, — у `.github/workflows/pr-tests.yml`.
  ```
  DJANGO_SETTINGS_MODULE=verification_settings BOS_VERIFY_DB=sqlite BOS_DATA_MODE=demo PYTHONUTF8=1 \
  BOS_TEST_DB_NAME=<тимчасова тека>/bos3-fasteners-qa.sqlite3 BOS_TEST_MEDIA=<тимчасова тека>/media \
  python -B manage.py test <модулі> --noinput
  ```
- **Фронтенд.**
  - Правки — лише в `frontend/boss_app_source.html`.
  - Потім `node scripts/build_frontend.cjs`. Похідні `assets/app.js` і `frontend/boss_app_html.html` комітяться разом: CI звіряє збірку з джерелом.
  - Node-тести: `scripts/test_bos4_*.cjs`, `scripts/check_frontend.cjs`, `scripts/check_flow_projections.cjs`.
- **Міграції.** Запускати `manage.py makemigrations --check`. Зміна схеми — лише рішенням власника.
- **Перед push:**
  - тести змінених модулів;
  - `git diff --check`;
  - перечитати diff так, ніби шукаєш, чим його відхилить CI.

## Мова й звіти
- **Українською:** інтерфейс, документи, PR і коментарі в GitHub. Коментар закінчується підписом Claude Code.
- **З власником** — мовою, якою він пише.
- **Звіти:** по картці — до 10 рядків, питання — одним списком «так/ні». Докази з ПК лишаються на D:, у Git — лише посилання й SHA-256.
