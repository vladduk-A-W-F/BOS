# A09 · незалежний огляд server configuration draft

12.09.2026. Перевіряючий агент не редагував checkout або draft кандидата; лише тимчасові probes/notes. A08 залишалася основною роботою root.

## Обсяг

Порівняно master v2.1, A09 у task table, server_settings/server_wsgi/server_config і 8 тестових методів кандидата. Тут оцінюється рання відмова від небезпечної/непрацездатної конфігурації та in-process proxy trust. Це не приймання установника, мережевого сервера, TLS, PG, Windows, health/logs або A09 загалом.

## Фактичні зауваження

1. **Перекриття DB/media у зворотному напрямку.** DB=`root/data`, media=`root/data/private` приймалися як при відсутньому `data`, так і при існуючому звичайному файлі `data`. Один шлях не може одночасно бути SQLite файлом і батьком каталогу media. Два subprocess probes створили WSGI application; спроб DB/socket не було. Потрібна симетрична перевірка вкладення.
2. **POSIX подвійний початковий slash обходив source exclusion.** `_locations` приймав root=`//tmp/.../source`, source_root=`/tmp/.../source`. На окремому синтетичному каталозі `os.path.samefile` підтвердив тотожність. Checkout не чіпали. Потрібна відмова для такого alias або metadata-safe canonicalization після відмови для links; не можна покладатися лише на lexical parents.
3. **Звичайний файл замість предка DB.** Існуючий синтетичний `root/data` файл і DB=`root/data/bos.sqlite3` приймалися; WSGI створювався. Потрібна перевірка, що кожен уже існуючий предок DB/media/static є каталогом. Відсутні майбутні каталоги самі по собі не є помилкою конфігурації на цьому кроці.

Докази: `tmp/A09_INDEPENDENT_PROBES.json/.log`, `tmp/A09_FILE_ANCESTOR_PROBE.json/.log`. У всіх subprocess записах `attempts=[]`. До/після перевірявся незмінний склад synthetic installation; жодного `sqlite3.connect`, `socket.bind`, `socket.connect`.

Додатково на ефективних налаштуваннях після імпорту приймалися SESSION_COOKIE_NAME=`sessionid` та CSRF_COOKIE_NAME=`different_csrftoken`. Default profile має правильні значення, тож це не віддалений header bypass. Водночас це прогалина заявленого effective validator: існуючий frontend (`frontend/boss_app_source.html`, fetch wrapper) читає саме cookie `csrftoken`, а `/api/auth/csrf/` не повертає окремий token JSON. Рекомендовані вузькі перевірки installation UUID/session-cookie відповідності та фіксованого CSRF-cookie контракту.

## Рішення про режими каталогів

Початковий контракт помилково описував exact 0700, хоча validator перевіряв лише відсутність group/world доступу. 0500 top-level root може бути валідним для вже підготовленої інсталяції з writable дочірніми data/private каталогами; він не є blocker сам по собі. Погоджено не вимагати 0700 лише для узгодження тексту, натомість явно визначити owner read/search та приватність. Режими без owner traversal потрібно відхиляти за mode bits незалежно від запуску тесту під root. Придатність writable children приймає наступна installer/runtime перевірка.

## Proxy і межа консенсусу

У поточному bounded огляді не знайдено обходу exact trusted peer: middleware спочатку очищує forwarding headers, відхиляє невідомий REMOTE_ADDR, неоднозначний protocol/client IP, повертає тільки перевірений client IP чинному login limiter. Це не доводить реальної мережевої ізоляції; reverse proxy мусить перезаписувати заголовки й обмежувати upstream.

Автор кандидата отримав усі зауваження і робить tmp-only правки. Остаточний scoped consensus можливий після перегляду цих правок і targeted результатів. Канонічну інтеграцію/fullverify виконує root після A08.

## Остаточний scoped consensus

Після правок повторно прочитано `_absolute`, `_locations`, `validate_effective` та нові регресії. Усі три конкретні path blockers усунено: симетричне перекриття, неканонічний // / UNC alias, звичайний файл у предках. Фіксуються installation UUID і cookie names; default session/CSRF flow збережено. 0500 дозволений для заздалегідь підготовлених children; owner read/search і відсутність group/world доступу перевіряються явно.

Фактичний авторський `tmp/A09_REVIEW_FINAL.json/.log`: **12/12 методів, 62 subprocess probes, 0 DB/socket attempts**. Окремий source alias тест доводить `samefile(alias, source)` на власному synthetic source, тому відмова не маскується лише режимом checkout. Незалежні дофіксові probes збережені. Самостійний повтор усієї suite не робився: root ще проведе канонічну інтеграцію/fullverify.

Переглянуті точні SHA:

- server_config.py: `616b23c559e0c8a4dd460aa750645e1b72b3945b1600c739b4ab5f03f868f855`
- server_settings.py: `673df71d572c5855b3a175cbe1ee3d45ecde5e1bba6c2376cf06a14608c968e9`
- server_wsgi.py: `83bcf4412eb752ee614b795aa5688c86fabab4f66c506a70d1de4354798bb0e0`
- tests/test_server_config.py: `bcc9f23e66d4a0e520fedd248bb9fd0c57ced751d954d0f91621cc6691295087`

**Консенсус:** кандидат конфігурації прийнятний у заявленому локальному обсязі; невирішених blockers цього огляду немає. Це не приймання A09/gate8: installer, actual HTTP/TLS/proxy, health/logs, upgrade, PG, Windows і остаточний fullverify залишаються окремими відкритими вимогами.
