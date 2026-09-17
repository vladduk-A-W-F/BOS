# C01 · сумісність старої UI/HTTP перевірки

Full24 actual `check_original.py` зупинився на `keyboard search and native dialog`: старий тест шукав змінну ref={dialog} від попередньої Topbar форми. C01 використовує нативний ControlledTask з ref={ref}; Ctrl+K збережено. Змінено лише source oracle, який тепер явно шукає той самий нативний елемент у ControlledTask та handler скасування. Це source check, не браузерний доказ.

Старі32 назви й лічильник побуквено збігаються з actual B03 report. Три додані C01 assertions (create preview, update preview, raw bypass refusal) виконуються й окремо звітуються як additional_passed=3; вони не змінюють фіксований legacy count151+5 і не прибрані. verify.py, його exact equality32 та11 критеріїв незмінні.

Actual окремий прогін на новій ownSQLite/media: exit0,32/32 +3/3additional; exactlabels proof BASELINE_LABELS.json. Product backend, UI, міграції й робочі БД не змінювалися. Canonical full24 продовжується на попередньому source; інтеграція цієї однієї правки очікує незалежного огляду й наступного full25.
