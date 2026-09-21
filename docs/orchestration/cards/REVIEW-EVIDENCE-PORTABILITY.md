# REVIEW-EVIDENCE-PORTABILITY

Пріоритет P1. Власник bos_evidence. Статус READY_EVIDENCE_COLLECTION. Залежності: немає.

## Проблема й доказ
У `620aeab2010c6c8327ce46c25bb62435bcf7f9e4` CONTINUATION_20260920_UA.md та portable EVIDENCE_INDEX описують окремі локальні receipt/raw і координаторський BoS-orchestration-state.json для PLAN-DOC-MATCH-CONTRACT, DOC-MATCH-SERVER і FLOW-READ-UI. Повний первісний raw і окремі hash-scoped незалежні verdict не опубліковані. Наявність індексу не замінює байти. Gate10 має portable raw/report/receipt, перевірені незалежно; його scoped PASS не скасовується.

## Дозволені файли й наступний крок
Читання: continuation reports/cards/indexes і доступні точні первісні receipts. Запис: нова docs/orchestration/evidence/continuation-portability/ та поточні orchestration посилання у review-гілці.
1. Скласти missing/present matrix для кожного receipt/raw/verdict та його source SHA/bytes/exit.
2. Якщо локальний інтегратор має оригінали, перенести тільки дозволені synthetic матеріали без секретів/клієнтських даних. Не вдавати доступ до його ПК. За відсутності — конкретний перелік файлів, BLOCKED_MISSING_ORIGINALS.
3. Оригінали не змінювати задля збігу SHA. Якщо потрібна редакція чутливого вмісту, позначити похідний redacted artifact новим SHA і не називати його оригіналом.
4. Незалежний reviewer перевіряє source→receipt→raw→verdict. Невідомий exit лишається UNKNOWN; mixed7 exit1 не перетворюється на загальний PASS.

## Приймання
Відтворювана карта доступності, точні hashes/байти, незалежний verdict для доступного scope й явний залишок. Повне виконання картки потребує необхідних первісних доказів; неповний пакет не знімає блокер.
Не повторювати тести для заміни втраченого evidence; не переписувати історичні свідчення, не змінювати readiness/AGENTS/дозволи. Браузерна доступність стенда зараз не підтверджується історичним receipt.
