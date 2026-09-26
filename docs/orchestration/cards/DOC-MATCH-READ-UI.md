# DOC-MATCH-READ-UI · явне читання документа закупівлі

20.09.2026, isolated continuation branch. Залежність: independently accepted
`operations/document_matching/server_adapter.py`, commit `67cc588`.

У CEO-картці закупівлі додано окрему секцію зіставлення. Користувач явно
обирає документ, постачальника й номенклатуру та натискає «Зіставити документ».
GET `/api/erp/purchases/<pk>/document-match/` приймає тільки ідентифікатори
через query-параметри. Purchase і Document перевіряються чинною Policy.
Відповідь `bos.document-match-read.v1` обгортає незмінений контракт
`bos.document-match.v1` і додає лише контекст читання/access revision.

Панель показує значення полів, сторінку, фрагмент, цитату, SHA-256 оригіналу,
джерела приймань і порівняння Decimal strings. Нове зіставлення прибирає
попередній результат; зміна джерел/доступу дає нейтральний 409, прострочена
HTTP-відповідь не повертає попередню чернетку на екран.

Сфера навмисно обмежена синтетичним навчальним форматом одного рядка й
повної закупівлі без ПДВ/додаткових витрат. Для звичайного документа UI
показує явну причину відмови. OCR та AI не підключені. `accept_draft`
означає лише узгоджену синтетичну чернетку: `operation_proposal=null`,
немає approval/confirm/posting кнопки та жодного запису до бізнес-даних.

Allowlist: views/urls; `erp/test_document_match_route.py`; frontend source та
generated artifacts; additive access catalogue/oracle/fixtures;
`scripts/check_document_match_ui.cjs`; тестовий harness
`scripts/check_flow_projections.cjs` (лише optional component/props); ця картка.

Перевірки: чотири нові HTTP tests PASS на окремій SQLite/private media;
п'ять actual JSX controlled cases PASS. Перший controlled запуск зупинився
на надто точному пробілі в assertion receipt-label; виправлено тільки
тестовий whitespace matcher, початковий raw збережено. Build і lexical
check пройшли. Попередні tests не повторювалися повністю. Додано один GET
до access catalogue зі збереженням усіх попередніх definitions/required
tests. Full access suite/PG/E2E та заборонені повтори не запускалися.

Evidence: sibling `continuation-evidence-20260920/document-ui`. Незалежний
review і окремий scoped browser helper мають власні receipts; ця картка
сама не є доказом повного document-to-posting сценарію. Готовність
TECHNICAL_READY=false, PILOT_ALLOWED=false зберігається.
