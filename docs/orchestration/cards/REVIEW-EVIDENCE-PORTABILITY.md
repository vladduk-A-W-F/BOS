# REVIEW-EVIDENCE-PORTABILITY

Пріоритет P1. Власник `bos_evidence`. Статус **PARTIAL_ON_HOLD_FREEZE**. Автоматичне виконання заборонене.

## Проблема та доказ

Closeout v17 опублікував переносні summary receipts і matrix pins. Незалежно перераховано SHA-256 для 12 опублікованих receipts/reviews — усі збігаються з `CYCLE_V17_MATRIX.json`. Водночас частина первісних S2/service/source-package raw, manifests, independent reviews та authorization history усе ще доступна лише через локальні `D:/...` посилання всередині summary. Посилання не замінює перевірку початкових байтів.

PR1 повідомляє відновлення тимчасового HTTPS 21.09.2026 о 21:40:36 UTC і 7/7 HTTP/auth/origin checks, але raw recovery receipt у Git-дереві відсутній. Committed outage 21:27 UTC та історичний smoke 20:53 UTC не доводять поточну доступність або стійкість після restart.

## Наступний крок після рішення власника

Імпортувати вже наявні дозволені raw/manifests/reviews без повтору тестів; додати SHA-256, source/product commit, середовище, час, scope, verdict та reviewer. Якщо файл недоступний — позначити `MISSING_ORIGINAL`, а не відтворювати доказ.

Дозволені файли: `docs/orchestration/evidence/**`, evidence index, поточний daily report. Заборонено змінювати product, AGENTS, readiness, pilot або запускати suites.
