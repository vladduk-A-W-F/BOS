# Незалежний review: observation blocked до тіла скрипта

Дата: 2026-09-28  
Режим: збережені raw/result evidence; нових запусків або probes не було.

## Перевірені докази

| Артефакт | SHA-256 |
| --- | --- |
| `ROOT_NATIVE_RECEIPT.json` | `69b64658044aac4015d185a384d1440054b1a919281a3dff1c0391c4dca40f5e` |
| `RESULT_DISPOSITION.json` | `a567867dce1ac713d8d04c140c94de749f83ef54302dc38501ae7190eeebfbc7` |
| `ROOT_TOOL_ERROR.txt` | `1e54fce235d0b84af2f3795b596fd2000db491c00e1f11f67e836cff212466eb` |

Native receipt фіксує один exact invocation (`1/1`), script SHA `abf8ba68f65ad99ba210cf2b5570d23e16337f4d88c3fa18702b5710878cba63` і native exit `1`. Вона також фіксує нуль apply/start/GET/kill та заборонений retry.

`ROOT_TOOL_ERROR.txt` прямо повідомляє, що absolute PowerShell не зміг завантажити `.ps1` через execution policy (`SecurityError`, `UnauthorizedAccess`). Це відмова до виконання body, тому CIM query, port listener observation і створення `observation1` не відбулися. Текст помилки має чесно обмежену provenance: він транскрибований із tool result, а не є independently captured native stderr byte stream.

## Вердикт

`ACCEPT_SCOPED_OBSERVATION_FAILURE_DISPOSITION`.

Поточний blocker -- sanctioned script execution/access. Occupancy, suppressed inner preflight cause та runtime availability залишаються `UNCONFIRMED`. Лічильник one-shot observation `1/1` витрачено, full problem лишається `2/3`, historical preflight `1/1` і old window start `1/1` не змінюються.

Наступна дія потребує явного owner рішення щодо sanctioned execution access і окремого reviewed scope. Заборонені policy change, `Bypass`, encoded/inline replay, alternate host/tool, повтор observation та будь-які recovery дії без такого рішення.
