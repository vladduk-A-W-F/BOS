# NETWORK-BROWSER-ONBOARDING-FIX

Підстава: run35516516284, Chrome152 відкрив застосунок і виконав login, після якого новий профіль показав штатний вибір сфери діяльності. Harness помилково одразу очікував navbar. Скріншот, ARIA та raw report збережені; бізнес-сценарії не починались.

Allowlist: .github/ci/network_browser_acceptance.py, ця картка, відповідні evidence. Пройти штатний onboarding кліком видимого елемента інтерфейсу, без підміни auth, localStorage або прав. Зберегти assertions реєстрів, ролей, рухів та мобільних розмірів. Автор browser_acceptance, reviewer currency_completion.

Перед наступним запуском source review того самого harness виявив залежну помилку select locator: Playwright включає option text у wrapped label, тому exact get_by_label не збігається. У тій самій test-defect картці helper знаходить контроль через label та окремо перевіряє точний власний текст підпису. Правила бізнес-результатів незмінні; між двома редакціями patch жодного запуску не було. Перший onboarding-only review замінюється review повного остаточного diff.

Наступне виконання — тільки після незалежного review конкретного patch; старі спроби не видаляються й ліміт не скидається. Runtime, main, production та готовність не змінюються.
