# PLAN-UX: аудит трьох сценаріїв і одна наступна візуальна зміна

20.09.2026. **BRIEF_ACCEPTED_SCOPED; PRIVATE_READABLE_FACTS_ACTIVE; IMPLEMENTATION_NOT_ACCEPTED.** Це перше завдання відділу дизайну в наявній PLAN-UX, не нова конкуруюча frontend-картка. Роль — `bos_ux`; постійний виконавець — чат «БОС — отдел дизайна», `01a0bffa-3fc7-7bc2-9868-86164c6e0315`. Факт і стан його audit перевіряються за власним звітом; організаційний writer audit не дублює. Незалежний reviewer — root; інтегратор спільного коду — `/root/product_integration_continuation`.

**Історичний author-v1 snapshot, збережений без переоцінки:** INITIAL_REPORT.json має `PREPARATION_READY_FOR_INDEPENDENT_REVIEW`, повідомляє про19 оглянутих PNG і один запропонований increment; незалежний verdict pending. Нижче збережено контракт завдання і критерії review, а не нове доручення повторити audit. Візуальні висновки цього автора не прийняті організаційним пакетом.

## Поточний стан PLAN-UX: прийнятий brief і приватне завдання READABLE-FACTS

Root прийняв підготовлену специфікацію у вузькому обсязі `ACCEPT_SCOPED_DESIGN_BRIEF_FOR_PRIVATE_PATCH`: `D:/3/BOSDev/reports/root/DESIGN-INITIAL-ROOT-REVIEW-20260920.json`, SHA256 `b4bb8e0323d84853b724d457af29765959d5acf874a54039aca217f36a77becb`. Незалежний контролер також зафіксував `APPROVE_SCOPED_PREPARATORY_DESIGN_SPEC`: `D:/3/BOSDev/evidence/design-initial-independent-review-20260920.json`, SHA256 `ebff8a90c7e19924363c6501e8481e305b7c033b732cd6a3b2219a916940b081`. Це приймання brief/audit і одного запропонованого increment; не приймання зміненого продукту. Організаційний інтегратор не повторював візуальний audit. Історичний INITIAL_REPORT із pending verdict збережений без переписування авторства.

Поточне завдання `PLAN-UX/READABLE-FACTS` — **ACTIVE_PRIVATE_PRESENTATION_PREPARATION**. Джерело призначення: `D:/3/BOSDev/handoffs/design-readable-facts-20260920/ASSIGNMENT_FROM_ROOT_RU.md`, SHA256 `c4f9870383751ae35a0a1be22bb8caadd35ec35c3023cbbaa803c88aaf1d7441`. Вхід — окремий network-кандидат, повний source SHA256 `d95e2b05ca06d5190bd2a9429997981acf9886d9218fccf33200df0adf49a56a`; манифест64 `D:/3/Codex/2026-09-20/bos-execution/work/network-composition-evidence-20260920/candidate-alias-fixed.json`, SHA256 `3c4a3e6e69b138fb1e64d778e663741c3c03932cebd06e8fea4b4709fa03d214`. Прийняті screenshots646 є контекстом і не підтверджують вигляд цього кандидата.

Приватний workspace: `D:/3/BOSDev/handoffs/design-readable-facts-20260920/workcopy`. Новий точний allowlist автора всередині цього handoff: `workcopy/frontend/boss_app_source.html`, `original/frontend/boss_app_source.html`, `DESIGN_READABLE_FACTS.patch`, `MANIFEST.json`, `REVIEW_NOTES_RU.md`; власні звіти — у `D:/3/BOSDev/reports/design/`. Дозволено лише локальний CSS і presentation JSX у трьох наявних функціях `OrderSettlement`, `OrderSupplyOptions`, `PurchaseDocumentMatch`. Усі поточні метрики, зокрема борг/утримання/доступна оплата, точні числа, тексти попереджень, null/zero/access, назви доступності, handlers/payload/Policy/recovery/effects зберігаються; глобальний `.bos-order-trace` не змінюється.

