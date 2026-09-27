# B30-DESIGN-NEXT: независимое static integration review

27.09.2026. Authors: действующий отдел дизайна и отдельные QA/review роли. Canonical reviewer bos3_candidate_review не автор. Source pair32acfb6ad3a0aeabe2f7501a28ba878dfeaeec87 и0d49a8991f1abcbf18e6d21dd11386e427cdd18c из bos3-product-design/repo, base54764b0 с product f55 в истории. Canonical base до включения72b3e46. Verdict ACCEPT_SCOPED_STATIC_INTEGRATION_B30_DESIGN_NEXT; P0–P2 findings нет.

Проверено: public BosOnlineBrochure использует local registry, не private API; case intent сохраняется к обычному входу. Workspace открывается после authenticated operations/status. Monitor монтируется внутри authenticated App, checks scope/access_revision, очищает данные на401/403/drift, отменяет pending запросы приunmount. Finance metric только при bosCan('finance'); нет новыхinterval/polling. Два independent snapshot GET при открытом Today/Helicopter являются документированным ограничением, не единым snapshot store.

Сверены frozen source/build/CSS/app/registry hashes из ACCEPT_SCOPED_RUN3.md с immutable bytes; wiring build_frontend.cjs соответствует источникам. Existing visual evidence сохранено: первая дизайн-карточка28 captures двух частей того же build, brochure/monitor8captures run3. Все failed runs остаются provenance; новый browser/build/AST/тесты не запускались root.

Разрешён последовательный перенос точных двух source commits с сохранением evidence. Первый компонент: общий visual system32acfb6; второй: brochure/monitor0d49a89. Отдельный root commit на каждый компонент, без squash исторических FAIL или main merge. Это не новая динамическая backend/auth/progress/ERP/CRM/release приёмка. Product/runtime pin остаётся f55 до нового exact package/delivery receipt, readinessfalse.

ARCH-02 документальная финансовая подпись исправляется автором отдельно без UI/formula/build/browser изменений; её новый exact diff требует delta review. Она не меняет numeric UI correctness уже проверенного source.
