# A08 · поточна цілісність оригіналу перед чинним ERP-допуском

**Висновок: перевірка потрібна в A08.** Checksum, перевірений лише під час download/review, не захищає складський допуск або зміну версії після пошкодження оригіналу. Це уточнення використання того самого приватного документа в чинних guards, а не нова операція, B08/OCR чи переінвентаризація 85 шляхів / 12 місць.

## Реальний red на поточному коді

`tmp/a08_erp_document_integrity_tests.py` — один метод із трьома сценаріями. Створено нову синтетичну SQLite. Документ спершу має `approved`, правильний SHA фактичних байтів і поточну версію. Справжній HTTP preview проходить. Після нього підмінено тільки `content` через SQL; checksum/status/code/revision залишено незмінними. Далі виконується справжній HTTP confirm.

| Чинна дія | Фактичний результат до правки | Очікуваний результат |
|---|---|---|
| `erp_quality`, result=approved | 200, `Lot.quality=approved`, `available` 0→10, Inspection/Event/receipt створено | 422, складський допуск, Inspection/Event/receipt і mutex без змін. |
| `erp_change` | 200, новий ChangeOrder draft, Event/receipt створено | 422, ECO/Event/receipt і mutex без змін. |
| `erp_apply_change` | 200, Item revision A→B, ChangeOrder approved, Event/receipt створено | 422, версія/стан/Event/receipt і mutex без змін. |

Результат: **1 метод, 6 failed assertions, errors=0; exit 1; 0,255 с.** Точні HTTP-відповіді, changed_models та SHA — `tmp/a08_erp_document_integrity_before.json`; повний лог — `tmp/a08_erp_document_integrity_before.log`. До preview всі три джерела справжні й валідні. Зміна bytes після preview не змінює чинний `erp.fingerprint()`, який містить лише ID/checksum/status документа. Тому перевірка лише preview або тільки збереженого checksum недостатня.

Команда з `/workspace/sites/bos-original-refined`:

```bash
PYTHONPATH=/workspace/scratch/c7b51e996a9f/tmp:/workspace/sites/bos-original-refined PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=verification_settings BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/check_a08_erp_red_389bb4b1.sqlite3 BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/a08_erp_red_media_389bb4b1 BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages A08_ERP_DOCUMENT_EVIDENCE=/workspace/scratch/c7b51e996a9f/tmp/a08_erp_document_integrity_before.json /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python manage.py test a08_erp_document_integrity_tests --noinput --verbosity 2
```

## Мінімальні межі зміни

1. Єдиний A08 accessor перевіряє фактичне джерело: bound private file або legacy BLOB/text-only за прийнятим контрактом. Не повторювати різні варіанти hash-логіки в ERP.
2. `accepted_documents(item, documents)` зберігає чинний результат `list[kind]`. Відсутній, пошкоджений або непідтверджений оригінал робить відповідний kind неприйнятним. Перехоплювати тільки очікувану типізовану помилку цілісності/відсутнього джерела; не приховувати довільні programming errors.
3. `usable` отримує false для такого сертифіката. Snapshot/дашборд залишається 200, кількість `available` для партії стає 0, а тип документа лишається у `missing_documents`. Для зрозумілої діагностики можна додати окрему причину `пошкоджений оригінал` / `оригінал відсутній`, не змінюючи сам kind: `erp.experience` використовує kind як машинний ключ для наступної дії.
4. `quality` з result=approved уже відмовляє, якщо список неприйнятних документів непорожній. Потрібна лише підсилена перевірка всередині чинного guard. `blocked`/`rework` не повинні стати неможливими через пошкоджений сертифікат.
5. `change` та `apply_change` після чинних status/latest/revision умов викликають той самий accessor і дають контрольовану помилку українською. `apply_change` перевіряє заново в межах транзакції, навіть якщо створення ECO раніше пройшло.
6. Не змінювати фізичне приймання в quarantine/pending: відсутній сертифікат не дорівнює забороні зафіксувати отримані матеріали. `newlot`/`attach` не отримують нових незапитаних business restrictions; використання, резерв, старт і відвантаження вже залежать від `usable`.
7. Не підміняти незмінний checksum actual hash, не скидати історичні status автоматично й не переписувати receipts. Пошкодження описує поточну непридатність доказу, а не привід змінювати минулі події.
8. Новий private-file варіант додається до цього самого corruption тесту після появи FileField; missing/corrupt bound file ніколи не бере валідний legacy BLOB як fallback. Кеш із TTL, черги та глобальне сканування документів на кожний dashboard не потрібні.

## Перевірка після мінімальної правки

- Повтор цього методу: усі три confirm дають 422 та нуль змін після preview.
- На валідному оригіналі старі A06 позитивні quality/change/apply_change залишаються зеленими.
- Окремо фактичний snapshot із пошкодженим required document: 200, available=0, kind у missing_documents, зрозуміла діагностика без внутрішніх шляхів.
- `blocked`/`rework` і приймання pending не блокуються цілісністю стороннього документа.
- Чинний A06 concurrency/mutex набір повторюється; справжній PostgreSQL лишається окремим доказом.

Це деталізація DOC-02/DOC-07/DOC-19 основного `A08_REGRESSION_PLAN_UA.md`; кількість задач, оцінка A08 3–5 людино-днів та заморожений інвентар не змінюються. Checkout не редагувався, робочі БД/файли не відкривалися.
