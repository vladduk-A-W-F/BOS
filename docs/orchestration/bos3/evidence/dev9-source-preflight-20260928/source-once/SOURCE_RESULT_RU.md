# B30-DEV9-SOURCE-RESULT-COLLECTION

## Зібраний source receipt

Після рівно одного вже зафіксованого clone та checkout зібрано тільки
read-only дані для `D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo`.
Checkout чистий до й після збору; `HEAD` detached на
`aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`. Очікуваний
`git symbolic-ref -q HEAD` завершився native exit `1` без stdout.

Clone і checkout до цього collector-кроку виконав root рівно по одному разу;
collector їх не запускав і не повторював. Їхні argv, environment,
одноразові caps, native exit `0` та хеші raw receipts перелічено у
`SOURCE_RESULT.json`.

## Цілісність коду

Контрольовані Git config значення відповідають prebind: вимкнено autocrlf,
fsmonitor і submodule recurse; hooks та attributes спрямовані на порожні
контрольовані D-файли. Object dependency підтверджено як
`target -> D canonical -> D main` через alternates.

Повний tracked source digest: `e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0`
для 2997 tracked files. Він відтворює `bos3_local.digest_source` без імпорту
helper: Git `ls-files -z` order, UTF-8 відносний шлях із forward slashes,
NUL і raw bytes кожного звичайного файла.

Candidate manifest і всі п’ять declared runtime delta files збігаються між
диском, Git blob і зафіксованими pins. Деталі та raw-receipt hashes наведені
у JSON.

## Межа

Це не runtime receipt: не запускалися застосунок, тест, build, instance,
процес, HTTP, lifecycle, БД або мережа. Доказ підтверджує тільки стан і
цілісність source checkout; готовність і delivery ним не приймаються.
Файли передаються незалежному reviewer, далі root; автор не приймає власну
роботу.
