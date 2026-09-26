# BATCH-02 · findings інтеграції erp/views.py

20.09.2026. Root integration виявила перехресний baseline дефект N2.patch: diff повторно сформовано проти канонічного дерева, де trace callback уже був доданий, тоді як ізольований N2/source містив первісний view без trace. Через це останній patch містив видалення callback. Незалежний source review прийняв N2 логіку, але не виявив цю зміну baseline фінального patch до інтеграційної перевірки.

Перший integrated адресний запуск завершився exit1 до test methods: URL resolver отримав AttributeError `erp.views has no attribute order_trace`. Raw/report збережено у execution/batch02/integrated. Це помилка складання двох прийнятих змін; не новий дефект trace/adjust logic і не PASS тестів. За повідомленням root, віддалений помилковий source не публікувався.

Root відновив точний trace suffix із прийнятого trace/source і лишив N2 preview. Reviewer статично порівняв:

- prefix canonical views до декораторів order_trace дорівнює прийнятому N2/source view, крім кінцевих переносів;
- suffix canonical від `@require_GET / @errors / def order_trace` дорівнює прийнятому trace/source suffix, крім кінцевого переносу;
- AST і повна композиція після нормалізації лише стику переносів збігаються.

Canonical erp/views.py SHA256: `feb05d367aedf37b43d2e3a257eeffd808b54f2d44f32d4a4487bd54711e5b72`. N2 source view SHA `612769c276be2425b4810c4b62c0b887ff7987781ecd68b2c932d1a6e7ab1c58`. Відновлення source статично **ACCEPT_SCOPED_INTEGRATION**; наступний integrated02 runtime результат оцінюється окремо, не вигадується.

Надалі patch має порівнюватися з immutable baseline card, не мінливим canonical. Для перетинів файлів root порівнює композицію прийнятих semantic hunks перед тестом/commit. Ні scope, ні критерії assertions не послаблено. Reviewer тестів не запускав.
