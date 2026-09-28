# Dev9: исходная копия и два отказа до обновления

Root включает только сохранённые документы и доказательства в действующую
ветку `codex/bos3-prerelease-20260927`. База документационного перехода:
`aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`.

Продукт `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf` и подготовленная
immutable-копия `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975` не меняются.
Новый documentation head не становится runtime pin.

1. Source-only clone и checkout выполнены по одному разу с native0.
   Digest `e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0`
   относится к подготовленной копии, не к работающему приложению.
2. Единственный no-write preflight native2 не сохранил внутреннюю причину.
   Его сообщение не доказывает занятость порта. Apply/start/GET не начаты.
3. Отдельный diagnostic invocation native1 заблокирован Windows execution
   policy до тела скрипта. CIM/listener observation не выполнены.
   `ROOT_TOOL_ERROR.txt` является транскрипцией вывода инструмента, не
   отдельным raw native stderr capture.

Основной пакет принят `ACCEPT_SCOPED_SAVED_EVIDENCE_PACKAGE_INTEGRITY`:
32 immutable inputs и два отдельных независимых verdicts. Коллизии имён
REVIEW и DELTA_REVIEW устранены с сохранением всех исходных текстов и hashes.
Пакет observation-refusal принят отдельно: 11 source-target копий.
Эти проверки не повторяют source preparation, preflight или runtime.

Текущий owner instance по последним сохранённым данным всё ещё prepared
на D dev8/60f. Доступность UNCONFIRMED. Историческая dev7-квитанция не
является подтверждением текущего сайта. Readiness false.

Предельные счётчики сохранены: global problem2/3, old-window start1/1,
preflight1/1, read-only observation1/1. Никакого автоматического повтора,
изменения политики Windows или обхода через inline/encoded/другой host нет.
Следующий обязательный шаг принадлежит владельцу: решить вопрос разрешённого
запуска диагностического скрипта и отдельного нового точного scope.
Решение не подменяет independent review и не разрешает восстановление само
по себе. Приложение root дополнительно не останавливал.