Автор не змінює спільний frontend, generated assets, STATE/QUEUE, моделі, БД або runtime і не виконує build/browser/tests. Наступний крок — незалежний review приватного diff; лише `/root/product_integration_continuation` інтегрує й перебудовує після окремого приймання. Реалізація ще **не прийнята**, actual browser acceptance потрібна для кінцевого source в окремому обмеженому scope. TECHNICAL_READY та PILOT_ALLOWED залишаються false.

## Історичний контракт початкового аудиту (не повторне доручення)

Робоча копія чату: `C:/Users/user/.codex/worktrees/c8b3/repo`. Її HEAD перевірити перед початком; старіша default branch не є прийнятим UI. База організаційного пакета — `620aeab2010c6c8327ce46c25bb62435bcf7f9e4`; продукт прийнятих screenshots — `646d3b80597e087a1ada14221024ec40588996f0`, SHA256 `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`. Прийняті артефакти доступні read-only у `D:/3/Codex/2026-09-20/bos-execution/work/continuation-20260920` на checkpoint620. Матеріали `D:/3/Codex/2026-09-20/bos-execution/work/design-department-20260920` — handoff колишнього виконавця, не cwd чату; використати їх з авторством і не повторювати паралельний audit.

## Вхідні докази

Портативне джерело — [MANIFEST.json](../orchestration/evidence/continuation-646d3b8/MANIFEST.json), [фактичний ui-report.json](../orchestration/evidence/continuation-646d3b8/browser-attempt5/artifacts/ui-report.json) і [незалежне приймання](../orchestration/evidence/continuation-646d3b8/BROWSER_ACCEPTANCE_RU.md). SHA кожного використаного зображення брати з report/manifest; записати його у власний audit manifest. Збережена browser-attempt5 має Gate10 7/7 і три окремі bounded flows; це не повні S1/S2/S3 та не Gate6.

| Частина аудиту | Збережені зображення в `browser-attempt5/artifacts/` | Межа доказу |
|---|---|---|
| S1: замовлення, розрахунки, оплата | `uah-preview.png`, `uah-confirmed.png`, `flow-settlement.png`, `flow-payment-preview.png`, `flow-payment-confirmed.png` | Показані стани order/payment; не весь order-to-debt процес |
| S2: зіставлення документа | `flow-document-match.png` | Ordinary document з явним unsupported_document; не успішне OCR або supplier bill posting |
| S3: забезпечення і переміщення | `flow-supply-selected.png`, `flow-supply-preview.png`, `flow-supply-confirmed.png` | Показані selected/preview/confirm; не повна закупівля, приймання й якість |
| Адаптивність і діалог | `viewport-390.png`, `viewport-768.png`, `viewport-1440.png`, `viewport-390-dialog.png`, `viewport-768-dialog.png`, `viewport-1440-dialog.png` | Розмір viewport і стан звіряти з report; не приписувати кожному S1/S2/S3 стану всі три ширини |
| Масштаб і помилка мережі | `native-zoom-200.png`, `native-zoom-200-dialog.png`, `network-failure.png`, `network-recovered.png` | Уже прийняті стани продукту646; статичне зображення не перевіряє клавіатурну поведінку самостійно |

Неприйнятий network-код, нові фінансові значення та можливе майбутнє злиття PR2 відокремити у розділ «контекст без прийнятого зображення». Не переносити на них Gate10 або висновок про вигляд зі старих screenshots. Історичний brief [PLAN_UX_BRIEF_UA.md](../orchestration/PLAN_UX_BRIEF_UA.md) — контекст попередньої PLAN-UX, а не доказ нинішнього дефекту.

## Точний allowlist результату дизайнера

Історичний точний allowlist із початкового призначення нового чату — лише:

- `D:/3/BOSDev/reports/design/DESIGN_BRIEF_RU.md` — роль, правила компонентів і один наступний increment;
- `D:/3/BOSDev/reports/design/UI_DESIGN_AUDIT_RU.md` — фактичні візуальні спостереження S1/S2/S3;
- `D:/3/BOSDev/reports/design/INITIAL_REPORT.json` — авторський звіт за шаблоном, source, входи/виходи з SHA та межі;
- `D:/3/BOSDev/reports/design/INITIAL_REPORT_MESSAGE.md` — повідомлення контролеру.

