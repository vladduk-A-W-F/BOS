# QA revision1: статический отказ до запуска

Reviewer `/root/start_overview_review`, 27.09.2026.
Verdict: **REVISE_BEFORE_NODE_GO**. Executions: 0.
Commit4999f7a/source62e31d8f и clean guards совпали; классификация
NEW_PRESENTATION_DELTA допустима только для нового pure helper.

Harness SHA `1a192776530c89085acae53860efca9117441097719a05d3987a1c03ab88f8e1`.
Scope SHA `0f148da4d03cbba2c4eb4355348b7159a41b728ce6488ef3e7cfb4461561b7fe`.

P1: Babel.transform получает весь HTML, начинающийся DOCTYPE, а не тело
text/babel script; JSX parser plugin также не включён. Нужен ровно один
ожидаемый script, его body с удалением штатных verbatim markers,
parserOpts.plugins=['jsx'], ast=true/code=false без React transform.
Все node.start/end должны индексировать извлечённый JS, не исходный HTML.

Reviewer отдельно подтвердил: fullHandoff.source_refs=[{order_id:77}]
валиден для фактического c01SourceRefs. Fixtures, presentation assertions,
nonmutation/no-leak boundaries соответствуют принятому контракту.
Это исправление дефекта тестового harness до первой попытки, не изменение
oracle ради PASS и не runtime failure. После исправления нужен static
delta review; никакого автоматического исполнения или повтора.
