# B30-RECOVERY-OBSERVATION-DIAGNOSIS-ONCE

## Межа пакета

Це окремий saved-evidence package для відмовленого read-only observation
script. Він не змінює parent preflight package, не запускає observation,
runtime, DB, процес, мережу, HTTP, start або GET.

## Зафіксований результат

Root виконав один exact invocation (`1/1`) final script
`observe_bos3_server_and_port8030_once.ps1` з SHA-256 `abf8ba68…`.
Він завершився native exit `1`, бо execution policy не дозволила завантажити
`.ps1`. Відмова сталася до script body: CIM та listener observations не
виконувались, `observation1` не створено, а inner preflight cause не
встановлено.

`ROOT_TOOL_ERROR.txt` є verbatim транскрипцією tool result, а не independently
captured native stderr byte stream. Тому він не може бути використаний для
твердження про зайнятий порт, ідентичність сервера або фактичну доступність
runtime. Поточна доступність лишається `UNCONFIRMED`.

Apply, official start та post-start GET мають `0` invocations. Global problem
accounting лишається `2/3`; historical preflight cap `1/1` і one-shot
read-only observation cap `1/1` витрачені. Новий observation, policy bypass,
encoded/inline replay, alternate host/tool або recovery цим пакетом не
дозволяються.

## Цілісність

Пакет містить 11 явно дозволених несекретних artifacts. Усі перевірені як
byte-identical за SHA-256 і довжиною. Author manifest збережено під
`SOURCE_MANIFEST.json` з явним `source_path: "MANIFEST.json"`, щоб не
конфліктувати з package manifest. Reviewer outputs не перезаписувалися.
Private owner state, credentials, secrets, DB, media та широкі logs не
включені.

Пакет передається незалежному reviewer для перевірки байтів та wording, потім
root. Він не є delivery, runtime або readiness acceptance.
