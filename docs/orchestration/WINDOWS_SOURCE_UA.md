# PLAN-SOURCE-WINDOWS · фактичний source SHA на Windows

Статус: **ACCEPT_SCOPED_NATIVE_WINDOWS_SOURCE** після незалежного review. Дата: 20.09.2026. Предмет — відтворюваність SHA поточного runtime на справжній Windows; повне приймання Windows / GATE11 не виконувалось.

## Кандидат і критерій

PR [#1](https://github.com/vladduk-A-W-F/BOS/pull/1), перевірений head `82beca6c14e097a31200068d72b15334c5bed319`. Runtime тотожний CI commit `8060075455206257d6283c70906facca98f0bc1a`: після нього три коміти змінювали тільки docs/evidence. Критерій — незмінена production-функція `scripts.verify.source_digest()` на справжньому `WindowsPath` повертає SHA, отриманий Linux CI, а повний набір її вхідних файлів точно відповідає Git.

Окремий runtime snapshot містить **348 файлів / 7 473 114 байтів**, без БД. 320 файлів узято з наданого локального архіву лише після точного збігу raw Git blob SHA; 28 отримано через GitHub connector за незмінним head. Кожен шлях, регістр, розмір, Git blob SHA й режим перевірено; колізій імен файлів/каталогів без урахування регістру, symlink або junction немає. Це відтворення всіх runtime-входів, а не повного Git checkout або історії.

## Результат

- Реальна ОС: Windows 10, build 19045. Python 3.12.14, `os.name=nt`, `WindowsPath`.
- Production SHA: `ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5` — точно збігається з [Linux/PG16 run 35507888776](https://github.com/vladduk-A-W-F/BOS/actions/runs/35507888776).
- Два наявні path-only unit методи: 2/2, без пропусків. Шість окремих перевірок на справжніх файлах: порядок mixed-case/directory-prefix; нормалізація текстового CRLF; збереження binary CRLF; виявлення зміни вмісту; виявлення перейменування; виключення bytecode.
- 348 raw Git blob/size/SHA256 до й після однакові. Незалежний reviewer повторно звірив inventory з живим Git tree й отримав той самий digest окремою реалізацією на Node.js.
- Остаточний процес: `python.exe -I -B work/native_windows_source.py`, exit **0**; `optimize=0`, `isolated=1`, assertions активні. Точний executable, тривалість і receipt — у report. Імпортовано лише перевірений verifier; `main()`, Django, БД та suites не запускались.

## Походження доказів і проміжні спроби

[Report](evidence/windows-source/report.json), [raw log](evidence/windows-source/raw.log), [unit log](evidence/windows-source/unit.log), [348-file manifest](evidence/windows-source/runtime-manifest.json), [independent review](evidence/windows-source/REVIEW.md), [independent digest](evidence/windows-source/INDEPENDENT_DIGEST.json), [SHA index](evidence/windows-source/sha256-index.json). Збережено точний helper виконання. Для відтворення його layout: `work/candidate-runtime/` — перевірені runtime blobs плюс AGENTS.md; `work/live-audit/runtime-inventory.json` — path/sha/size/mode з manifest; helper — `work/native_windows_source.py`. Результати пишуться в `outputs/windows-source-evidence/`.

Перша спроба не завершилась: створена Python tempfile директорія не дозволила runner записати підкаталог (WinError 5); raw відмову збережено. Недоступну директорію й її права не змінювали. Для допоміжних синтетичних probes використано нову звичайну workspace-директорію з успадкованими правами. Друга спроба завершилась успішно; її helper/report/raw збережено в `attempt2/`. Після review додано fail-closed перевірку assertions, точного імпортованого модуля й junction; остаточний обмежений запуск підтвердив результат. Це не повтори full/PG suite/E2E й не скидання P05 3/3. Окремого повного receipt першої спроби немає; їй не зараховано PASS.

## Межі та наступний крок

Закрито тільки попередню прогалину PLAN-SOURCE «native Windows не перевірений» щодо source identity цього runtime. Чиста установка Windows, критерії 1–3 і 6, повний PostgreSQL/SQLite suite, бізнес-E2E, production activation та browser acceptance не входили в пакет. Windows 11 не заявляється. `P06=BLOCKED`, `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, GATE11 `NOT_RUN`; історичні receipts й обмеження незмінні.

Окремо актуалізовано stale [P10-003 card](cards/P10-003.md) за вже наявними адресними PG16 доказами. Повторна реалізація isolation guard не потрібна. Причини P06-F04/F05 залишаються відкритими; наступний runtime пакет призначає головний оркестратор.
