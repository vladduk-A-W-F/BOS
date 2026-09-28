# Незалежний static review: observation diagnosis після відмови preflight

Дата: 2026-09-28  
Режим: підготовка лише для читання; спостереження не виконувалося.

## Перевірені входи

| Артефакт | SHA-256 |
| --- | --- |
| `OBSERVATION_DIAGNOSIS_CARD.json` | `0eacc412c31c406abcf2e9aa09439344686f1fd17c15054ea544948d23e0dac8` |
| `observe_bos3_server_and_port8030_once.ps1` | `0c8c7a9649fb194963a31fada4cfda563d767a54df3598414b70b1f9fb2f1a2b` |
| `MANIFEST.json` | `a1f57880737a32c9860c3ae340afe4fa3a93cb9240433e17eb31c1c194ca467e` |

## Межа та безпека

1. Скрипт відмовляється до будь-якої OS-дії, поки `RootObservationGo` є `PENDING`; окремий `observation1` directory створюється один раз через CreateNew-подібний evidence flow, а його наявність означає відмову від повтору.
2. Дочірній процес -- лише absolute native Windows PowerShell з process-local `PSMODULEPATH`, `-NoProfile`, `-NonInteractive` і captured native exit/stdout/stderr. Він не імпортує Django, не читає owner instance, не відкриває БД, не виконує HTTP, socket bind або lifecycle команд.
3. Єдиний дозволений live surface -- CIM process metadata для `internal-serve` та metadata усіх listener на `8030`. Raw command lines не друкуються: доказ містить PID, creation time, executable path, listener address/port і boolean BoS classification. Це відповідає картці; executable path є дозволеним identity/path полем, а не application data.
4. Отриманий nonzero native exit або captured stderr лише пояснюватиме причину suppressed guard. Навіть успішне спостереження не є preflight, не створює `PREFLIGHT.json`, не задовольняє apply gate та не доводить доступність runtime.

## Класифікація

`SAME_PROBLEM_READ_ONLY_DIAGNOSIS_NOT_FULL_RETRY` коректна. Це не новий product ID і не обхід already consumed preflight `1/1`: окремий ліміт один раз стосується лише missing-cause observation. Лічильники full problem `2/3`, old window start `1/1` та failed preflight `1/1` зберігаються.

## Вердикт

`ACCEPT_SCOPED_STATIC_ONE_READ_ONLY_OBSERVATION_RECIPE`.

Після окремого root GO допускається рівно одне спостереження за цим exact hash. Відмова або результат не дозволяють retry preflight, apply, start, GET, kill чи будь-яку зміну runtime. Результат потребуватиме окремого raw-evidence review перед наступним рішенням.
