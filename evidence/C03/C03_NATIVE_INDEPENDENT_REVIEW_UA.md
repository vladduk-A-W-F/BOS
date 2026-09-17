# C03 native · незалежний вузький review

Scoped consensus: погоджую; блокуючих прогалин у двох native-файлах не виявлено.

Перевірено read-only `tmp/c03_restore_candidate/FROZEN_MANIFEST.json`, SHA `f53023310c76f76c755d7f05d77af9226083f60855f0b98aea27f1ea3b01ad94`: SHA двох файлів, базового check_restore та всіх перелічених evidence збігаються. Actual evidence: перший native run 18/18, exit0; `native-1.json` SHA `ca4e4c3b64886342d7490880dee37e9393cb5f63cf2750d6d65e4dbc70888c13`. Це прочитаний авторський запуск, незалежно його не повторював.

Diff строго додає два checks, returned counterparty PK та explicit old53 subset/exact56 table set. Старі 16 checks збережені; Tasks/Corrections helpers byte-identical stable core1. EUR4.56+17.39=21.95; USD123.45−2.34=121.11, paid2.34/AR0; UAH9801.07 перевіряється окремо точним decimal string. Archived EUR залишається в journal totals.

Actual HTTP upload/review/download зберігає literal CSV bytes/SHA. Після native restore звіряються Import/Line/Allocation/details/джерело/current summaries/journal/export, old session confirm403 і чотири domain no-change previews: id=null та первісний receipt literal-equal. Statement snapshot незмінний до/після цих перевірок. Stable core1 no-change preview відкочує atomic preparation і повертає результат до створення ActionProposal.

Порядок Tasks → Statements → Corrections правильний: незмінний B03 helper фіксує весь ERP+home snapshot. Task/home та C03 order/movement/invoice/paid зміни мають відбутися перед freeze цього snapshot; після нього додавання законних змін створило б хибний restore mismatch. Тут oracle не обрізано й не послаблено.

Перевірка була тільки читанням коду, diff, manifests і наданих logs/JSON. Нових тестових/серверних запусків, читання БД/private backup або canonical edits не було. Фінальний canonical C03 full обов’язковий незалежно від цього scoped consensus; PG/Windows/browser/upgrade/rollback цим review не доведені.
