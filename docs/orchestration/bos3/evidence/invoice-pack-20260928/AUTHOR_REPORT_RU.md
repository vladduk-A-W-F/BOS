# B30-INVOICE-PACK-DEV8 · авторський звіт

## Походження

- Canonical source, тільки для читання:
  `D:\3\BOSDev\workspaces\bos3-canonical\repo`
- Exact source commit: `c00c60aad0c4f8e70251da3c7174ed105089198b`.
- Source SHA-256: `boss_project/version.py`
  `f6f2aa4c3b4434a79aeb48729b77f0a54e694dfb18ebf42b1a9e134dfe56b776`;
  `README.md` `35ce8760a3c7922a4ff336a36b9df0b9c1b63ac122796471a66f70ea11180999`;
  `README_UA.md` `00d94b5863bac317f371de8620b3fb2d409b9db8910ace08c8bd016d734f76ae`.

## Зміна у mirror

У D-only mirror змінено лише три файли з allowlist:

- `boss_project/version.py`: `0.3.0-dev.7` -> `0.3.0-dev.8`.
- `README.md` і `README_UA.md`: додано вузький опис того, що invoice-only
  currency входить до фінансової проєкції, а empty snapshot зберігає EUR
  fallback; оновлено delivery boundary до installed dev.7 / dev.8 pending.
- PDF прямо лишено незмінною пам'яткою dev.7: backend-виправлення не змінює
  її сценарій і не є підставою для регенерації або нового PDF-доказу.

Збережено межі preview, UXD02, browser-acceptance, уроків, readiness і
production. Це не доставлений runtime та не приймання релізу.

## Перевірка

Виконано лише читання exact source commit і SHA-256 трьох source/result files.
Не запускалися tests, imports, build, PDF regeneration, runtime, DB, network
або canonical/C writes. Незалежний review ще потрібний; автор не приймає цей
пакет.
