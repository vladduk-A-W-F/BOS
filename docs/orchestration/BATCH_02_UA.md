# BATCH-02 · джерела замовлення й адресне погодження

## Зміни за модулями
- PLAN-LINKS-READ, commit `1958163e982cf249dbdf619389fe3568a5510b53`: GET trace одного замовлення; Policy, точні Decimal, явні restricted/partial, джерела резервів/поставок/скасувань, роботи, завдання й дозволені рахунки. Два проходи перевірки та нейтральний 409 при зміні. Каталог доповнено до 191 маршрутів/75 field tests; старі 190/57 збережено. Глобальний writer inventory 85/12 незмінний.
- PLAN-UX-TRACE, commit `313850f02ec866ededc417602e155427d7cc5222`: розділ «Джерела виконання» у чинному inspector; Decimal як рядки, restricted/null, явний refresh, відкидання пізніх відповідей і перевірка свіжого доступу перед переходом.
- PLAN-N2-ADJUST, commit `603de9de7c92c77ce7a69d198fdfc786e8aca8e3`: тільки нові ERP preview для erp_adjust отримують серверний dependency_context. Пов’язані партія/номенклатура/місце/резерви/рухи/версії документів/байти/права та показаний вплив перевіряються перед commit. Інші дії, generic preview і старі пропозиції використовують початковий global fingerprint. Mutex, CAS, replay та rollback збережені. Адитивна nullable міграція; робочих БД не змінено.

Незалежний reviewer прийняв усі три модулі в зазначеному обсязі. Початковий N2 patch був перестворений щодо вже зміненого canonical і видаляв trace suffix; root виявив це на URL import, повернув точний прийнятий suffix і повторно звірив композицію з reviewer. Неправильний проміжний код не потрапив у GitHub. Перший raw log збережено.

## Докази
- Авторський trace: 18 різних HTTP-методів PASS у 17+2 запусках, один повтор; baseline 404 RED збережено.
- Авторський N2: 21 різний portable метод PASS у двох запусках; первинна помилка archive fixture збережена й виправлена штатним archive шляхом.
- Інтеграція SQLite: 39/39 PASS, exit0, 28.811s; raw SHA `7a68c860d198732d18439a140052b53b7ba085397b37e89c8fc2235aaba13404`.
- UX: штатна локальна Babel build, JS syntax і 18/18 контрольованих перевірок фактичного JSX. Це не браузерне приймання.
- PostgreSQL16.15: run [35507888776](https://github.com/vladduk-A-W-F/BOS/actions/runs/35507888776), attempt1, exact commit `8060075455206257d6283c70906facca98f0bc1a`, runtime `ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5`. 42/42: trace18 + adjustment24.
- Три справжні конкурентні сценарії: незалежні партії200/200; одна партія200/409; повтор однієї пропозиції200/200 з одним ефектом. Третє з’єднання підтвердило pg_blocking_pids та wait_event_type=Lock до звільнення mutex.
- Runtime і source DB canaries незмінні. ZIP11719bytes, SHA `4908b2ad522fde391d254061a41560fd8e3336c692d3ad5f6819eff7fe97b6ec`; усі 8 indexed files звірено. Повний raw у ZIP в evidence/batch02/PG16.
- Старий BATCH01 workflow35507888700: scopePASS, targetedSKIPPED. Новий wrapper не викликав старих тестових стадій.

## Межі
Це PASS_SCOPED нових карток. Немає full suite, actual business E2E, браузерного/Windows/production acceptance. P06 BLOCKED; TECHNICAL_READY=false; PILOT_ALLOWED=false. Історичні P05/A09/A10/A11 не скинуто. Подвійне читання trace не є глобальним атомарним snapshot; великий обсяг не тестувався. Розширення адресного погодження на інші дії — окремі картки. Наступні пакети: SaaS handoff і лендинг.
