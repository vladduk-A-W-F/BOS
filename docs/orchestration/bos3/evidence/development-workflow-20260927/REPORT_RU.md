# B30-DEV-WORKFLOW: авторский отчёт

27.09.2026. Автор root, независимые reviewers bos3_candidate_review (управление) и start_overview_review (отдельный CLI). Исходный документационный HEAD 54764b0ac33e7e7a0f044a21a7ea1899410b6fb8. Продукт остаётся f55a15de4006d10c0d7c65f8a2ca8499fbb99819; runtime 33d7d387aa582c04339a91ae94361948ea67904c.

## Поручение и причина

Прямое поручение владельца в этом чате: «КАК ПРАВИЛЬНО НАСТРОИТЬ РАЗРАБОТКУ СДЕЛАЙ ЭТО». Отдельно прочитано прямое недельное поручение владельца в чате контроля 01a0bf0f-a9e4-7631-87e1-bb1aed03f174. Существующая цель и её уточнение cutoff 04.10 23:59 подтверждены сохранёнными материалами контролёра; здесь новая цель не создаётся. Снимки OWNER_WEEK_TARGET_RU.md, observer-control-receipt.json, automation-verification.json и weekly-plan-independent-review.json сохранены без изменения байтов. Это датированные свидетельства контролёра, не новая проверка native goal из этого чата.

Обнаружены две реальные проблемы управления: canonical календарь всё ещё разрешал работы 05–11.10 после нового запрета; штатный tools/bos_control.py читал только исторические STATE/QUEUE, а не действующий BoS 3.0. Исправления управления и инструмента разделены на атомарные карточки.

## Изменение управления

Синхронизированы текущая секция AGENTS.md, BOS3_EXECUTION_RU.md, ACTIVE_WORK_PLAN_RU.md, TEAM_CURRENT_RU.md, CONTROL_STATE.json, EXECUTION_PROMPT_RU.md и RELEASE_PLAN_RU.md. Добавлен DEVELOPMENT_WORKFLOW_RU.md: единый интегратор, конкретная карточка/allowlist/source/DoD, независимый reviewer, отдельный QA, последовательный commit, PR и зеркало, предел времени, отчёт и точные границы при all-blocked. Пять приоритетов содержат причины, владельцев решений и следующий шаг. Исторические карточки и результаты сохранены, не превращены в новые назначения.

Новая read-only матрица bos3_candidate_review подтвердила: готовой независимой продуктовой карточки без нового допуска или feedback сейчас нет. Разрешённая независимая работа этого хода относится к прямой настройке разработки. B30-PREVIEW-DELIVERY явно BLOCKED до точного ответа владельца; общий новый START или JSON не снимает этот blocker.

Контролёр передал новый существенный статус: его native goal переведена в BLOCKED, не COMPLETE, после трёх последовательных ходов с тем же обязательным blocker. Сохранён goal-blocked-audit.json с native_status_confirmed_at_utc 2026-09-27T13:35:53.918653+00:00. CONTROL_STATE содержит этот reported status и источник. Это не отменяет текущую разрешённую настройку root, не меняет automation ACTIVE/15min и не разрешает доставку. Получение отчёта не вызвало ACK/новую goal.

## Review и проверка

Первое docs-review обнаружило преждевременную формулировку, будто --scope bos3 уже интегрирован. До интеграции во все оперативные инструкции добавлено явное предупреждение. Финальная применимость команды будет подтверждена отдельными code/oracle review, synthetic QA и commit; будущие результаты не объявляются PASS.

Первое code-review CLI обнаружило ложный PASS при двух отсутствующих pins и жёстко закреплённый текущий blocker. Автор исправил их до первого выполнения. Первая synthetic попытка дала 14 PASS и один FAIL (лишний newline); после точечной правки и независимого review выполнен только упавший метод: exit 0. Полного повтора не было. Тест не изменялся. CLI_REVIEW_RU.md и оба raw receipt сохраняют эту историю отдельно от лимитов приложения.

CLI интегрирован root в 4e014971e5db33f9106de86399424bedf2ca15bb и push подтверждён. PR #10 остаётся draft/unmerged, connector подтвердил точный head. Преждевременные формулировки заменены ссылками на фактически доступный read-only интерфейс и его evidence. Финальное review управляющего пакета проводится после этой интеграции.

Финальный независимый verdict bos3_candidate_review: ACCEPT_SCOPED_DEVELOPMENT_CONTROL, без новых blocking findings. Прежний P1 закрыт фактической интеграцией CLI. WORKFLOW_REVIEW_RU.md сохраняет scope и проверенные условия; это не браузерная или продуктовая приёмка.

Статическая проверка новых записей root: git diff --check, exit 0. Новые Django/app tests, frontend build, HTTP, browser, lifecycle, DB/secret операции не выполнялись. Отдельная однократная read-only проверка CLI на реальном управляющем пакете имеет собственные config-* receipts и не повторяет synthetic unittest.

Фактическая CONFIG_INTEGRATION: validate exit 0, PASS согласованности; status exit 0. QA bos3_crm_impl, каждая команда один раз. Проверенный CONTROL_STATE SHA-256 50A821B5F652368D8F03244EE90FBD118151C9CA7900109F2A278D6F21A2C70C относится к состоянию перед этим документальным закрытием B30-DEV-WORKFLOW; после добавления verdict и DONE прогон не повторялся. Вывод сохранил разные dev.3/dev.1, pending delivery, false readiness, cutoff_reached=false. Это не фактическая проверка работоспособности сайта.

В первичном config receipt QA ошибочно захешировал PDF manifest вместо LIGHT_PREVIEW_CANDIDATE.json. Оригинал сохранён. Исправление provenance оформлено отдельным config-provenance-correction.json: after-run SHA-256 3DE8AB135C9E16F3298A955EB0D6D9484578E9225F4C10FE0C78128C5A73E6A2, worktree/staged diff пуст. Его нельзя выдавать за pre-run hash или новый запуск validation.

## Сохранённые ограничения

Один существующий heartbeat, тот же root-адресат, период 15 минут. Текущий prompt прочитан из automation.toml; он уже содержит недельный срок и границы. Никаких новых сервисов, расписаний, чатов, native goals, изменений модели или прав. Независимо проверенный alias integrator не является новым главным процессом.

Dev-tool commit не изменяет принятый продукт f55 и не включается автоматически в maintenance allowlist. Пакет приложения, PDF и evidence 9/9 AST/build/12 artifacts не пересобирались и не перепроверялись. TECHNICAL_READY/PILOT_ALLOWED/MVP=false. После cutoff допустимы только чтение, итог и пауза automation; приложение не останавливать.
