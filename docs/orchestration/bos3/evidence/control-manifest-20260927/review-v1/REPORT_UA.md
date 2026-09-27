# B30-CONTROL-MANIFEST: статичний звіт

## Первинна причина

`validate_bos3()` безумовно читав
`LIGHT_PREVIEW_CANDIDATE.json`, хоча чинний `CONTROL_STATE.json` обирає manifest
через `candidate_manifest`. Через це контроль міг звіряти pin, версію та
readiness не з поточним обраним candidate.

Окремо `CONSUMED_ONE_SHOT` historical delivery порівнювався з поточним
product candidate. Це змішувало вичерпаний dev3 one-shot з наступним candidate.

## Зміна

- `selected_candidate_manifest()` приймає лише JSON filename без директорій,
  абсолютних шляхів чи traversal, розв'язує його в межах `BOS3_DOCS` і повертає
  validation failure для відсутнього або невалідного файла.
- Перевірки product pin, version і readiness тепер працюють з manifest, який
  обрав `state.candidate_manifest`; literal current filename видалено.
- `CONSUMED_ONE_SHOT` використовує власний `exact_product_pin` та вимагає, щоб
  `B30-PREVIEW-DELIVERY.result_commit` збігався з ним. Новий candidate не
  отримує historical authorization.
- Додано synthetic regression fixtures: alternate selected manifest, missing
  manifest, unsafe name та pin mismatch. Вони не змінюють readiness або
  delivery status у будь-якому реальному control state.

## Межі

Це зміна лише read-only development-control CLI. Вона не читає БД, не запускає
Django, не виконує delivery, не змінює runtime, readiness, historical limits,
manifest або control state. Файли не запускалися: import, compile, unit tests,
CLI та мережеві дії не виконувалися.

## Запропонована адресна QA-команда

Після незалежного review і окремого дозволу QA:

```powershell
python -m unittest tools.test_bos3_control.Bos3ControlTest.test_state_selected_alternate_manifest_is_used tools.test_bos3_control.Bos3ControlTest.test_missing_selected_manifest_fails tools.test_bos3_control.Bos3ControlTest.test_unsafe_selected_manifest_fails_without_reading_it tools.test_bos3_control.Bos3ControlTest.test_selected_manifest_pin_mismatch_fails
```

Це нова synthetic CLI-schema перевірка; вона не є повтором app, browser, ERP,
fixture або historical lifecycle QA.
