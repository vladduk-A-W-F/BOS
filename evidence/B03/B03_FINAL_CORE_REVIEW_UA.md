# B03 — фінальний незалежний висновок щодо core

12.09.2026. **Погоджено перевірений B03 product core для інтеграції; попередні конкретні блокери закрито.** Це scoped source/evidence consensus, не приймання всього B03 або BoS MVP. Canonical full verify та фінальний access-пакет окремі; браузер, PostgreSQL, Windows і CI тут не виконувались.

Reviewer не редагував checkout або кандидат, не запускав нових tests/restore/A09/серверів і не читав оригінальні DB/media. Висновок ґрунтується на повному попередньому source review шести writer paths, фінальному diff і фактично виконаних автором/root синтетичних доказах. Попередній checkpoint зі знахідками збережено в `B03_CORE_REVIEW_UA.md`.

## Точна версія

`tmp/b03_candidate/FINAL_CORE_REVIEW_CHECKPOINT.json`: SHA256 `f006fa26eb165d151057e3b3bf29aff679c72955a4a836e59922676ee992cfeb`. Самостійно звірено15/15product files і5/5evidence hashes без розбіжностей. Aggregate sorted compact JSON словника15source: `227fddbe137e0a75fc9a6e67d3bea13375a51c2a1035a5841838552a03c7ec7f`.

Ключові source SHA:

| Файл | SHA256 |
|---|---|
| erp/corrections.py | `590f986c528b27293fda666e50b3f8e3daeeeb3d2c0d74c48b80fb8972f95705` |
| erp/balances.py | `1402b9181db52325e4a67c860d1044d342964140c1c6861e8722a6fa0901c004` |
| erp/correction_views.py | `adb8e918db83dc217319cfc62f721b9b4fa94a9ed19aa6e63ecd7f74862e2dd5` |
| boss_project/policy.py | `029e5a1432bca7eec763e834f416bb6de2e0fbeba6015f71addd2cf8e4b3d8b8` |
| operations/service.py | `a8353a3cfbd4f77efcfb98c5316bb00eea838a9ab550f2b6a9b93d4595cca421` |
| operations/projections.py | `8d3c1fd8600f24e98a572eb0e4deb11635aa28390ac4ae2d5ac6bba026a8eb7e` |
| erp/experience.py | `0f81cef52c74b70738a4a97ebf97ae4b8e44435a060e8b5c86f43ab3eb6ce936` |
| erp/migrations/0005_source_corrections.py | `69d3e9edeb7acb778ed0250ba79f1b232097440ff8f0ad86f656b9990af1257f` |

Повні15source SHA та прочитані tests/evidence SHA записані окремо в `B03_FINAL_CORE_REVIEW_FACTS.json`.

## Закриття останніх блокерів

1. **Дублікати nonCEO events.** `projection-red.log` реально отримав4IDs замість3unique. Final projection робить ID-dedup зі збереженням insertion order; кожен recent Event один раз, correction_events лишається окремим ledger-linked read. Тест actual return + manager snapshot проходить у55/55.
2. **Прихований financial state у next_step.** Ранній `projection-red.log` містив неправильний fixture URL404 — це не доказ продуктового витоку. Наступний `projection-compat-red.log` із правильним endpoint реально показав різні manager JSON до/після credit. Final nonCEO branch стоїть перед unresolved_returns/active financial allocations; manager JSON до/після credit буквально рівний, тест пройшов. CEO зберігає точний unresolved return і customer_credit no-action flow.

Попередні historical snapshot permissions, existing supplier lot у preview, ambient Decimal HTTP та cancelled BOM ETA виправлення залишилися незмінними від перевіреного core checkpoint. Жодного обходу source guard, обнулення historical snapshot або послаблення credit cap у цих final fixes немає.

## Прийнята бізнес-поведінка

Всі шість дій використовують strict closed payload, canonical operation UUID і server identity. Dispatch бере ERP mutex; reread/replay відбувається до нового domain Event. Same proposal та new proposal/same intent повертають canonical receipt, інший payload під тим самим ключем відхиляється. Early replay не переписує первісний Event.result/actor.

Cancellation використовує grossQ−executed−cancelled, звільняє тільки власний зайвий резерв newest-first і не змінює stock/Movement/gross quantity. Shared helpers охоплюють reserve/ship/job/receive, request allocation, coverage/ETA, B02 live totals. Imported PO еталон source8/pre3/current5→receive2/cancel1/return1 залишає received2/open2 і первісний B02 snapshot/receipt.

Supplier return виходить тільки з actual receipt origin та вільного фізичного залишку, створює negative Movement/GoodsReturn/pending claim. Customer exact return має per-source і старий aggregate lot+line cap, створює blocked lot і reference=source lot.code; legacy return path не переписано. Cost бере вже збережений source Movement через cumulative Fraction/integer cents, не переоцінює історію за поточною ціною. Actual три частини Q0.001 з sourceQ0.003/cost0.01 дали0.00/0.01/0.00 уEUR/USD/UAH.

