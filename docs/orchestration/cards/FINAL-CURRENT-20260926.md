# FINAL-CURRENT-20260926

Доручення власника 26.09.2026: об'єднати останню версію і коміти, зробити її основною та фінальною на поточний момент; прибрати повтори контенту та поліпшити текст у колонках.

GitHub #5 є issue про фіналізацію, а не PR. Продуктова база: 207c742; документи v17: c4a68d4; план: a3c0596. Нове пряме доручення дозволяє merge в main у цьому обсязі. P05/Network 3/3, A09/A10/A11, production, реальні дані та платні API залишаються обмеженими.

Історію мережевої, tracking і daily-review гілок включено merge-комітами; runtime зберігає новішу композицію v17. Автор root; незалежний reviewer plan_review. Перша інтеграція 0cb8fdb, друга 49adfce. Їхні verdicts: ACCEPT_SCOPED для merge-resolution та походження.

Окрема продуктова картка UI-COLUMN-CONTENT-01: лише підписи metadata, відображення відсутніх значень, усунення повторного заголовка та похідна штатна збірка. Власник source: columns_implementation у виділеній копії; QA: columns_qa; reviewer не є автором.

Allowlist документації: README.md, docs/orchestration/{CURRENT_BASELINE.json,FINAL_CURRENT_RU.md,STATE.json,QUEUE.json,CONTEXT_UA.md,PLAN_UA.md,DECISIONS_UA.md,ORCHESTRATOR_UA.md}, ця картка та evidence/current-20260926. AGENTS.md отримує лише датоване посилання на новий чинний обсяг. Історичні closeout/matrix/evidence не переписуються.

Дозволені перевірки: Git ancestry/blob/diff, статичний bos_control validate, нові вузькі column tests, контрольовані module_views, JSX lexical check, штатна frontend build та локальний isolated component render на синтетичних fixtures. Це не повтор старого full/PG/E2E/network browser suite. Усі фактичні результати й пропуски потрапляють у звіт.

Вихід: один main-кандидат зі збереженими source ancestors, незалежним review, manifest, позначеною поточною версією і snapshot tag. Після завершення нові продуктова розробка й автоматичні прогони не починаються без наступного доручення.
