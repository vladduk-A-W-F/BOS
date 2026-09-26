# PLAN-SOURCE / P04-F01 · міжплатформний source SHA

Дата: 20.09.2026. Статус: **FIX_PREPARED_SCOPED**, незалежний review очікується. Канонічний BOS не змінено цим агентом.

## Причина й мінімальне виправлення

Історичний `sources/BoS_Execution_Prompts_UA/P04_RESULT_UA.md` фіксує P04-F01: однакові 336 файлів дають різні SHA через сортування Path між ОС; на той час patch не застосовано. Поточний код досі містив `sorted(set(files))` у `scripts.verify.source_digest`. Path порівнює компоненти; Windows flavor нормалізує регістр для порівняння, POSIX flavor — ні. Нормалізація `\` → `/` після сортування вже не виправляла інший порядок хешування.

Змінено тільки sort key: `sorted(set(files), key=lambda p: p.relative_to(ROOT).parts)`. Це порівнює відносні компоненти як звичайні case-sensitive рядки на обох ОС; root/drive не потрапляє до ключа. Збережені перелік включених файлів, framing name/NUL/content/NUL, UTF-8 шляхів, CRLF normalization і SHA-256.

**Сортування всього `.as_posix()` рядка навмисно не застосовано:** воно міняло б поточний Linux порядок, бо `operations/seed/documents.json` стало б раніше за `operations/seed/documents/D01.md`. Чинний Linux Path сортує за компонентами, і `documents` передує `documents.json`. Окрема регресія утримує саме цю сумісність.

`package_server.py` теж обходить native Path, але його source SHA рахується з JSON manifest через `sort_keys=True`; порядок додавання dict entries не впливає на digest. Його змінювати не потрібно. `check_data_transfer.py` та `e2e_scenario.py` імпортують спільний verifier helper, тому отримують цю правку без додаткових змін. Локальних `.github/ci/evidence.py` файлів у відновленому canonical runtime немає; відсутність не видається за їхній review.

## Межі картки та походження

Працював тільки в `execution/source_digest/src`. До початку картки root уже інтегрував окремі дозволені правки: зафіксований поточний Linux snapshot містив **342** source-файли, SHA `b9722ed16722cee83de6d7b30d9cac7077488237bd5f3020c60709e851ab859d`. Це не початковий SHA кандидата 7d46dced і не його підміна. Файл verifier до цієї картки побайтово збережено як `verify-original.py` поза source inventory.

Allowlist:

- `scripts/verify.py`: один рядок comparator та два рядки пояснення.
- `scripts/test_source_digest.py`: два нові тести pure path/hash behavior.

`source_digest.patch` — точний diff від зафіксованого pre-card verifier; `files.json` — SHA обох файлів. Жодної зміни GATES, SUITES, frozen85/12, readiness, workflow або запусків verifier main.

## RED / GREEN

Команда в ізольованій копії:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest scripts.test_source_digest -v
```

| Перевірка | Фактичний результат | Доказ |
|---|---|---|
| RED: незмінний verifier + нові regression tests | 2 методи; 2 failing Windows subcases; exit1; 0.010 с | red.log |
| GREEN: точний patch | **2/2 PASS**, exit0; 0.009 с | green.log |
| AST parse обох змінених файлів | exit0 | same-inventory proof command |
| Той самий 342-file inventory, до/після comparator | Linux SHA точно збережено; Windows стає рівним Linux | same-inventory-proof.json |

Тести викликають **реальний** `verify.source_digest`, підставляючи лише read-only in-memory inventory. Вони використовують справжні Python `PurePosixPath` / `PureWindowsPath` зі штатною семантикою порівняння. Перевіряють mixed case, underscore, root-level launcher, дві протилежні enumeration orders, binary bytes та CRLF text normalization. Очікуваний порядок задається явно, без повторення production comparator. Другий метод захищає порядок директорії з ім’ям-prefix (`documents/` проти `documents.json`). Це synthetic path proof, не native Windows чи full acceptance.

## Точний доказ збереження Linux SHA

Для порівняння алгоритмів взято **одні й ті самі pre-card bytes**: новий test omitted; старі bytes verify підставлені в пам’яті. Початкові файли на диску не змінювалися. Обидва алгоритми отримали однакову інвентаризацію342.

| Path flavor | Старий comparator | Новий comparator |
|---|---|---|
| POSIX | `b9722ed16722cee83de6d7b30d9cac7077488237bd5f3020c60709e851ab859d` | `b9722ed16722cee83de6d7b30d9cac7077488237bd5f3020c60709e851ab859d` |
| Windows | `9bfc86c004bff5db03c5936dd963fd0c89c159eaf4abf754dd909d7244d1fa62` | `b9722ed16722cee83de6d7b30d9cac7077488237bd5f3020c60709e851ab859d` |

Після реального редагування verifier й додавання test source inventory закономірно став343, новий фактичний SHA — `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20`. Він не підміняється старим SHA; історичні PASS не успадковуються. `same-inventory-proof.json` містить обидва окремі факти.

## Обмеження й наступний крок

App, Django, DB, PostgreSQL, native Windows, full, E2E, CI, інсталяція та deploy не запускались. Жодних тестових чи реальних БД не створено. Readiness та вичерпаний P05 ліміт незмінні. Колізії назв файлів, які відрізняються лише регістром і не можуть співіснувати на типовій Windows FS, не є предметом цього сортувального виправлення.

Незалежний review точного patch + raw logs → послідовна інтеграція root. Подальше повне/Windows приймання потребує власних чинних передумов; ця картка їх не обходить і не запускає.
