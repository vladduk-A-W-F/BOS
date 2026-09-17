# A08 · передумови синтетичних positive fixtures

Перегляд вихідного коду 11.09.2026, поточний A07 working tree; checkout не змінювався. Пошук `checksum` охопив усі Python-файли проєкту, крім історичних evidence та міграцій. Реальні БД не відкривалися.

**Виконуваних Document positive fixtures із `checksum='a'*64`, вигаданим checksum або іншим явно непов'язаним hash не знайдено. Setup-only виправлення наразі не потрібне.**

| Fixture / шлях | Фактичний SHA | Наслідок для A08 |
|---|---|---|
| `operations/test_access.py`, `A04SyntheticCase.make_document` | `sha256(content).hexdigest()` | Усі похідні A04 read/download/review fixtures мають валідний BLOB. Старі assertions не змінювати. |
| `operations/test_review_response_projection.py` | Успадковує A04 fixture; змінюється тільки contract | Positive review має залишитися 200 після integrity check. |
| `scripts/access_fixtures.py` | Успадковує A04 fixture; review надсилає її фактичний hash | Gate 4 дозволений download/review не потребує послаблення. |
| `operations/test_document_mutex.py` | SHA фактичних `b'A06 synthetic certificate revision A'` | A06 interleaving/ordering fixtures залишаються валідними. |
| `erp/test_concurrency.py`, helper `document` | SHA фактичного UTF-8 content | No setup changes. |
| `seed_bos_demo.py`, `seed_erp_demo.py` | SHA `text.encode()`, BLOB пустий | Навмисний валідний legacy text-only; accessor має підтримати точний SHA тексту. Не заповнювати BLOB лише для проходження тесту. |
| `scripts/check_operations.py` | Positive download/review використовують результат справжнього upload | Hash уже обчислює parser із оригіналу. Новий FileField не повинен змінити observable assertions. |
| `fixtures/synthetic/transfer.py` | SHA оригінального BLOB для всіх Document | Є порожній оригінал із непорожнім derived text: потрібен саме `sha256(b'') → b''`. Це не дефект fixture. |
| `erp/test_value_boundaries.py` | SHA всіх 256 значень байта та додаткових non-UTF8 байтів | Не декодувати BLOB у текст; checksum правильний. |
| `erp/test_data_preflight.py`, `scripts/check_data_transfer.py` | SHA фактичних raw/proof bytes | No setup changes. |
| `erp/test_data_transfer.py` | Окрема мінімальна таблиця `demo_record`, не Document; checksum відповідає synthetic binary | Не переносити сюди HTTP Document-вимоги; це typed transport proof. |

Виняток іншого типу: старі `ChatFile` fixtures закономірно не заповнюють checksum, бо такого поля ще немає. Нове поле має безпечний непідтверджений default, а не автозгенерований hash порожнього файла. A04 history/archive metadata positives не повинні раптово вимагати verified download, якого ці тести не роблять. Для нових positive private-accessor tests потрібно створити фізичний файл і зберегти SHA фактичних байтів. Legacy ChatFile migration tests навмисно залишають hash непідтвердженим до явної перевірки копії.

Якщо повний A08 verify знайде ще неврахований синтетичний positive із неправильним checksum, допустиме лише виправлення setup: обчислити hash тих самих незмінених байтів, зберегти старі assertions і описати prerequisite. Негативні тести пошкоджених файлів не «ремонтувати», runtime integrity check не послаблювати.
