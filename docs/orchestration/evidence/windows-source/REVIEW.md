# PLAN-SOURCE-WINDOWS · незалежний review

Дата: 20.09.2026. Рецензент: незалежний агент `p06_f02_review`.
**Вердикт: ACCEPT_SCOPED_NATIVE_WINDOWS_SOURCE.** У перевіреному обсязі блокерів не виявлено. Закрито прогалину доказу обчислення source digest на фактичному WindowsPath; прийняття встановлення або GATE11 не заявляється.

## Предмет та джерела

Перевірено точний runtime snapshot кандидата `82beca6c14e097a31200068d72b15334c5bed319` з [PR #1](https://github.com/vladduk-A-W-F/BOS/pull/1). Порівняльний Linux CI digest належить commit `8060075455206257d6283c70906facca98f0bc1a`, [run 35507888776](https://github.com/vladduk-A-W-F/BOS/actions/runs/35507888776). Цей review незалежно звіряє файли, алгоритм і native evidence; не повторює Linux CI.

Рецензент окремо отримав незрізане recursive Git tree точного head (2009 entries), самостійно відібрав входи `source_digest` і підтвердив **348/348** шляхів, Git blob SHA, розмірів та режимів авторського inventory. Повний Git checkout/історію не відновлено: snapshot містить 348 runtime inputs і окремий `AGENTS.md`.

## Методика

Статично прочитано `scripts/verify.py`, `scripts/test_source_digest.py`, reconstruction helper та кінцевий native helper. Імпорт незміненого `scripts.verify` не викликає verifier main, Django setup або БД. Helper перевіряє `verify.__file__`, `verify.ROOT`, активні assertions та фактичний тип WindowsPath. `BOS_TEST_DEPENDENCIES` видаляється з середовища перед імпортом.

Архівні байти приймалися лише при збігу raw Git blob SHA; решту отримано для того самого head. Перед і після запуску helper перевірив кожен Git blob SHA/розмір, точне написання всіх шляхів і відсутність зайвих файлів, symlink/junction. Рецензент незалежно звірив raw bytes усіх 348 файлів з live Git та фінальним manifest. Незалежний Windows scan всього дерева (384 entries з коренем) не знайшов ReparsePoints. Конфліктів casefold немає ані серед повних імен, ані серед компонентів каталогів. `scripts/verify.sh` має допустимий режим regular executable 100755; решта — 100644.

Незалежний Node.js-розрахунок використовував тільки стандартні бібліотеки, raw bytes з перевіреного inventory, окремий comparator за Unicode code points компонентів, явне name/NUL/content/NUL framing та CRLF normalization. Продуктовий код під час цього розрахунку не викликався. Результат збережено в [INDEPENDENT_DIGEST.json](INDEPENDENT_DIGEST.json).

## Команда та фактичні результати

Фінальна команда виконавця, звірена з шляхами helper і параметрами receipt:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -I -B 'C:\Users\user\Documents\Codex\2026-09-20\bos-execution\work\native_windows_source.py'
```

Helper викликає тільки `verify.source_digest()`, два методи `scripts.test_source_digest` через `unittest` і шість локальних файлових probes. Рецензент не запускав цю команду повторно.

| Доказ | Факт |
| --- | --- |
| ОС | Windows 10, `10.0.19045`; `os.name=nt` |
| Python | 3.12.14, 64-bit AMD64 |
| Path | Фактичний `WindowsPath` |
| Режим | `isolated=1`, `optimize=0`, `assertions_active=true` |
| Runtime inventory | 348 точних файлів, 7 473 114 байтів; незмінний до/після |
| Наявні unit methods | **2/2 OK**, skipped 0; первинний `unit.log` прочитано |
| Native probes | **6/6** перевірок із активними assertions |
| Завершення | Exit 0; фінальний receipt і raw output узгоджені |
| Source SHA-256 | `ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5` |

Native Python digest, незалежний Node digest та встановлений Linux CI digest **точно збігаються**.

Шість probes перевіряють явно заданий порядок mixed-case і directory-prefix назв, еквівалентність CRLF/LF для тексту, чутливість до CRLF-зміни binary bytes, зміни текстового вмісту, перейменування шляху та виключення bytecode. Native fixtures створені за межами candidate snapshot; очікуваний порядок задано явно, без копіювання production sort expression.

## Історія виконання й цілісність

Перша спроба завершилася WinError5 при створенні підкаталогу/cleanup усередині `TemporaryDirectory`; її [первинний журнал](attempt1-fixture-permission-failure.log) збережено. Окремий receipt успіху source/unit етапів цієї спроби не збережено; вони не зараховуються тут як незалежно підтверджений успішний запуск.

Для optional probes виконавець використав новий каталог у вже дозволеному `work/` з успадкованими правами й залишив fixtures. Відхилений каталог не ремонтували, ACL не послаблювали, новий дозвіл не обходили. Другий успішний запуск і його helper збережені в `attempt2/`. Фінальне обмежене виконання після reviewer recommendations додало перевірки імпорту, assertions/ізоляції та junction і виконувалося явно з `-I -B`. Історія невдалих/попередніх запусків не прихована; ліміт P05 не змінено.

Рецензент перевірив фінальний helper SHA-256:
`9ccc6a2f4ce856a85aa12fd043a933d59bd34bfe2d363af2474b1641bec10cc7`.

Контрольні суми прочитаних первинних файлів:
- `report.json` та `raw.log`: `1ca2997b71b593a58973ac2fd0cbfab410ce07fb47e5d15aa1c589431014e77c`, по 1759 bytes; JSON ідентичний.
- `unit.log`: `48fb7ad43057e51d061c202cc0741213a03e0e858f77d582aa994cf0113aa207`, 467 bytes.
- `runtime-manifest.json`: `17fc9b076f92badc5c7049b5e5a3c1ce4582ac1926cf48b81a0b5725958fa44f`, 82559 bytes.
- `attempt1-fixture-permission-failure.log`: `d4b7d1b5d96175997a5411722b690d20847d7e2b54e8aa145f6d4e84cf35b067`, 3069 bytes.

## Межі висновку

Доказ стосується source identity на наявному Windows 10 host і лише двох path unit methods та шести native probes. Він не підтверджує чисту Windows 11 або іншу чисту установку, запуск Django/app, PostgreSQL, міграції, full suite, E2E, інсталяцію/upgrade/rollback чи всі критерії GATE11. Native fixtures не є перевіркою робочої або історичної БД.

`whole_git_tree_verified=false`, `application_or_database_started=false`, `full_suite_run=false`, `gate11_accepted=false`, `technical_ready=false`, `pilot_allowed=false` залишаються коректними. Runtime product files не змінювалися. Цей review дозволяє інтегрувати scoped evidence та узгодити документацію; він не є дозволом на merge, publication, full CI або readiness transition.
