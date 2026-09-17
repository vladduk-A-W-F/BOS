# A06 · повторне збереження фінансової форми

11.09.2026. Джерело: HEAD `92097ecd0f7d40776c793c0405ac80b16bb5f0b8`, поточний `frontend/boss_app_source.html`. Перед роботою прочитано `docs/PROGRESS_UA.md`.

Кандидат: `a06_frontend_candidate.html`. Точний патч: `a06_frontend.patch`. Checkout, бази та інші компоненти не змінювались. A04 guard, localStorage, AuthGate, fetch wrapper та первісна стилістика збережені.

## Поведінка

- Кожна форма має окремий контролер наміру в React ref. UUID v4 створюється через `window.crypto.randomUUID()`; fallback використовує `getRandomValues`, версію 4 та RFC-варіант. Без доступної криптографії запит не відправляється.
- POST містить `Idempotency-Key`. Однаковий повтор після помилки мережі, 409 або непрочитаної відповіді повторно використовує попередній ключ і тіло.
- Зміна поля після помилки скидає намір. Додатково begin порівнює серіалізоване тіло: інший payload не може отримати попередній ключ.
- Lock встановлюється синхронно до першого await. Повторний старт повертається без запиту. На час збереження поля, Save, Cancel і перемикач відкриття форми вимкнені; обробники також перевіряють lock.
- Помилка залишається біля форми, значення не очищаються. Після підтвердженої успішної JSON-відповіді форма закривається й очищається. Нове відкриття або явне скасування завершує попередній намір; наступне збереження отримує новий ключ.
- Контролер існує лише в пам’яті цього екземпляра форми; ключі не записуються в спільне сховище. Scope містить mode, user_id та role. Інший користувач/роль/режим ніколи не використовує попередній ключ. Перезавантаження або повторне відкриття компонента — нова форма, не автоматичний retry старої операції.

## Каталог знайдених фінансових HTTP create

| Джерело | Запит | Зміна |
|---|---|---|
| Served source: Bank.addTx | POST `/api/transactions/` | Стабільний per-form Idempotency-Key, lock, збереження форми після помилки. |
| Served source: Salaries.add | POST `/api/salaries/` | Окремий per-form Idempotency-Key, lock, збереження форми після помилки. |
| Served source: Salaries.pay | POST `/api/salaries/{id}/pay/` | Не create нарахування; не змінено цим патчем. |
| Legacy `frontend/boss_app_glass.html` | POST `/transactions/` через api.send | Не served source і не ціль цього підзавдання; не змінено. |
| Legacy `frontend/boss_app_glass.html` | POST `/salaries/` через api.send | Не served source і не ціль цього підзавдання; не змінено. |

Salary bulk loop у поточному served frontend **відсутній**. `ai_assistant/views.py::_create_salary` створює один запис через `save_salary`; інструкція про масові tool-виклики належить відкладеному legacy-адаптеру. Новий bulk workflow не додано. Перевірено, що незалежні екземпляри контролера дають різні UUID навіть для однакових даних; у майбутній масовій формі кожен рядок потребуватиме власного такого контролера, збереженого між повторами рядка.

## Перевірки і межі

1. `node tmp/a06_intent_checks.cjs tmp/a06_frontend_base.html` → exit 1, до правки helper відсутній; збережено `a06_ui_before.log`. Це початкова перевірка наявності контракту, не відтворення backend-дубля.
2. `node tmp/a06_intent_checks.cjs` → PASS. Перевірено життєвий цикл чистого контролера: UUID/fallback, подвійний старт, pending reset, повтор після release, зміна payload/поля, success/fresh form, scope та незалежні рядки. `a06_ui_after.log`.
3. Babel syntax та lexical references → PASS. Компіляція кандидата збережена тільки як `tmp/a06_frontend_candidate.js`.

HTTP/backend, React effect, фактичні натискання в браузері та браузерне приймання не запускались цим агентом. Pure helper checks не доводять поведінку мережі або browser gate. Після інтеграції root має виконати штатну збірку; серверні Idempotency-Key контракт і concurrency залишаються root-задачею A06.

SHA256 базового source: `33b6060055642a67ea0bcbbda0f7a2cc68dce76905b1cc488e61eebe05ce9b01`.

SHA256 кандидата: `c669c95ee8c4356b8a2c7964f22c8c17751fe2294a8ddf2275f3fc3751d712fd`.