Авторський звіт — за спільним шаблоном, зі своїм реальним CODEX_THREAD_ID. Новий чат має явне призначення відправити його через codex_channel.py до observer; деталі в REPORTING_UA.md. До product files, docs/design, shared frontend, STATE/QUEUE, БД, runtime, tests або CI цим першим завданням не записувати. Майбутнє перенесення специфікації в docs/design або diff потребує окремого allowlist і передачі єдиному інтегратору. Наявний опис майбутньої відповідальності за docs/design не розширює ці чотири початкові шляхи.

## Що підготувати

1. **Аудит.** Для кожного S1/S2/S3 записати хоча б одну перевірену візуальну оцінку: конкретне спостереження або «підтверджених проблем не виявлено» з межами огляду. Не вигадувати дефекти для кількості. Кожен finding має ID, scenario/state, шлях і SHA screenshot, viewport за report, область екрана, видимий факт, вплив на користувача, пропозицію та окремо неперевірені припущення. Пріоритет пояснити наслідком, не смаком автора.
2. **Правила компонентів.** Одна узгоджена таблиця для типографіки, відступів, ієрархії заголовків, таблиць/чисел/валют, джерел і документів, action controls, status/empty/error/restricted/stale, діалогів/фокусу та вузьких екранів. У кожному рядку: видимий стан, запропоноване правило, вимірюваний параметр/стан і спосіб майбутньої перевірки. Не називати запропоновані tokens уже наявними. Недоступні CSS-величини або контраст позначати «не виміряно», а не PASS.
3. **Один наступний increment.** Обрати рівно одну візуальну зміну після аудиту: один основний екран або один спільний компонент із явним переліком місць застосування. Дати проблему з finding IDs, схему до/після, тексти українською, запропоновані параметри, межі коду, залежності та конкретні acceptance criteria. Решту покращень залишити списком без другого пакета. Якщо доказів дефекту немає, запропонувати одну обґрунтовану зміну як пропозицію, а не виправлення доведеного багу.
4. **Авторський звіт з manifest-полями.** У INITIAL_REPORT.json зафіксувати source646, checkpoint620, SHA використаних входів/виходів, невиконані перевірки й фактичний стан роботи; додаткового manifest-файла поза початковим allowlist не створювати. Передати root на незалежний review та повідомити контролера.

## Вимірювані критерії першого результату

- В аудиті є окремі записи S1, S2, S3; кожне твердження про наявний вигляд має screenshot/path/SHA/state. Усі невидимі стани й network-контекст явно позначені неперевіреними.
- Таблиця правил охоплює дев'ять перелічених груп; кожне нове правило містить числовий параметр у CSS px або чіткий перелік станів/поведінки. Невиміряні поточні значення не підставлені з припущень.
- Наступний пакет містить рівно один increment і критерії для 390/768/1440 та 200%, з чесною відміткою, які стани вже є на збережених зображеннях. Критерії майбутньої реалізації: ключові суми/валюти/одиниці/кнопки не обрізані; довгі українські назви читаються; порядок заголовків і primary action однозначний; стан не позначений лише кольором; вимога чинного brief щодо основних touch actions не менше44×44 CSS px збережена.
- Для діалогу/дії, якщо вони входять у increment, прописано очікувані Tab/Enter/Escape та повернення фокусу. Статичний audit не оголошується новою перевіркою цих дій.
- Немає нових або прихованих бізнес-дій, зміни preview/confirm/replay, ролей, payload, валютної арифметики чи вигаданих документів/джерел.
- INITIAL_REPORT.json розбирається і містить manifest-поля; виходи обмежені чотирма шляхами; незалежний verdict root зазначений як pending до фактичного приймання. Нові browser/DB/CI runs для цього аудиту не виконуються.

## Завершення і наступний крок

Після передачі двох матеріалів і авторського JSON/повідомлення статус — `READY_FOR_INDEPENDENT_REVIEW`, не `UI_IMPLEMENTED`. Root приймає або повертає конкретні findings; після приймання окремо призначає публікацію документації або інтегратору одну реалізацію зі свіжим source/allowlist. Зміна source не успадковує приймання screenshots646 автоматично. Усі 11 gates, readiness/pilot=false та історичні обмеження залишаються чинними.
