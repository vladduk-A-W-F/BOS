# BoS 3.0 dev.3: светлое превью

27.09.2026. Кандидат реализован, собран и независимо рассмотрен. Теперь действительно установлен на ПК владельца; доставка и одна desktop/mobile entry-проверка приняты отдельно. Это не полный release GO.

## Точная версия

- Продукт: f55a15de4006d10c0d7c65f8a2ca8499fbb99819, версия 0.3.0-dev.3.
- UI: aee8d0ee41afd5cba256a0b4a4deddadf7af6e4e, база реализации defd1fc12545053159a3a888013d096c79157fd3.
- Дерево продукта: 7630570bbe2221ee3b8b1c3c3e27e90d99341c4c.
- Canonical: C:/Users/user/.codex/worktrees/bos-consolidation-plan/repo, codex/bos3-prerelease-20260927.
- Паспорт 12 файлов и SHA-256: LIGHT_PREVIEW_CANDIDATE.json. Последующий документационный HEAD не заменяет product pin.
- PR для review: https://github.com/vladduk-A-W-F/BOS/pull/10. Draft, не merge в main.

## Реализовано

Первый экран стал светлым интерактивным превью с зелёным акцентом, локальной иллюстрацией метизов и тремя отдельно выбираемыми кейсами. Доступны исходные факты, ожидаемый учебный эффект, контекстные диаграммы, узнаваемые значки и просмотр передачи между отделами с действием и контролем. Основное действие выбранного кейса ведёт к обучению через персональный вход; сам просмотр не сохраняет прогресс и не меняет ERP/CRM.

В CSS предусмотрены desktop-композиция и мобильное расположение. Диаграммы не изображают реально выполненный урок: 140 + 360 = 500 комплектов; 250 + 20 = 270 проверенных остатков, не объём отгрузки; 10 000 + 6 400 = 16 400 грн. Дефицит 120 шайб показан отдельно от комплектов. Защищённая рабочая область сохраняет прежнюю тему; её общая локализация и доводка остаются последующим релизным этапом. PDF остаётся вспомогательной трёхстраничной памяткой.

## Проверено

| Доказательство | Результат и граница |
| --- | --- |
| Независимое review кода и финального AST oracle | start_overview_review: ACCEPT_SCOPED_STATIC / ACCEPT_SCOPED_AST_ORACLE |
| Отдел дизайна | ACCEPT_STATIC по фактическому diff snapshot; собственный shell доступ UNCONFIRMED, не браузерная проверка |
| Entry-flow попытка 2/3 | 9/9 PASS, native exit 0; без браузера, сети, БД, уроков и lifecycle |
| Одна штатная сборка новой source-ревизии | native exit 0; JSX compiled, local script assets wired |
| Версия, README, manifest и PDF | bos3_preview_archaeology: ACCEPT_SCOPED_STATIC; все три готовые PNG-страницы просмотрены, без обрезаний/наложений |
| Подготовка обновления | Независимое ACCEPT_SCOPED_STATIC exact-pin runner; не запускался |
| Фактическое обновление 27.09 | Одно capture/stop/apply/start, exits0; сохранность data/media/credentials до browser login; dev.3 exact f55, loopback waitress |
| Одна entry-проверка 27.09 | Светлый старт, desktop1365x900/mobile390x844, case intent payment, обычный вход, not_started; ACCEPT_SCOPED_DELIVERY_AND_ENTRY, без уроков и full acceptance |

Raw output, receipts и review находятся в evidence/light-preview-20260927/, evidence/light-preview-pack-20260927/ и evidence/light-preview-delivery-20260927/. Успешные проверки не повторяются без новой причины.

## Что остаётся открытым

Выданный runtime: 0.3.0-dev.3 / f55a15de4006d10c0d7c65f8a2ca8499fbb99819; LOCAL_RUNTIME_RECEIPT.json. Capture/stop/apply/start exits0, protected payload до/после старта совпал. Браузер подтвердил dev.3 по адресу http://127.0.0.1:8030/, светлый старт, desktop/mobile и обычный вход. Независимый verdict ACCEPT_SCOPED_DELIVERY_AND_ENTRY.

Прямое разрешение «СДЕЛАЙ ПОЛНЫЙ ПЕРЕХОД ДА» получено и проверено root; одно окно выполнено. Новый общий ответ «ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ» действует для обычных reviewed owner-local обновлений в согласованном плане. Entry-проверка не включала уроки, ERP/CRM mutations, migrations/reset, full/PG/E2E или повторы.

Исторические результаты обучения и CRM из dev.2 не становятся новой динамической приёмкой f55a15d. Сохраняются fixture 3/3 с исправлением только статически, прежний progress 3/3, использованное Node-исключение 1/1 и ограничения P05/A09/A10/A11. Внешние тестировщики, reset-контракт, фактическое прохождение и owner feedback остаются отдельными условиями. Старые CANDIDATE_MANIFEST.json и CANDIDATE_ACCEPTANCE_RU.md сохранены как история dev.2.

TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false. Недельный cutoff 04.10.2026 23:59 Europe/Berlin не заменяет full acceptance и feedback. Старый 11.10 не продлевает окно. Текущие исполнители: TEAM_CURRENT_RU.md; следующий новый scope B30-DESIGN-NEXT ведётся отдельно от f55.