Invoice credit використовує ordinal InvoiceLink snapshot та cumulative budgets із exact Invoice.amount equality. Перевіряються одночасно global GoodsReturn capacity, invoice-line Q capacity та залишковий monetary budget після commercial credit. Actual zero/nonzero budgets0.00/0.01, commercial+physical conflict, повторне кредитування того самого повернення між двома invoices і full reversal перевірені. Reversal копіює первісні allocations. Claim confirmation з amount0.00 відрізняється від pending null, потребує actual verified Document; повторна confirmation заборонена.

Settlement відділяє net/receivable/customer_credit, чинний payment cap бере receivable; Invoice.amount/paid/старі Events, Transaction/Salary/cash credit/return діями не ремонтуються. Actual amount123.40/paid100/credit24.68 дав customer_credit1.28, reversal — receivable23.40. Це не банківський refund, AP чи повна бухгалтерія.

Outcome GET має exact action+UUID, перевіряє поточні role/source/historical permissions та повертає projected canonical receipt без payload/writer/new Event. Missing/hidden404unknown не доводить відсутність commit. GoodsReturn current source/result і snapshot documents звіряються окремо; hidden historical source прибирає return/claim/event/outcome/replay. Return aggregates показують null/restricted замість неповної суми. Financial credit/claim amounts/reasons/source budgets не виходять через nonCEO projections. Історія старше300movements/150events відновлюється через повні scoped source/result IDs та ledger-linked correction_events, без загального Event dump.

## Фактичні перевірки

| Доказ | Фактичний результат і межа |
|---|---|
| compat-green.log |55/55,32.056s:18B03 tests і погоджений старий B01/B02 subset; обидва останні blockers green. Це не повний canonical test suite. |
| final-sources-1.log |3/3,6.684s: request allocation після cancellation/return, multi-invoice physical-return cap і concurrent legacy reserve/ship/transfer cross cases. |
| gate5-final.json/log |99/99,75.460s;110/110unique ERP records,33actions, немає missing/duplicates/runner failures. |
| preservation-1.log |3/3,8.946s: усі6new ledgers populated; actual SQL constraints/PROTECT, reverse refusal доDDL з exact schema/rows/sequences/migrations, full typed53/receipt/source integrity. |
| typed-compat-red→green |Старі47 oracles реально відмовили на53. Explicit fixed47+6 table set →2/2,12.044s; старі source/receipt/ID/sequence/media assertions залишилися. |
| SQL atomicity |Реальний BEFORE INSERT trigger на SupplierClaim відмовляє після return path, уся транзакція відкочується, proposal receipt=None; після видалення лише власного trigger той самий intent створює один GoodsReturn. |
| Root native restore |14/14actual HTTPS, усі6ledgers,7same-intent replays, snapshot equality та source bytes; деталей нижче. |

Gate5 baseline_b02 самостійно порівняно з canonical B02: буквально ті самі88methods/92records/27actions і coverage entries. Старий baseline_a06 також буквально збережений. Додано11methods,18currency records і6actions. Фінальний manifest SHA `3b8c10d49cf5b0725e22af164605d171dd0a15f461223c3abae6f93b8e16747c`; checker тепер вимагає exact99/110/33, не виводить очікування з discovery. Gate5 JSON SHA `8e9fd838986e561c9d5b6c66c67988eb7a3cd0e554f9fdb6d37474f7f94b36a1`.

Concurrent real HTTP pairs охоплюють усі6actions×3currencies, distinct intents на той самий source budget, two proposals/same intent, cancellation↔receive/ship/reserve, supplierreturn↔transfer/reserve, credit↔payment. Це SQLite proof. Не робиться висновок про PostgreSQL scheduling або невиконані комбінації акторів.

## Історичні migration fixtures та restore

B01 fixture спочатку створює справжній approved PO черезHTTP на current runtime, доводить порожній B02/B03 ledger і відокремлює пізні порожні міграції до0003 ПЕРЕД before-state. B02 fixture створює справжній import, доводить порожні6B03таблиць та pin0004 перед before-state. Старі state/assertions не змінено; populated джерела не стиралися. Фактичні попередні compatibility reds збережені; green B01 має refused=true/changed=[]. Новий populated B03 reverse тест окремо перевіряє current full schema без втрати будь-якої нової таблиці.

Root `tmp/b03_restore_candidate/evidence/restore-green-1.json` SHA `969db30312390a1212afba9e05107aca27e6ca10b9a77f58fd5db5b9524b7917` має complete=true,14/14. Source-read fixture попередньо звірено з real B02 template. Фактичні B03 counts cancellation2/release1/return2/claim2/adjustment2/lines2, native53 tables; restored snapshot SHA `17efcfd90a19f3d7aa407fb514d8b74cee68661a8b5df02aa540be29fc4418b0` однаковий до/після,7canonical receipts відновлено через outcome/new proposals, new_business_effects0. Run має version0.2.12-dev, бо це кандидат до canonical version bump; його не слід називати вже завершеним B03 release/full verify.

## Межі фінального висновку

У перевіреному core не лишилося конкретних blocking findings. Фінальний file manifest із access3files і повний canonical verify ще мають бути виконані/звірені root. Цей висновок не приймає фактичний browser UX, PostgreSQL/Windows/CI, наскрізний E2E, upgrade/rollback чи всю готовність MVP. Усі11gates лишаються. A09 mandatory full22 мав client413green, але попередню нестабільність не оголошено усунутою й додаткових спроб reviewer не робив.
