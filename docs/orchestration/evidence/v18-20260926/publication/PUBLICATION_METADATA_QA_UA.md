# V18 publication metadata QA

## Межа

Канонічне дерево `bos-consolidation-plan` читалося лише для цього пакета.
Нові artifacts створено тільки в цій ізольованій теці. Не запускалися app
tests, CI, build, browser, PostgreSQL, Django system check, checker, AST,
fsck або будь-яка дія публікації/merge/tag/push.

Це перевірка publication metadata, а не підтвердження remote push, повної
готовності продукту або виконання 11 GATES.

## Результати

| Перевірка | Exit | Фактичний результат |
| --- | ---: | --- |
| `bos_control.py validate` | 0 | Static PASS: roles `10`, tasks `42`, gates `11`; application tests і CLI runtime не запускалися. |
| Publication JSON matrix | failure | Усі 5 JSON файлів успішно parsed, але assertion harness звернувся до неіснуючого для `CURRENT_BASELINE` поля `product_candidate_commit` замість чинного `product_commit`. Це `FAIL_HARNESS_FIELD_NAME`; повтору не було. |
| Git/digest matrix | 1 | Digest `44a3a2e...f94307a`, merge parents, old tag і чотири ancestry assertions успішні. Після цього scope assertion відхилив metadata paths `AGENTS.md`, `README.md`, `README_UA.md`; це `FAIL_HARNESS_SCOPE`. Повтору не було. |
| Original-100 ledger loop | NOT_RUN | Не розпочався після terminating scope assertion. Не позначається PASS у цьому пакеті й не повторювався. Root/reviewer окремо використали transitive ancestry proof через parent `81ba3a0...` та exact merge parent. |

## Успішні підперевірки з raw receipt

- Runtime source digest кандидата `718b89497da0d338057ab2bd81d5034c68362d79`
  дорівнює `44a3a2ee9fb1e8b36917f7c2c5c6aa60e533f1d3236e26de907e64520f94307a`.
- Exact parents merge: `03fa08f797503d04d2340ba8aa57e719b275c019` і
  `81ba3a04e74ecf139433ae9196775b7dcc09305c`.
- `bos-current-2026-09-26^{}` peel дорівнює `03fa08f...`.
- `2520814...`, `a3c0596...`, `03fa08f...` і `81ba3a0...` є ancestors
  `718b894...` за окремими `merge-base --is-ancestor` assertions.

## Обмеження та передача

`publication_json.observed-terminal.txt` є точним transcript першого JSON
запуску: terminating exception стався до створення планового stdout receipt.
Він не є rerun. `publication_git_digest.stdout-stderr.txt` містить успішні
subchecks і terminating scope finding. Жоден з цих harness failures не
приховувався та не був послаблений до PASS.

Незалежний manual review прийняв schema/scope розмежування як
`ACCEPT_SCOPED`: `CURRENT_BASELINE.product_commit` і
`STATE.product_candidate_commit` обидва дорівнюють `2520814...`; root-level
`AGENTS.md`, `README.md`, `README_UA.md` є дозволеними metadata, не runtime.
Reviewer також підтвердив transitive inclusion 100 ledger commits через
прийнятий ancestor `81ba3a0...` і його exact parent relationship у merge
`718b894...`. Це зовнішнє review evidence, не PASS невиконаного matrix loop.

Висновок для цього пакета: `PARTIAL_METADATA_AUDIT_WITH_HARNESS_FINDINGS`.
Readiness лишається false; цей пакет не змінює 11 GATES, рішення щодо
main/tag або факт remote publication.
