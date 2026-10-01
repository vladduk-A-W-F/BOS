# Незалежний review guided-learning контракту

**Вердикт: CHANGES_REQUIRED.** Пакет має повне кількісне покриття, але дві частини обов'язкового контрактного scope потребують уточнення. Це висновок щодо авторського контракту; продуктова поведінка не перевірялася.

Картка: GUIDED-LEARNING-CONTRACT-REVIEW-R1-20261001. Reviewer: 01a0c05d-6eeb-79f1-a135-be66985b442f. Прийняття контексту записане до семантичної перевірки о 2026-09-30 23:05:30 UTC. Прийняту ID-карту та Q01–Q03 повторно не рецензовано; перевірено використані нові залежності.

## Точні входи

| Вхід | SHA-256 |
|---|---|
| Review admission | `30d45969e90f06cbf3a20de3d76e9e0dcae5090ee56616ed904fdad31df3b4e5` |
| Input manifest | `258e0478443b96acadf0715f6597e0eb6fe23385f8a5a4be9504ce7e230e6301` |
| Writer SESSION_CAPABILITIES.json | `4902e0bf6d508848dbe62c5a3c907f68a2ca4293ad3717b69e0de029a4ee5e02` |
| Semantic CONTRACT_CANDIDATE_UA.json | `faf6588f755a43de12b45c9b30256fb07ef380e87a6c22f5be4ecbb652932753` |

Source: `D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo`, HEAD `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`. Збіглися 13/13 входів manifest та 24/24 source-хеші. Усі 293 writer evidence refs мають наявний файл, ненульовий symbol, коректний діапазон рядків і точний file SHA. Перевірка метаданих посилань не є виконанням або автоматичним доведенням семантики.

## Findings

### GCR01 — P2: Clear/reset не має source disposition або явної прогалини

Writer перелічує дев'ять подій lifecycle, semantic candidate — сім, але жоден не визначає clear/reset. Чинний change приймає start/pause/tour/navigate/check; start повторно використовує запис тієї самої identity, pause зберігає progress/current_step, невідома дія відхиляється. Отже, ні start, ні pause, ні зміна ролі не є підтвердженим reset прогресу.

Наслідок: Інтегратор не може визначити дозволену поведінку початку заново, межі локального очищення та збереження серверного прогресу. Обов'язкова частина scope лишилася без висновку.

Місце: [lifecycle](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/writer-r1/SESSION_CAPABILITIES.json:2123); [lifecycle_source_alignment](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/enablement-final-r1/CONTRACT_CANDIDATE_UA.json:82).

Джерела: [training/service.py:234–259](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:234) — change start/pause/tour; [training/service.py:260–297](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:260) — change navigate/check/unknown action; [operations/middleware.py:53–57](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/operations/middleware.py:53) — training_progress observer allowlist; [training/urls.py:4–9](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/urls.py:4) — urlpatterns. Хеші всіх джерел наведені у REVIEW.json.

Виправлення: Writer додає окремий CLEAR_RESET із точними source refs: у перевіреному training API скидання не підтримується. Enablement явно фіксує unsupported/implementation_gap та очікувану межу: локальне очищення не є скиданням серверного прогресу; жодних нових reset-прав, видалення сесій або повторного проведення ERP/CRM. Для майбутнього reset визначити owner і окреме рішення інтегратора; можна прив'язати до GC-F05/GC-F06 без додавання нового продуктового API.

Власник корекції: writer: `01a0be9f-b413-7822-9f93-16ba69f4f00f`; semantic: `01a0f2ce-270f-7ac3-bea0-1447f87aed61`.

Критерій закриття: У новому writer/semantic snapshot є явний CLEAR_RESET disposition, той самий source pin, source refs та узгоджені межі прав/збереження даних. Лише контрактна корекція; runtime NOT_RUN.

### GCR02 — P2: Пропуск denied/not_applicable не визначає наступний крок і завершення

