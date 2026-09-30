# UXD03-WAIT-01 V2: одно решение о раскрытии причины

Reviewer `/root/bos3_candidate_review`, 27.09.2026; clean source e710.
V2 SHA-256 `3b68b476bcb73350399d9733735f99ecd4b7d68003032471dcc3d21dc9c3312b`.
Verdict: **REVISE_PENDING_DISCLOSURE_DECISION**. Executions: 0.

Прежние gaps участника/source checks, waiting_guard, transition matrix,
lock/CAS/dispatch/replay и end после drift/deactivation устранены в
контракте. Это не реализованное или проверенное поведение.

Остался P1: объявление произвольной причины «несекретной» не обеспечивает
серверной защиты содержимого. Free-text 3-240 символов попадает в общие
Task projection/history для permitted readers, включая observer.
Trim/длина/непустота не обнаруживают медицинские, финансовые или другие
чувствительные сведения. Нельзя утверждать семантическую фильтрацию.

Нужно зафиксировать один режим:

1. Произвольная причина является потенциально чувствительной business
   metadata, видимой всем уже source-authorized Task readers; это осознанный
   disclosure contract, без обещания семантической фильтрации.
2. Shared projection/history содержит только серверный reason code из
   закрытого перечня. Свободное пояснение и field-level access отдельно.

Root один раз задал владельцу вопрос о выборе, рекомендуя второй режим.
Ответ пока отсутствует. Это вопрос поведения, не permission на БД.
Запрет всех generic updates во время wait остаётся продуктовым предложением;
миграция, implementation и runtime change не назначены. Следующий шаг:
фактический выбор -> уточнённый exact contract -> независимый review ->
отдельная migration-backed карточка/допуск, если согласованы.
