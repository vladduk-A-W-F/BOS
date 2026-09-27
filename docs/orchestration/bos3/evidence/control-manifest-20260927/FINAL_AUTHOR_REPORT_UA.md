# B30-CONTROL-MANIFEST: статичний звіт

## Revision 3: P1 JSON shape

Після завантаження selected manifest validator тепер вимагає JSON object. Масив,
`null` або scalar повертають контрольований `FAIL`, а не аварійний виклик
`.get`. Додано один новий synthetic метод `test_nonobject_selected_manifest_fails`.

Чотири попередні адресні manifest-регресії з accepted run1 збережені без змін і
не повторюються. Цей revision не виконував тестів; новий метод очікує окремого
focused QA-допуску після незалежного delta review.

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
  manifest, unsafe name та pin mismatch. Missing-manifest fixture видаляє
  створений safe temporary manifest до прямого `validate_bos3()` виклику, тому
  перевіряє саме відсутній файл. Вони не змінюють readiness або
  delivery status у будь-якому реальному control state.

## Межі

Це зміна лише read-only development-control CLI. Вона не читає БД, не запускає
Django, не виконує delivery, не змінює runtime, readiness, historical limits,
manifest або control state. У revision 3 не виконувалися import, compile, unit
tests, CLI та мережеві дії.

## Запропонована адресна QA-команда

Після незалежного review і окремого дозволу QA:

```powershell
python -m unittest tools.test_bos3_control.Bos3ControlTest.test_nonobject_selected_manifest_fails
```

Це один новий synthetic CLI-schema focused method; він не є повтором app,
browser, ERP, fixture або historical lifecycle QA.
