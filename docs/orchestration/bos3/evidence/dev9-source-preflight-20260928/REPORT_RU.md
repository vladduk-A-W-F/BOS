# B30-DEV9-SOURCE-AND-PREFLIGHT-EVIDENCE

## Межа пакета

Це saved-artifact evidence package. Він містить лише названі несекретні
source, template, decision, review та preflight records з recovery scratch.
Жоден source digest, preflight, тест, import, build, lifecycle, процес,
мережевий або HTTP-виклик цим пакетом не повторювався.

## Зафіксовані факти

Збережений source result фіксує рівно один shared/no-checkout clone і один
detached checkout з native exit `0`, clean detached source на
`aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975` та digest
`e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0`.
Це окремий source-only факт, а не доказ delivery або живої runtime.

Фактичний єдиний preflight завершився native exit `2`; його cap спожито
`1/1`. Success receipt відсутній: `PREFLIGHT.json` порожній. Збережений
guard повідомляє `SERVER_OR_PORT_OCCUPIED_STOP_WITHOUT_KILL`, але inner
CIM/listener stdout/stderr та native status не збережено. Отже пакет не
доводить ані зайнятий порт, ані ідентичність сервера, ані причину observation
failure. Поточна доступність лишається `UNCONFIRMED`.

Apply, official start і post-start GET не починалися: кожен має `0`
invocations. Problem accounting лишається `2/3`; повна runtime verification
не виконувалась. Збережені template/review artifacts документують майбутні
гейти, але не дають дозволу на новий preflight, apply, start, GET, recovery
чи зміну readiness.

## Цілісність і приватність

У пакет включено 32 явно вказані файли. Для кожного підтверджено byte-identical
копію за SHA-256 і довжиною; повний перелік provenance містить `MANIFEST.json`.
Історичний recovery manifest збережено під target-шляхом
`history/RECOVERY_PREPARATION_MANIFEST.json`; його явно задекларований
source-шлях — кореневий `MANIFEST.json` recovery scratch.
Historical template reports/reviews позначені як historical scope, а не як
поточний execution proof. Навмисно виключено private owner state, access і
secret файли, БД, media, широкі logs і весь source code tree поза трьома
дозволеними templates.

Immutable inputs та незалежні verdicts розділені. `REVIEW_RU.md` є
byte-identical historical recovery input із declared source path. Незалежний
package review збережено без зміни окремо як `PACKAGE_REVIEW_RU.md`, а його
delta review — як `PACKAGE_DELTA_REVIEW_RU.md`; обидва задекларовані в
`independent_verdicts`. Вони не підміняють source artifacts і не
використовуються як їх provenance.

Пакет передається незалежному reviewer, потім root. Самоприймання відсутнє.