Restriction кейсу 01 наказує пропускати недоступний ролі вид зі станом denied/not_applicable, не completed. Не визначено, коли обрати denied або not_applicable, чи розблоковується наступний крок і як це впливає на завершення уроку. У pinned source observer отримує числовий answer замість operation/crm; session_state відкриває наступний крок лише після valid і не має not_applicable. Загальна позначка candidate/proposal зберігає чесну межу реалізації, але не усуває неоднозначність цього нового правила.

Наслідок: Дві реалізації можуть або назавжди заблокувати сценарій observer, або зарахувати пропущений обов'язковий крок у завершення уроку. Рольовий контракт не дає критерію перевірки такого результату.

Місце: [case_application BOS3-CASE-01 restriction_uk](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/enablement-final-r1/CONTRACT_CANDIDATE_UA.json:48); [GC-F05/GC-F06](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/enablement-final-r1/CONTRACT_CANDIDATE_UA.json:77).

Джерела: [training/service.py:167–175](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:167) — observations observer conversion; [training/service.py:179–210](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:179) — session_state valid/unlocked/completed; [training/service.py:260–265](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:260) — change locked target gate. Хеші всіх джерел наведені у REVIEW.json.

Виправлення: Розвести чинне observer->answer і майбутній role-specific skip. Для proposed denied/not_applicable зазначити умову, блокування/перехід, вплив на lesson completed, доказ і поведінку після зміни ролі; або позначити саме це правило як невпроваджену залежність GC-F05/GC-F06 без твердження, що крок уже можна пропустити. Denied не надає бізнес-прав і не доводить успіх.

Власник корекції: semantic: `01a0f2ce-270f-7ac3-bea0-1447f87aed61`; writer_consulted: `01a0be9f-b413-7822-9f93-16ba69f4f00f`.

Критерій закриття: У новому semantic snapshot є одна узгоджена таблиця/правило переходу для недоступного кроку з явним source status та gap IDs, без зміни прав або коду.

### GCR03 — P3: У кейсі 03 залишилась закрита умовна залежність від writer

Фраза «якщо він підтверджений writer» лишає враження відкритої перевірки command path. Writer вже вказує create_task через operations preview/confirm, а semantic case_source_alignment це повторює. Непідтверджена частина — прив'язка receipt до training step, а не існування command path.

Наслідок: Читач case_application не може однозначно відрізнити завершену source-перевірку від майбутньої реалізації GC-F03.

Місце: [case_application BOS3-CASE-03 sequence](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/enablement-final-r1/CONTRACT_CANDIDATE_UA.json:50); [case_source_alignment BOS3-CASE-03](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/enablement-final-r1/CONTRACT_CANDIDATE_UA.json:70); [case_capabilities followup](D:/3/BOSDev/evidence/resume-solutions-20260930/main/guided-author-snapshots/writer-r1/SESSION_CAPABILITIES.json:2763).

Джерела: [tasks/commands.py:84–101](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/tasks/commands.py:84) — prepare create_task; [tasks/commands.py:140–163](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/tasks/commands.py:140) — preview/apply task receipt; [training/service.py:153–163](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:153) — observations followup predicate; [training/service.py:285–287](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:285) — change stamp persistence. Хеші всіх джерел наведені у REVIEW.json.

Виправлення: Замінити умовну фразу точним посиланням на підтверджений create_task preview/confirm; окремо вказати partial/GC-F03 для step->receipt binding і чинний predicate видимого неархівованого task з assignee/deadline. Не вимагати task done і не проводити новий платіж.

Власник корекції: semantic: `01a0f2ce-270f-7ac3-bea0-1447f87aed61`.

Критерій закриття: Case application і case_source_alignment узгоджені, умовне очікування writer прибране, GC-F03 збережено.

## Покриття та підтверджені межі

