# Незалежний review: відмова єдиного preflight dev9 recovery

Дата: 2026-09-28  
Режим: review збережених evidence та static guard; live probe, retry і runtime-дії не виконувалися.

## Перевірені докази

| Артефакт | SHA-256 | Висновок |
| --- | --- | --- |
| `preflight-receipts/NATIVE_RECEIPT.json` | `d6243dd2fee83e8af116c4a020e8d68e1dbf86cc9ccd520968416edfcc2a8a89` | один exact preflight, native exit `2` |
| `preflight-receipts/PREFLIGHT.json` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | stdout порожній; success receipt відсутній |
| `ROOT_RECOVERY_DECISION.json` | `398d0d6cfcb2ba49fb2bf32f03c71e6c34160bb15281d5a0de5162c11b1dae9a` | preflight максимум `1`, apply/start/GET окремі gates |

Native receipt фіксує точний argv з `-X utf8 -B`, fixed owner root та failed dev8 source, одну інвокацію з maximum `1`, `apply_calls: 0`, `start_calls: 0`, `HTTP_calls: 0`. Отже preflight `1/1` спожито, а подальші фази не починалися.

## Що саме доведено кодом і результатом

`SERVER_OR_PORT_OCCUPIED_STOP_WITHOUT_KILL` виникає лише після успішного проходження попередніх preflight guards: final pins, exact fixed instance/failed source, exact failed source head/digest/clean tree, ordinary owner paths, відсутній `process.json`, prepared dev8 binding, database presence та збережений cleanup receipt. Це не доводить protected aggregate або residual metadata: вони обчислюються лише після `require_no_server_or_listener()` і success receipt не створено.

Внутрішня PowerShell перевірка навмисно відкидає stdout/stderr і зводить будь-який nonzero результат CIM/listener запиту до одного fail-closed коду. Тому evidence **не доводить**, що listener або dev8 `internal-serve` реально існував: причина могла бути occupied port/process, PowerShell/CIM failure або інша помилка цієї внутрішньої перевірки. Поточна доступність runtime лишається `UNCONFIRMED`.

## Диспозиція

`ACCEPT_SCOPED_PREFLIGHT_FAILURE_DISPOSITION`.

Процедуру правильно зупинено без kill, retry, apply, official start чи GET. Це не є продуктова або candidate failure і не є доказом збереження aggregate.

Наступним мінімальним рішенням може бути лише окрема картка static diagnosis/repair, яка зберігатиме класифікований внутрішній результат guard без виконання нового preflight. Вона не скидає ліміт `1/1`, не дозволяє повтор і не підтверджує зайнятий порт без нової окремо авторизованої live-перевірки.