| Частина | Результат незалежної звірки |
|---|---|
| 12 lesson fields + 12 step fields + 5 session requirements | 29/29; 5 exists, 20 partial, 4 implementation_gap. Alias goal_uk/title_uk/step_id відділено від буквальних полів API. |
| П'ять видів кроків | information — implementation_gap; інші чотири — partial. Чинні answer/operation/crm не названі повною реалізацією п'яти видів. |
| Три кейси | Чинні predicates і command paths узгоджені з кодом; case03 followup не вимагає task done або receipt. Семантичні послідовності є proposal. GCR02/GCR03 уточнюють їх. |
| Сім CAP | CAP-LESSON-VERSION — gap; решта шість — partial. Відсутність receipt binding, full expected_context, server next_step відображена. |
| Вісім GC-F | 8/8, усі посилання gap_ids існують. Групи не є виконаною реалізацією. GCR01 потребує явного clear/reset disposition; GCR02 — конкретного role transition. |
| Ownership і права | Server user/role + installation/fixture/case identity; UUID не дає чужих прав. Observer може писати навчальні відповіді через вузький middleware виняток, але не ERP/CRM. Case03 — CEO. |
| Read/write paths | GET перераховує стан без запису progress; POST start/pause/tour/navigate/check працюють через training service. Operations proposal належить user/role/auth session; CRM окремо звіряє session UUID і source PK. |
| Persistence і completion | progress зберігає stamp, не відповідь/час/повний source snapshot/receipt. Domain fact не доводить виконання саме цим користувачем у цьому проходженні. |
| Pause, reentry, mismatch | start/pause не стирають progress; GET може обчислити needs_recheck без DB write. Нова роль/fixture має іншу identity; lesson version та повний client expected_context лишаються gaps. |
| Already executed | Підтверджений існуючий CRM handoff та replay того самого proposal відокремлені від нового proposal. Не заявлено загальної гарантії no-double-write для будь-якої нової команди. |
| Synthetic UAH | 500/140/360/120; LOT-A 250, LOT-B 20 hold; 16 400/10 000/6 400 грн збережено як навчальні факти. План, контакт та задача не підміняють відвантаження або платіж. |

Загальна межа candidate/proposal і GC-F01–08 сформульована чесно. За перевіреними новими твердженнями не виявлено підміни запропонованої schema/API реалізованою функціональністю. Це не скасовує зазначених дефектів повноти контракту.

## Мінімальні наступні залежності

1. Writer та enablement виправляють GCR01–GCR03 у нових авторських snapshot; прийняті попередні результати не переписуються.
2. Main готує новий exact manifest, sole integrator визначає scope повторного review лише змінених контрактних частин.
3. Після окремого прийняття контракту інтегратор може призначити implementation залежності: lesson/version/source binding (GC-F01/02), типізований результат і receipt link (GC-F03), kind/role/error/pause правила (GC-F04/05), current/next (GC-F06), FAQ/acceptance (GC-F07), явне рішення щодо backend prerequisite case03 (GC-F08). Цей review не дає дозволу реалізувати їх.

## Перевірки та обмеження

Виконані лише читання файлів, JSON parse, SHA-256, перевірка HEAD, зіставлення метаданих та ручний статичний review. Машинні перевірки: 13/13 manifest, 24/24 source SHA, 293/293 evidence ranges, 29/5/3/7/8 coverage; невідомих gap IDs немає. Перевірка symbol тут означає наявність назви та ручне читання релевантного коду, а не parser-based resolution усіх довільних label.

Product executions = **0**. Runtime, browser, progress persistence in a running system і behavior QA — **NOT_RUN**. App/import/Node/JS/build/tests/PG/E2E/HTTP/DB/process/resource/network probes не запускалися. Записано лише REVIEW.json і REVIEW_UA.md у виділений review-каталог. Джерело, авторські пакети, canonical, DB та історія спроб не змінювалися. Модель і reasoning effort не підтверджені спостереженням.

**contract_accepted=false; guided_integration_implemented=false; TECHNICAL_READY=false; PILOT_ALLOWED=false; MVP=false.**

Повний машинний ledger входів, source-хешів, findings та перевірок: [REVIEW.json](D:/3/BOSDev/evidence/resume-solutions-20260930/integrator/guided-contract-review-r1/REVIEW.json). Хеш цього Markdown зберігається в JSON; хеш JSON повідомляється зовні після фінального запису.
